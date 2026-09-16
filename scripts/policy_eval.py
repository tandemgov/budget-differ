"""Policy-change evaluation: does the tool surface the changes that matter? See docs/evaluation.md.

  extract            re-read raw reports with an independent splitter into change units (tests/policy_reference/units/)
  sample             write blind labeling batches to .policy-eval/batches/
  merge              fold .policy-eval/labels/ into tests/policy_reference/ (never overwrites human labels)
  worksheet          export a CSV for human adjudication to .policy-eval/
  review             bounded acceptance-review packet (misses, false alarms, samples, sections to read in the originals)
  import FILE.csv    fold adjudicated rows back in
  score [--json]     missed substantive changes, false alarms, alignment disagreements vs the size-only baseline
  score --as KIND=substantive   re-score as if a label kind counted as substantive (e.g. funding_amount), to show a definition's effect
  --set holdout      any command, on the held-out comparisons instead of the demonstration set

Run as: uv run python scripts/policy_eval.py COMMAND
"""

from __future__ import annotations

import json
import random
import re
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from rapidfuzz import fuzz, process

from budget_differ.compare import compare_documents, load_document
from budget_differ.config import approps_repo
from budget_differ.corpus import available_reports, raw_path
from budget_differ.models import ChangeClass
from budget_differ.policy import REVIEW
from budget_differ.segment.preprocess import body_bounds, extract_pre_text

EVAL_DIR = ROOT / ".policy-eval"
UNITS_DIR = ROOT / "tests" / "policy_reference" / "units"
BATCH_DIR = EVAL_DIR / "batches"
LABELS_DIR = ROOT / "tests" / "policy_reference"

# The rules were developed reading "demo" edits; "holdout" was labeled after they were frozen.
SETS = {
    "demo": [
        ("house", "energy-water", "CRPT-118hrpt580", "CRPT-119hrpt213"),
        ("house", "energy-water", "CRPT-119hrpt213", "CRPT-119hrpt667"),
        ("house", "legislative-branch", "CRPT-118hrpt555", "CRPT-119hrpt178"),
        ("house", "legislative-branch", "CRPT-119hrpt178", "CRPT-119hrpt666"),
    ],
    "holdout": [
        ("house", "energy-water", "CRPT-117hrpt394", "CRPT-118hrpt126"),
        ("house", "legislative-branch", "CRPT-117hrpt389", "CRPT-118hrpt120"),
    ],
}
COMPARISONS = SETS["demo"]
# Two paragraphs are the same passage edited when their similarity clears this and each is the other's best match.
EDIT_PAIR_RATIO = 60.0
# Units whose word-level edit is at most this many words are where a size-based classifier is weakest, so the sample takes all of them.
SMALL_EDIT_WORDS = 12
SAMPLE_SEED = 20260916
# Energy-Water reports are several times longer; beyond the small edits, sample this many of the remaining units per comparison.
LARGE_SAMPLE = 80
# Held-out comparisons take every small edit plus this many other units, whatever the subcommittee.
HOLDOUT_SAMPLE = 40
BATCH_SIZE = 70
# A tool paragraph matches a reference paragraph at this normalized similarity or better (the splitters differ on hyphen rejoin and table edges).
LOCATE_RATIO = 90.0

_HYPHEN_WRAP = re.compile(r"(?<=[a-z])- (?!(?:and|or)\b)(?=[a-z])")
_LEADER = re.compile(r"\.{4,}")


def comparison_id(old: str, new: str) -> str:
    return f"{old}__{new}"


@dataclass
class RefPara:
    text: str
    heading: str  # nearest preceding heading-like line, for context only
    index: int


def split_paragraphs(raw: str) -> list[RefPara]:
    """Paragraphs from GPO fixed-width text by indentation and blank lines only, sharing no code with the tool's segmenter.

    Deeper indents (9+) are headings or table cells; dotted-leader lines are table rows.
    """
    lines = extract_pre_text(raw).split("\n")
    start, end = body_bounds(lines)
    out: list[RefPara] = []
    buf: list[str] = []
    heading = ""

    def flush() -> None:
        nonlocal buf
        if buf:
            text = re.sub(r"\s+", " ", " ".join(buf)).strip()
            text = _HYPHEN_WRAP.sub("", text)
            if len(text.split()) >= 4:
                out.append(RefPara(text, heading, len(out)))
        buf = []

    for line in lines[start:end]:
        stripped = line.strip()
        indent = len(line) - len(line.lstrip())
        if not stripped:
            flush()
            continue
        if _LEADER.search(line):
            flush()
            continue
        if indent >= 9:
            flush()
            if re.search(r"[A-Za-z]", stripped) and len(stripped) < 90:
                heading = stripped
            continue
        if 2 <= indent <= 8:
            flush()
            buf = [stripped]
        elif buf:
            buf.append(stripped)
    flush()
    return out


