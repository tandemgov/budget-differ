"""Record-linkage evaluation for cross-year section alignment.

Turns the aligner's decisions into a measurable dataset instead of spot-checked pages:

  uv run python scripts/linkage_eval.py emit [chamber] [subcommittee]
      Run every adjacent-FY pair, trace all linkage decisions (accepted matches and
      near-miss rejections from every pass, plus rename-promotion candidates), and
      write .linkage-eval/candidates.jsonl with text excerpts and auto-labels for
      the unambiguous ends of the similarity range.
  uv run python scripts/linkage_eval.py sample [N]
      Stratified sample of unlabeled, non-auto-labelable candidates (per pass and
      score band, borderline first) into .linkage-eval/to_label.json for adjudication.
      Adjudicated labels accumulate in tests/linkage_labels.json, matched by content.
  uv run python scripts/linkage_eval.py score
      Precision/recall per pass against auto + adjudicated labels, plus threshold
      sweeps for the tunable passes.

Label semantics: "same" means the two sections are the same recurring provision or section slot (continuation, rename, or renumbering — the thing a reader wants diffed year over year); "different" means pairing them would diff unrelated language.
"""

from __future__ import annotations

import hashlib
import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from rapidfuzz import fuzz

from budget_differ import align as align_mod
from budget_differ.align import align_sections, section_similarity
from budget_differ.compare import RENAME_PROMOTE, _best_matches, _promote_bar, load_document
from budget_differ.config import approps_repo
from budget_differ.corpus import available_reports, discover_pairs
from budget_differ.models import Section

EVAL_DIR = Path(__file__).resolve().parents[1] / ".linkage-eval"
CANDIDATES = EVAL_DIR / "candidates.jsonl"
TO_LABEL = EVAL_DIR / "to_label.json"
LABELS = Path(__file__).resolve().parents[1] / "tests" / "linkage_labels.json"
# Labels from before content keying whose section texts were never saved; kept for their notes, not scored.
UNRECOVERABLE = Path(__file__).resolve().parents[1] / "tests" / "linkage_labels_unrecoverable.json"
# A label follows its sections by content: same pair slug and headings, and both text excerpts at least this similar.
LABEL_TEXT_MATCH = 90.0
EVIDENCE_CHARS = 300

TEXT_EXCERPT = 700
# Auto-label bounds on full-body token_set_ratio: above the ceiling two sections are unambiguously the same provision; below the floor unambiguously different. The band between is what adjudication is for.
AUTO_SAME = 97.0
AUTO_DIFF = 25.0

PASS_THRESHOLDS = {
    "fuzzy_heading": align_mod.FUZZY_ACCEPT,
    "content_parent": align_mod.CONTENT_ACCEPT,
    "content_title": align_mod.CONTENT_ACCEPT,
    "rename": RENAME_PROMOTE,
}


def _text(sec: Section) -> str:
    return " ".join(p.text for p in sec.paragraphs)


def _cand_id(slug: str, old: Section, new: Section) -> str:
    key = json.dumps([slug, list(old.path), old.order, list(new.path), new.order])
    return hashlib.sha1(key.encode()).hexdigest()[:16]


def _auto_label(old: Section, new: Section) -> str | None:
    ta, tb = _text(old)[:4000], _text(new)[:4000]
    if not ta.strip() and not tb.strip():
        # Table-only sections carry no text to compare; an identical path means the same slot, anything else is unjudgeable here.
        return "same" if old.path == new.path else None
    sim = fuzz.token_set_ratio(ta, tb)
    if sim >= AUTO_SAME:
        return "same"
    # Low text similarity proves nothing for same-path pairs — recurring slots get rewritten wholesale (COMMITTEE RECOMMENDATION blocks, renumber-guarded GPs are separate). Only differing-path pairs with substantial dissimilar text are safely different.
    if sim <= AUTO_DIFF and old.path != new.path and len(ta) > 120 and len(tb) > 120:
        return "different"
    return None


def _record(slug: str, entry: dict) -> dict:
    old, new = entry["old"], entry["new"]
    return {
        "id": _cand_id(slug, old, new),
        "slug": slug,
        "pass": entry["pass"],
        "score": round(entry["score"], 1),
        "accepted": entry["accepted"],
        "old_path": list(old.path),
        "new_path": list(new.path),
        "old_heading": old.heading,
        "new_heading": new.heading,
        "old_text": _text(old)[:TEXT_EXCERPT],
        "new_text": _text(new)[:TEXT_EXCERPT],
        "auto": _auto_label(old, new),
    }