def _key(text: str) -> str:
    return re.sub(r"[^a-z0-9$%]+", " ", text.lower()).strip()


def extract_units(old_raw: str, new_raw: str) -> list[dict]:
    olds = split_paragraphs(old_raw)
    news = split_paragraphs(new_raw)
    old_by_key: dict[str, list[RefPara]] = defaultdict(list)
    for p in olds:
        old_by_key[_key(p.text)].append(p)
    units: list[dict] = []
    new_left: list[RefPara] = []
    matched_old: set[int] = set()
    for p in news:
        pool = old_by_key.get(_key(p.text))
        if pool:
            o = pool.pop(0)
            matched_old.add(o.index)
            if o.heading != p.heading:
                units.append(_unit("relocated", o, p))
        else:
            new_left.append(p)
    old_left = [p for p in olds if p.index not in matched_old]

    pairs: list[tuple[RefPara, RefPara]] = []
    if old_left and new_left:
        old_keys = [_key(p.text) for p in old_left]
        new_keys = [_key(p.text) for p in new_left]
        best_new = [process.extractOne(k, new_keys, scorer=fuzz.ratio) for k in old_keys]
        best_old = [process.extractOne(k, old_keys, scorer=fuzz.ratio) for k in new_keys]
        used_old: set[int] = set()
        used_new: set[int] = set()
        for i, (_, score, j) in enumerate(best_new):
            if score >= EDIT_PAIR_RATIO and best_old[j][2] == i:
                pairs.append((old_left[i], new_left[j]))
                used_old.add(i)
                used_new.add(j)
        old_left = [p for i, p in enumerate(old_left) if i not in used_old]
        new_left = [p for j, p in enumerate(new_left) if j not in used_new]
    units.extend(_unit("edited", o, n) for o, n in pairs)
    units.extend(_unit("removed", o, None) for o in old_left)
    units.extend(_unit("added", None, n) for n in new_left)
    units.sort(key=lambda u: (u["new_index"] if u["new_index"] is not None else u["old_index"], u["type"]))
    for k, u in enumerate(units):
        u["id"] = f"u{k:04d}"
    return units


def _unit(kind: str, old: RefPara | None, new: RefPara | None) -> dict:
    import difflib

    changed = None
    if old is not None and new is not None:
        a, b = old.text.split(), new.text.split()
        sm = difflib.SequenceMatcher(None, a, b, autojunk=False)
        changed = sum(max(i2 - i1, j2 - j1) for tag, i1, i2, j1, j2 in sm.get_opcodes() if tag != "equal")
    return {
        "type": kind,
        "old_heading": old.heading if old else None,
        "new_heading": new.heading if new else None,
        "old_text": old.text if old else None,
        "new_text": new.text if new else None,
        "old_index": old.index if old else None,
        "new_index": new.index if new else None,
        "changed_words": changed,
    }


def _entries():
    repo = approps_repo()
    by_id = {e.package_id: e for e in available_reports(repo)}
    return repo, by_id


def cmd_extract() -> None:
    repo, by_id = _entries()
    UNITS_DIR.mkdir(parents=True, exist_ok=True)
    for _, _, old_id, new_id in COMPARISONS:
        old_raw = raw_path(repo, by_id[old_id]).read_text(errors="replace")
        new_raw = raw_path(repo, by_id[new_id]).read_text(errors="replace")
        units = extract_units(old_raw, new_raw)
        path = UNITS_DIR / f"{comparison_id(old_id, new_id)}.jsonl"
        path.write_text("".join(json.dumps(u) + "\n" for u in units))
        print(f"{comparison_id(old_id, new_id)}: {len(units)} units {dict(Counter(u['type'] for u in units))}")


def _load_units(cid: str) -> list[dict]:
    return [json.loads(line) for line in (UNITS_DIR / f"{cid}.jsonl").read_text().splitlines()]


def selected_units(subcommittee: str, cid: str, holdout: bool = False) -> list[dict]:
    units = _load_units(cid)
    if subcommittee == "legislative-branch" and not holdout:
        return units
    small = [u for u in units if u["type"] == "edited" and (u["changed_words"] or 0) <= SMALL_EDIT_WORDS]
    rest = [u for u in units if u not in small]
    rng = random.Random(f"{SAMPLE_SEED}-{cid}")
    n = HOLDOUT_SAMPLE if holdout else LARGE_SAMPLE
    return small + rng.sample(rest, min(n, len(rest)))


def cmd_sample() -> None:
    BATCH_DIR.mkdir(parents=True, exist_ok=True)
    n_batches = 0
    for _, sub, old_id, new_id in COMPARISONS:
        cid = comparison_id(old_id, new_id)
        for old in BATCH_DIR.glob(f"{cid}__*.json"):
            old.unlink()
        chosen = selected_units(sub, cid, holdout=COMPARISONS is SETS["holdout"])
        blind = [
            {k: u[k] for k in ("id", "type", "old_heading", "new_heading", "old_text", "new_text")} for u in chosen
        ]
        for b in range(0, len(blind), BATCH_SIZE):
            n_batches += 1
            (BATCH_DIR / f"{cid}__{b // BATCH_SIZE:02d}.json").write_text(
                json.dumps({"comparison": cid, "units": blind[b : b + BATCH_SIZE]}, indent=1)
            )
        print(f"{cid}: {len(chosen)} selected")
    print(f"{n_batches} batch file(s) in {BATCH_DIR}")


def cmd_merge() -> None:
    LABELS_DIR.mkdir(parents=True, exist_ok=True)
    merged: dict[str, dict] = defaultdict(dict)
    for path in sorted((EVAL_DIR / "labels").glob("*.json")):
        data = json.loads(path.read_text())
        merged[data["comparison"]].update(data["labels"])
    for cid, labels in merged.items():
        dest = LABELS_DIR / f"{cid}.json"
        existing = json.loads(dest.read_text())["labels"] if dest.exists() else {}
        for uid, lab in labels.items():
            if existing.get(uid, {}).get("reviewer", "draft") == "draft":
                existing[uid] = lab
        units = {u["id"] for u in _load_units(cid)}
        unknown = set(existing) - units
        if unknown:
            raise SystemExit(f"{cid}: labels for unknown unit ids {sorted(unknown)[:5]} — re-run extract?")
        out = {"comparison": cid, "labels": dict(sorted(existing.items()))}
        dest.write_text(json.dumps(out, indent=1, ensure_ascii=False) + "\n")
        print(f"{cid}: {len(existing)} labels {dict(Counter(v['kind'] for v in existing.values()))}")


WORKSHEET_FIELDS = [
    "comparison", "id", "type", "old_heading", "new_heading", "changes", "old_text", "new_text",
    "draft_kind", "draft_categories", "draft_rationale", "reviewer_kind", "reviewer_categories", "reviewer_note", "reviewer_name",
]


def _word_changes(old: str | None, new: str | None) -> str:
    import difflib

    if not old or not new:
        return ""
    a, b = old.split(), new.split()
    sm = difflib.SequenceMatcher(None, a, b, autojunk=False)
    return " | ".join(
        f"[{' '.join(a[i1:i2])}] -> [{' '.join(b[j1:j2])}]" for tag, i1, i2, j1, j2 in sm.get_opcodes() if tag != "equal"
    )