def _rename_candidates(removed: list[Section], added: list[Section]) -> list[dict]:
    """Mirror compare._promote_renames decisions, including the near-miss band."""
    best = _best_matches(removed, added)
    out = []
    for old_sec in removed:
        entry = best.get(id(old_sec))
        if entry is None:
            continue
        new_sec, score = entry
        if score < RENAME_PROMOTE - align_mod.TRACE_MARGIN:
            continue
        back = best.get(id(new_sec))
        mutual = back is not None and back[0] is old_sec
        op, np_ = old_sec.path[:-1], new_sec.path[:-1]
        shorter = min(len(op), len(np_))
        parent_ok = op == np_ or op[:shorter] == np_[:shorter]
        out.append(
            {
                "pass": "rename",
                "score": score,
                "accepted": bool(
                    mutual and parent_ok and score >= _promote_bar(old_sec, new_sec)
                ),
                "old": old_sec,
                "new": new_sec,
            }
        )
    return out


def emit(argv: list[str]) -> None:
    repo = approps_repo()
    reports = available_reports(repo)
    chamber = argv[0] if argv else None
    subcommittee = argv[1] if len(argv) > 1 else None
    pairs = discover_pairs(reports, chamber, subcommittee)
    EVAL_DIR.mkdir(exist_ok=True)
    n = 0
    with CANDIDATES.open("w") as fh:
        for pair in pairs:
            slug = pair.slug()
            old_doc = load_document(repo, pair.old)
            new_doc = load_document(repo, pair.new)
            trace: list[dict] = []
            _, removed, added = align_sections(old_doc, new_doc, trace=trace)
            trace.extend(_rename_candidates(removed, added))
            for entry in trace:
                fh.write(json.dumps(_record(slug, entry)) + "\n")
                n += 1
            print(f"{slug}: {len(trace)} decisions")
    print(f"wrote {n} candidates -> {CANDIDATES}")


def _load_candidates() -> list[dict]:
    return [json.loads(line) for line in CANDIDATES.read_text().splitlines()]


def _load_labels() -> list[dict]:
    if not LABELS.exists():
        return []
    return json.loads(LABELS.read_text())


def _norm_heading(h: str) -> str:
    return " ".join(h.upper().split())


def _evidence(r: dict) -> dict:
    return {
        "slug": r["slug"],
        "old_heading": r["old_heading"],
        "new_heading": r["new_heading"],
        "old_text": r["old_text"][:EVIDENCE_CHARS],
        "new_text": r["new_text"][:EVIDENCE_CHARS],
    }


def _match_labels(rows: list[dict], labels: list[dict]) -> dict[int, dict]:
    """Row index → label, matched by content so segmentation changes that shift paths or order do not orphan adjudications."""
    by_key: dict[tuple[str, str, str], list[int]] = defaultdict(list)
    for i, r in enumerate(rows):
        by_key[(r["slug"], _norm_heading(r["old_heading"]), _norm_heading(r["new_heading"]))].append(i)
    out: dict[int, dict] = {}
    for lab in labels:
        ev = lab["evidence"]
        for i in by_key.get((ev["slug"], _norm_heading(ev["old_heading"]), _norm_heading(ev["new_heading"])), []):
            r = rows[i]
            if (
                fuzz.ratio(r["old_text"][:EVIDENCE_CHARS], ev["old_text"]) >= LABEL_TEXT_MATCH
                and fuzz.ratio(r["new_text"][:EVIDENCE_CHARS], ev["new_text"]) >= LABEL_TEXT_MATCH
            ):
                out[i] = lab
    return out


def migrate(argv: list[str]) -> None:
    """One-time: attach content evidence to id-keyed labels from any candidate file that still has their texts."""
    labels = _load_labels()
    sources: dict[str, dict] = {}
    for path in [TO_LABEL, *map(Path, argv)]:
        if path.exists():
            data = json.loads(path.read_text()) if path.suffix == ".json" else [json.loads(x) for x in path.read_text().splitlines()]
            sources.update({r["id"]: r for r in data})
    if CANDIDATES.exists():
        for r in _load_candidates():
            sources.setdefault(r["id"], r)
    kept, lost = [], []
    for lab in labels:
        if "evidence" in lab:
            kept.append(lab)
        elif lab["id"] in sources:
            kept.append({**lab, "evidence": _evidence(sources[lab["id"]])})
        else:
            lost.append(lab)
    LABELS.write_text(json.dumps(kept, indent=1, ensure_ascii=False) + "\n")
    if lost:
        prior = json.loads(UNRECOVERABLE.read_text()) if UNRECOVERABLE.exists() else []
        UNRECOVERABLE.write_text(json.dumps(prior + lost, indent=1, ensure_ascii=False) + "\n")
    print(f"{len(kept)} labels carry evidence; {len(lost)} unrecoverable -> {UNRECOVERABLE.name}")