def cmd_worksheet(set_name: str) -> None:
    import csv

    EVAL_DIR.mkdir(parents=True, exist_ok=True)
    path = EVAL_DIR / f"worksheet-{set_name}.csv"
    with path.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=WORKSHEET_FIELDS)
        w.writeheader()
        for _, _, old_id, new_id in COMPARISONS:
            cid = comparison_id(old_id, new_id)
            label_path = LABELS_DIR / f"{cid}.json"
            if not label_path.exists():
                continue
            labels = json.loads(label_path.read_text())["labels"]
            units = {u["id"]: u for u in _load_units(cid)}
            for uid, lab in labels.items():
                u = units[uid]
                human = lab.get("reviewer", "draft") != "draft"
                w.writerow(
                    {
                        "comparison": cid,
                        "id": uid,
                        "type": u["type"],
                        "old_heading": u["old_heading"],
                        "new_heading": u["new_heading"],
                        "changes": _word_changes(u["old_text"], u["new_text"]),
                        "old_text": u["old_text"],
                        "new_text": u["new_text"],
                        "draft_kind": lab["kind"],
                        "draft_categories": ";".join(lab.get("categories") or []),
                        "draft_rationale": lab.get("rationale", ""),
                        "reviewer_kind": lab["kind"] if human else "",
                        "reviewer_categories": ";".join(lab.get("categories") or []) if human else "",
                        "reviewer_note": lab.get("rationale", "") if human else "",
                        "reviewer_name": lab["reviewer"] if human else "",
                    }
                )
    print(f"wrote {path}")


KINDS = {"substantive", "funding_amount", "routine_numbers", "renumbering", "editorial", "moved", "out_of_scope"}


def cmd_import(csv_path: str) -> None:
    import csv

    by_cid: dict[str, dict] = defaultdict(dict)
    with open(csv_path, newline="") as fh:
        for row in csv.DictReader(fh):
            name = (row.get("reviewer_name") or "").strip()
            kind = (row.get("reviewer_kind") or "").strip()
            if not name or not kind:
                continue
            if kind not in KINDS:
                raise SystemExit(f"{row['comparison']} {row['id']}: unknown kind {kind!r}")
            by_cid[row["comparison"]][row["id"]] = {
                "kind": kind,
                "categories": [c.strip() for c in (row.get("reviewer_categories") or "").split(";") if c.strip()],
                "rationale": (row.get("reviewer_note") or "").strip(),
                "reviewer": name,
            }
    for cid, rows in by_cid.items():
        dest = LABELS_DIR / f"{cid}.json"
        data = json.loads(dest.read_text())
        for uid, lab in rows.items():
            prior = data["labels"].get(uid, {})
            lab["same_passage"] = prior.get("same_passage")
            lab["draft"] = {k: prior[k] for k in ("kind", "categories", "rationale") if k in prior} if prior.get("reviewer", "draft") == "draft" else prior.get("draft")
            data["labels"][uid] = lab
        dest.write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n")
        print(f"{cid}: {len(rows)} adjudicated label(s) imported")


# Acceptance review: per comparison, every miss and false alarm plus these seeded samples, and whole sections read directly in the originals.
REVIEW_TRUE_FLAGS = 6
REVIEW_QUIET = 4
REVIEW_SECTIONS = 2
REVIEW_DIR = ROOT / "review"
REVIEW_FIELDS = ["group", "tool_result", "tool_flags", "demo_link"] + WORKSHEET_FIELDS + ["tool_verdict"]
FINDINGS_FIELDS = [
    "comparison", "section", "demo_link", "prior_year_text", "proposed_text", "why_it_matters", "tool_showed_it", "reviewer_name",
]


def _anchor_index(pair) -> list[tuple[str, str]]:
    out = []
    for sd in pair.sections:
        for sec in (sd.old, sd.new):
            if sec is not None:
                out.extend((_key(p.text), sd.anchor) for p in sec.paragraphs)
    return out


def _anchor_for(unit: dict, index: list[tuple[str, str]]) -> str:
    keys = [k for k, _ in index]
    for text in (unit["new_text"], unit["old_text"]):
        if not text:
            continue
        hit = process.extractOne(_key(text), keys, scorer=fuzz.ratio, score_cutoff=LOCATE_RATIO)
        if hit:
            return index[hit[2]][1]
    return ""


def _tool_result(loc: dict) -> tuple[str, str]:
    if "change" not in loc:
        return loc["status"], ""
    flags = sorted({f.label for f in loc["flags"] if f.tier >= REVIEW})
    return f"{loc['status']}: {loc['change'].label} (size alone: {loc['literal'].label if loc['literal'] else '-'})", "; ".join(flags)