def sample(argv: list[str]) -> None:
    target = int(argv[0]) if argv else 200
    candidates = _load_candidates()
    matched = _match_labels(candidates, _load_labels())
    rows = [r for i, r in enumerate(candidates) if r["auto"] is None and i not in matched]
    # Borderline-first stratification: distance from the pass threshold defines the band; every (pass, band) group contributes round-robin so no pass dominates.
    groups: dict[tuple[str, int], list[dict]] = defaultdict(list)
    for r in rows:
        ref = PASS_THRESHOLDS.get(r["pass"])
        band = 99 if ref is None else int(abs(r["score"] - ref) // 5)
        groups[(r["pass"], band)].append(r)
    for g in groups.values():
        g.sort(key=lambda r: r["id"])  # deterministic
    ordered_groups = sorted(groups.items(), key=lambda kv: (kv[0][1], kv[0][0]))
    picked: list[dict] = []
    while len(picked) < target and any(g for _, g in ordered_groups):
        for _, g in ordered_groups:
            if g and len(picked) < target:
                picked.append(g.pop(0))
    TO_LABEL.write_text(json.dumps(picked, indent=1))
    print(f"{len(rows)} unlabeled candidates; sampled {len(picked)} -> {TO_LABEL}")


def score(argv: list[str]) -> None:
    rows = _load_candidates()
    labels = _load_labels()
    judged = _match_labels(rows, labels)

    labeled = [(r, judged[i]["label"] if i in judged else r["auto"]) for i, r in enumerate(rows)]
    labeled = [(r, lb) for r, lb in labeled if lb in ("same", "different")]
    used = {id(lab) for lab in judged.values()}
    print(f"{len(rows)} candidates, {len(labeled)} labeled "
          f"({len(judged)} rows carry an adjudicated label; {len(used)} of {len(labels)} adjudicated labels matched a current candidate)")
    adjudicated = [(rows[i], lab["label"]) for i, lab in judged.items() if lab["label"] in ("same", "different")]

    def pr(subset: list[tuple[dict, str]]) -> tuple[int, int, float, float]:
        acc = [(r, lb) for r, lb in subset if r["accepted"]]
        tp = sum(1 for _, lb in acc if lb == "same")
        fp = len(acc) - tp
        pos = sum(1 for _, lb in subset if lb == "same")
        prec = tp / len(acc) if acc else float("nan")
        rec = tp / pos if pos else float("nan")
        return tp, fp, prec, rec

    by_pass: dict[str, list[tuple[dict, str]]] = defaultdict(list)
    for r, lb in labeled:
        by_pass[r["pass"]].append((r, lb))
    print(f"\n{'pass':16} {'n':>5} {'acc':>5} {'tp':>5} {'fp':>4} {'prec':>7} {'rec*':>7}")
    for pass_name in sorted(by_pass):
        subset = by_pass[pass_name]
        tp, fp, prec, rec = pr(subset)
        acc_n = sum(1 for r, _ in subset if r["accepted"])
        print(f"{pass_name:16} {len(subset):5} {acc_n:5} {tp:5} {fp:4} {prec:7.1%} {rec:7.1%}")
    tp, fp, prec, rec = pr(labeled)
    print(f"{'OVERALL':16} {len(labeled):5} {tp + fp:5} {tp:5} {fp:4} {prec:7.1%} {rec:7.1%}")
    print("* recall over labeled candidates only (blocking misses are invisible here)")
    # Auto-labels cover only the unambiguous ends; adjudicated rows are the informative subset.
    tp, fp, prec, rec = pr(adjudicated)
    print(f"{'ADJUDICATED ONLY':16} {len(adjudicated):5} {tp + fp:5} {tp:5} {fp:4} {prec:7.1%} {rec:7.1%}")
    for pass_name in sorted({r["pass"] for r, _ in adjudicated}):
        subset = [(r, lb) for r, lb in adjudicated if r["pass"] == pass_name]
        tp, fp, prec, rec = pr(subset)
        print(f"  {pass_name:14} {len(subset):5} {tp + fp:5} {tp:5} {fp:4} {prec:7.1%} {rec:7.1%}")

    for pass_name in ("fuzzy_heading", "content_parent", "content_title", "rename"):
        subset = by_pass.get(pass_name, [])
        if len(subset) < 10:
            continue
        ref = PASS_THRESHOLDS[pass_name]
        print(f"\nthreshold sweep — {pass_name} (current {ref}):")
        for t in range(int(ref) - 15, int(ref) + 16, 5):
            acc = [(r, lb) for r, lb in subset if r["score"] >= t]
            tp = sum(1 for _, lb in acc if lb == "same")
            pos = sum(1 for _, lb in subset if lb == "same")
            prec = tp / len(acc) if acc else float("nan")
            rec = tp / pos if pos else float("nan")
            marker = " <- current" if t == int(ref) else ""
            print(f"  t={t:3}  accepted={len(acc):4}  prec={prec:6.1%}  rec={rec:6.1%}{marker}")


def main() -> int:
    commands = {"emit": emit, "sample": sample, "score": score, "migrate": migrate}
    if len(sys.argv) < 2 or sys.argv[1] not in commands:
        print(__doc__)
        return 2
    commands[sys.argv[1]](sys.argv[2:])
    return 0


if __name__ == "__main__":
    sys.exit(main())