def cmd_review() -> None:
    """Write review/review-packet.csv, review/findings.csv (blank template), and review/sections.md."""
    import csv

    repo, by_id = _entries()
    REVIEW_DIR.mkdir(exist_ok=True)
    rows: list[dict] = []
    section_lines = ["# Sections to read directly in the original reports", ""]
    for _, _, old_id, new_id in COMPARISONS:
        cid = comparison_id(old_id, new_id)
        labels = json.loads((LABELS_DIR / f"{cid}.json").read_text())["labels"]
        units = {u["id"]: u for u in _load_units(cid)}
        pair = compare_documents(load_document(repo, by_id[old_id]), load_document(repo, by_id[new_id]))
        view = _tool_view(pair)
        index = _anchor_index(pair)
        slug = f"{pair.new_doc.chamber}-{by_id[new_id].slug()}-fy{pair.old_doc.fiscal_year}-fy{pair.new_doc.fiscal_year}"
        rng = random.Random(f"{SAMPLE_SEED}-review-{cid}")
        groups: dict[str, list[tuple[str, dict]]] = defaultdict(list)
        for uid, lab in sorted(labels.items()):
            unit = units[uid]
            if lab.get("same_passage") is False and unit["new_text"]:
                unit = {**unit, "old_text": None}  # scored on the new side only, as in score
            loc = locate(unit, view)
            kind = lab["kind"]
            if kind == SUBSTANTIVE and not _surfaced(loc, baseline=False):
                groups["1 missed substantive"].append((uid, loc))
            elif kind in NOT_SUBSTANTIVE and _promoted(loc):
                groups["2 false alarm"].append((uid, loc))
            elif kind == SUBSTANTIVE and _promoted(loc):
                groups["3 flag, looks right"].append((uid, loc))
            elif kind in NOT_SUBSTANTIVE and loc["status"] == "edited" and not _promoted(loc) and loc["change"] < ChangeClass.SUBSTANTIVE:
                groups["4 quiet, looks right"].append((uid, loc))
        for name, cap in (("3 flag, looks right", REVIEW_TRUE_FLAGS), ("4 quiet, looks right", REVIEW_QUIET)):
            if len(groups[name]) > cap:
                groups[name] = rng.sample(groups[name], cap)
        for name in sorted(groups):
            for uid, loc in groups[name]:
                u, lab = units[uid], labels[uid]
                result, flags = _tool_result(loc)
                anchor = _anchor_for(u, index)
                rows.append(
                    {
                        "group": name,
                        "tool_result": result,
                        "tool_flags": flags,
                        "demo_link": f"../demo/{slug}/index.html" + (f"#{anchor}" if anchor else ""),
                        "comparison": cid,
                        "id": uid,
                        "type": u["type"],
                        "old_heading": u["old_heading"],
                        "new_heading": u["new_heading"],
                        "changes": _word_changes(u["old_text"], u["new_text"]),
                        "old_text": u["old_text"],
                        "new_text": u["new_text"],
                        "draft_kind": lab["kind"],
                        "draft_categories": ";".join(lab.get("categories") or []),
                        "draft_rationale": lab.get("rationale", ""),
                        "reviewer_kind": "",
                        "reviewer_categories": "",
                        "reviewer_note": "",
                        "reviewer_name": "",
                        "tool_verdict": "",
                    }
                )
        # Sections with real changes, chosen at random, so the reviewer can find what neither the tool nor the reference caught.
        changed = sorted(
            (sd for sd in pair.sections if sd.old is not None and sd.new is not None and sd.change >= ChangeClass.MINOR),
            key=lambda sd: sd.anchor,
        )
        section_lines += [f"## {by_id[new_id].subcommittee} FY{pair.old_doc.fiscal_year} → FY{pair.new_doc.fiscal_year}", ""]
        for sd in rng.sample(changed, min(REVIEW_SECTIONS, len(changed))):
            section_lines.append(
                f"- **{sd.new.heading}** ({' › '.join(sd.display_path[:-1])}): "
                f"[tool page](../demo/{slug}/index.html#{sd.anchor}); "
                f"originals: [FY{pair.old_doc.fiscal_year} PDF]({by_id[old_id].pdf_url}), [FY{pair.new_doc.fiscal_year} PDF]({by_id[new_id].pdf_url})"
            )
        section_lines.append("")
    with (REVIEW_DIR / "review-packet.csv").open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=REVIEW_FIELDS)
        w.writeheader()
        w.writerows(rows)
    findings = REVIEW_DIR / "findings.csv"
    if not findings.exists():
        with findings.open("w", newline="") as fh:
            csv.DictWriter(fh, fieldnames=FINDINGS_FIELDS).writeheader()
    (REVIEW_DIR / "sections.md").write_text("\n".join(section_lines))
    print(f"{len(rows)} rows -> {REVIEW_DIR / 'review-packet.csv'}; {dict(Counter(r['group'] for r in rows))}")


def _review_findings() -> tuple[int, int]:
    import csv

    path = REVIEW_DIR / "findings.csv"
    if not path.exists():
        return 0, 0
    with path.open(newline="") as fh:
        rows = [r for r in csv.DictReader(fh) if (r.get("reviewer_name") or "").strip()]
    return len(rows), sum(1 for r in rows if (r.get("tool_showed_it") or "").strip().lower() in ("no", "n", "false"))


# --- scoring ---------------------------------------------------------------

SUBSTANTIVE = "substantive"
# Labels a reader need not act on; a policy flag on one of these is a false alarm.
NOT_SUBSTANTIVE = {"editorial", "routine_numbers", "renumbering"}


@dataclass
class ToolView:
    edits: list[tuple[str, str, object]]  # (old key, new key, ParagraphDiff)
    added: dict[str, object]
    removed: dict[str, object]
    moves: list[tuple[str, str, object]]
    old_keys: list[str]
    new_keys: list[str]


def _tool_view(pair) -> ToolView:
    edits, moves = [], []
    added: dict[str, object] = {}
    removed: dict[str, object] = {}
    old_keys, new_keys = [], []
    for sd in pair.sections:
        if sd.old is not None:
            old_keys.extend(_key(p.text) for p in sd.old.paragraphs)
        if sd.new is not None:
            new_keys.extend(_key(p.text) for p in sd.new.paragraphs)
        if sd.change == ChangeClass.ADDED:
            for p in sd.new.paragraphs:
                added[_key(p.text)] = sd
        elif sd.change == ChangeClass.REMOVED:
            for p in sd.old.paragraphs:
                removed[_key(p.text)] = sd
        for pd in sd.paragraph_diffs:
            if pd.old is not None and pd.new is not None and pd.change != ChangeClass.UNCHANGED:
                edits.append((_key(pd.old.text), _key(pd.new.text), pd))
            elif pd.old is None and pd.new is not None:
                added[_key(pd.new.text)] = pd
            elif pd.new is None and pd.old is not None:
                removed[_key(pd.old.text)] = pd
    for m in pair.moves:
        moves.append((_key(m.diff.old.text), _key(m.diff.new.text), m))
    return ToolView(edits, added, removed, moves, old_keys, new_keys)


def _close(a: str, b: str) -> bool:
    return a == b or fuzz.ratio(a, b) >= LOCATE_RATIO


def _find_in(keys, target: str) -> str | None:
    if target in keys:
        return target
    hit = process.extractOne(target, list(keys), scorer=fuzz.ratio, score_cutoff=LOCATE_RATIO)
    return hit[0] if hit else None


def locate(unit: dict, view: ToolView) -> dict:
    """What the tool did with one reference unit."""
    ok = _key(unit["old_text"]) if unit["old_text"] else None
    nk = _key(unit["new_text"]) if unit["new_text"] else None
    for o, n, m in view.moves:
        if (ok is None or _close(o, ok)) and (nk is None or _close(n, nk)):
            return {"status": "moved", "change": m.diff.change, "literal": m.diff.literal_change, "flags": m.diff.flags}
    if ok and nk:
        for o, n, pd in view.edits:
            if _close(o, ok) and _close(n, nk):
                return {"status": "edited", "change": pd.change, "literal": pd.literal_change, "flags": pd.flags}
        # Paired with something else, or split into a drop and an add.
        other_new = next((n for o, n, _ in view.edits if _close(o, ok)), None)
        if other_new is not None:
            return {"status": "mispaired"}
        in_removed = _find_in(view.removed, ok) is not None
        in_added = _find_in(view.added, nk) is not None
        if in_removed and in_added:
            return {"status": "split"}
        if unit["type"] == "relocated":
            return {"status": "unchanged"}
        if _find_in(view.old_keys, ok) is None or _find_in(view.new_keys, nk) is None:
            return {"status": "missing"}
        return {"status": "unchanged"}
    if nk:
        if _find_in(view.added, nk) is not None:
            return {"status": "added"}
        hit = next((pd for _, n, pd in view.edits if _close(n, nk)), None)
        if hit is not None:
            # The tool paired a paragraph the reference splitter left unpaired; either side may be right.
            return {"status": "absorbed", "change": hit.change, "literal": hit.literal_change, "flags": hit.flags}
        return {"status": "missing" if _find_in(view.new_keys, nk) is None else "unchanged"}
    if _find_in(view.removed, ok) is not None:
        return {"status": "removed"}
    hit = next((pd for o, _, pd in view.edits if _close(o, ok)), None)
    if hit is not None:
        return {"status": "absorbed", "change": hit.change, "literal": hit.literal_change, "flags": hit.flags}
    return {"status": "missing" if _find_in(view.old_keys, ok) is None else "unchanged"}


def _surfaced(loc: dict, baseline: bool) -> bool:
    """Would a reader scanning the ranked page be pointed at this unit?"""
    if loc["status"] in ("added", "removed", "split"):
        return True
    if loc["status"] not in ("edited", "moved", "absorbed"):
        return False
    if baseline:
        return loc["literal"] is not None and loc["literal"] >= ChangeClass.SUBSTANTIVE
    return loc["change"] >= ChangeClass.SUBSTANTIVE


def _promoted(loc: dict) -> bool:
    return loc["status"] in ("edited", "moved") and any(f.tier >= REVIEW for f in loc["flags"])


def cmd_score(as_json: bool, remap: dict[str, str] | None = None) -> None:
    repo, by_id = _entries()
    report: dict = {"comparisons": {}}
    totals: Counter = Counter()
    examples: dict[str, list] = defaultdict(list)
    for _, sub, old_id, new_id in COMPARISONS:
        cid = comparison_id(old_id, new_id)
        label_path = LABELS_DIR / f"{cid}.json"
        if not label_path.exists():
            print(f"{cid}: no labels yet", file=sys.stderr)
            continue
        labels = json.loads(label_path.read_text())["labels"]
        units = {u["id"]: u for u in _load_units(cid)}
        pair = compare_documents(load_document(repo, by_id[old_id]), load_document(repo, by_id[new_id]))
        view = _tool_view(pair)
        c: Counter = Counter()
        for uid, lab in labels.items():
            unit = units[uid]
            loc = locate(unit, view)
            kind = (remap or {}).get(lab["kind"], lab["kind"])
            small = unit["type"] == "edited" and (unit["changed_words"] or 0) <= SMALL_EDIT_WORDS
            c["labeled"] += 1
            c["human_adjudicated"] += lab.get("reviewer", "draft") != "draft"
            c[f"label:{kind}"] += 1
            c[f"status:{loc['status']}"] += 1
            if kind == "out_of_scope":
                continue
            if lab.get("same_passage") is False:
                # The reference splitter paired lookalike boilerplate; judge the tool only on whether the new side surfaced.
                c["reference_mispair"] += 1
                loc = locate({**unit, "old_text": None}, view) if unit["new_text"] else loc
            elif loc["status"] in ("mispaired", "split", "absorbed"):
                c["alignment_disagreement"] += 1
                c[f"alignment_disagreement:{loc['status']}"] += 1
                examples["alignment_disagreement"].append((cid, uid, loc["status"], kind))
            if unit["type"] == "relocated" and kind == "moved" and loc["status"] == "unchanged":
                c["move_not_shown"] += 1
            if kind == SUBSTANTIVE:
                c["substantive"] += 1
                c["substantive_small"] += small
                for mode, base in (("current", False), ("baseline", True)):
                    if not _surfaced(loc, base):
                        c[f"missed:{mode}"] += 1
                        c[f"missed_small:{mode}"] += small
                        if mode == "current":
                            examples["missed"].append((cid, uid, loc["status"], lab.get("categories"), unit["changed_words"]))
                if loc["status"] == "missing":
                    c["missed_segmentation"] += 1
            if kind == "funding_amount":
                c["funding_amount"] += 1
                c["funding_amount_promoted"] += _promoted(loc)
            if kind in NOT_SUBSTANTIVE and loc["status"] in ("edited", "moved"):
                c["not_substantive_located"] += 1
                if _promoted(loc):
                    c["false_alarm:policy_flag"] += 1
                    examples["false_alarm"].append(
                        (cid, uid, kind, sorted({f.category for f in loc["flags"] if f.tier >= REVIEW}))
                    )
                if loc["literal"] is not None and loc["literal"] >= ChangeClass.SUBSTANTIVE:
                    c["false_alarm:size"] += 1
            if _promoted(loc):
                c["promoted"] += 1
                c[f"promoted_label:{kind}"] += 1
        report["comparisons"][cid] = dict(c)
        totals.update(c)
    report["totals"] = dict(totals)
    report["examples"] = {k: v for k, v in examples.items()}
    if as_json:
        print(json.dumps(report, indent=2, default=str))
        return
    for cid, c in list(report["comparisons"].items()) + [("TOTAL", report["totals"])]:
        _print_summary(cid, Counter(c))
    found, not_shown = _review_findings()
    if found:
        print(f"\nreviewer findings from reading originals (review/findings.csv): {found} recorded, {not_shown} not shown by the tool")


def _print_summary(cid: str, c: Counter) -> None:
    sub = c["substantive"] or 1
    print(f"\n== {cid}")
    print(f"  labeled units: {c['labeled']} ({c['human_adjudicated']} human-adjudicated, {c['labeled'] - c['human_adjudicated']} draft)  " + ", ".join(f"{k[6:]}={v}" for k, v in sorted(c.items()) if k.startswith("label:")))
    print("  tool status:   " + ", ".join(f"{k[7:]}={v}" for k, v in sorted(c.items()) if k.startswith("status:")))
    print(
        f"  missed substantive: current {c['missed:current']}/{c['substantive']} ({100 * c['missed:current'] / sub:.1f}%), "
        f"size-only baseline {c['missed:baseline']}/{c['substantive']} ({100 * c['missed:baseline'] / sub:.1f}%)"
    )
    print(
        f"    of which small edits (<= {SMALL_EDIT_WORDS} words): current {c['missed_small:current']}/{c['substantive_small']}, "
        f"baseline {c['missed_small:baseline']}/{c['substantive_small']}; lost in segmentation: {c['missed_segmentation']}"
    )
    promoted = c["promoted"] or 1
    print(
        f"  false alarms: policy flags on non-substantive edits {c['false_alarm:policy_flag']}/{c['not_substantive_located']} "
        f"(flag precision {100 * c['promoted_label:substantive'] / promoted:.1f}% of {c['promoted']} promoted); "
        f"size-based substantive on non-substantive edits {c['false_alarm:size']}"
    )
    print(
        f"  alignment disagreements with the reference pairing: {c['alignment_disagreement']} "
        f"(mispaired {c['alignment_disagreement:mispaired']}, split {c['alignment_disagreement:split']}, absorbed {c['alignment_disagreement:absorbed']}); "
        f"moves shown as unchanged: {c['move_not_shown']}; reference pairings judged not the same passage: {c['reference_mispair']}"
    )
    print(f"  narrative dollar-only changes: {c['funding_amount']} labeled, {c['funding_amount_promoted']} promoted by a flag")


def main(argv: list[str]) -> int:
    global COMPARISONS
    if not argv:
        print(__doc__)
        return 2
    if "--set" in argv:
        k = argv.index("--set")
        COMPARISONS = SETS[argv[k + 1]]
        argv = argv[:k] + argv[k + 2 :]
    cmd = argv[0]
    if cmd == "extract":
        cmd_extract()
    elif cmd == "sample":
        cmd_sample()
    elif cmd == "merge":
        cmd_merge()
    elif cmd == "review":
        cmd_review()
    elif cmd == "worksheet":
        cmd_worksheet("holdout" if COMPARISONS is SETS["holdout"] else "demo")
    elif cmd == "import":
        cmd_import(argv[1])
    elif cmd == "score":
        remap = dict(a.split("=", 1) for a in (argv[k + 1] for k, x in enumerate(argv) if x == "--as"))
        cmd_score("--json" in argv, remap)
    else:
        print(__doc__)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
