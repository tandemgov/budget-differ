"""Audit the section tree the segmenter builds, corpus-wide.

Two kinds of checks:

- Truth: an account whose title maps to one USASpending agency must sit under that agency; generic titles are skipped.
- Structure: label-free tree invariants, described in docs/methodology.md.

Usage:
    uv run python scripts/hierarchy_audit.py                      # whole corpus
    uv run python scripts/hierarchy_audit.py --demo               # the six demonstration reports
    uv run python scripts/hierarchy_audit.py --report CRPT-119hrpt178 [--report ...]
    uv run python scripts/hierarchy_audit.py --json out.json      # also write per-report metrics
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor

from budget_differ.compare import load_document
from budget_differ.config import approps_repo
from budget_differ.corpus import _norm, available_reports, load_agency_lexicon
from budget_differ.segment.headings import AGENCY_SUPPLEMENT, TOPICAL

# USASpending records the agency's *current* name; older reports print the name in force at the time. Credit historical names as correct parentage.
AGENCY_ALIASES: dict[str, set[str]] = {
    "U S AGENCY FOR GLOBAL MEDIA": {"BROADCASTING BOARD OF GOVERNORS"},
}

# Accounts whose managing agency (execution) legitimately differs from their appropriations-report placement: State/Foreign Ops appropriates IMET and FMF under Department of State even though Defense executes them. Structure under State is correct parsing, not misparenting.
STRUCTURAL_EXCEPTIONS = {
    "INTERNATIONAL MILITARY EDUCATION AND TRAINING",
    "FOREIGN MILITARY FINANCING PROGRAM",
    # NOAA's account; USASpending's title normalization collides it with an EPA account, so the "unambiguous" truth names the wrong agency.
    "OPERATIONS RESEARCH AND FACILITIES",
}

# Legislative agencies USASpending omits; kept apart from the segmenter's list so the audit does not grade the parser against itself.
AUDIT_LEGISLATIVE_AGENCIES = frozenset(
    {
        "SENATE",
        "HOUSE OF REPRESENTATIVES",
        "JOINT ITEMS",
        "UNITED STATES CAPITOL POLICE",
        "CAPITOL POLICE",
        "OFFICE OF COMPLIANCE",
        "OFFICE OF CONGRESSIONAL WORKPLACE RIGHTS",
        "CONGRESSIONAL BUDGET OFFICE",
        "ARCHITECT OF THE CAPITOL",
        "LIBRARY OF CONGRESS",
        "GOVERNMENT PRINTING OFFICE",
        "GOVERNMENT PUBLISHING OFFICE",
        "GOVERNMENT ACCOUNTABILITY OFFICE",
        "OPEN WORLD LEADERSHIP CENTER",
        "CONGRESSIONAL OFFICE FOR INTERNATIONAL LEADERSHIP",
        "JOHN C STENNIS CENTER FOR PUBLIC SERVICE TRAINING AND DEVELOPMENT",
    }
)

GROUPINGS = frozenset({"FUNDS APPROPRIATED TO THE PRESIDENT"})

_ANNOTATION = re.compile(r"^(INCLUDING|EXCLUDING)\b")
_SEC = re.compile(r"^SEC \d")

DEMO_REPORTS = [
    "CRPT-118hrpt555", "CRPT-119hrpt178", "CRPT-119hrpt666",
    "CRPT-118hrpt580", "CRPT-119hrpt213", "CRPT-119hrpt667",
]

STRUCTURE_METRICS = ["nested_agency", "annotation_section", "duplicate_path", "resumed_parent"]


def account_truth(repo) -> dict[str, str]:
    """normalized account title -> normalized managing agency (unambiguous only)."""
    data = json.loads((repo / "data/reference/federal_accounts.json").read_text())
    accounts = next(v for k, v in data.items() if k != "metadata")
    seen: dict[str, set[str]] = {}
    for a in accounts:
        agency = a.get("managing_agency")
        title = a.get("account_title") or ""
        if not agency or not title:
            continue
        keys = {_norm(title)}
        # Titles often end ", <Agency>" — index the bare form too, and use the first comma segment to catch generic names ("Buildings and Facilities, <anything>") that recur across agencies: any collision disqualifies.
        stripped = re.sub(r",\s*" + re.escape(agency) + r"\s*$", "", title, flags=re.I)
        keys.add(_norm(stripped))
        keys.add(_norm(title.split(",")[0]))
        for k in keys:
            if k:
                seen.setdefault(k, set()).add(_norm(agency))
    return {k: next(iter(v)) for k, v in seen.items() if len(v) == 1}


def _is_split_provision(path: tuple[str, ...]) -> bool:
    # General provisions are keyed (title, SEC n) on purpose (builder._split_general_provisions), so they sit outside the account tree by design.
    return len(path) == 2 and bool(_SEC.match(path[1]))


def structure_findings(paths: list[tuple[str, ...]], agencies: frozenset[str]) -> dict[str, list[str]]:
    """Label-free structural violations in one report's ordered section paths."""
    out: dict[str, list[str]] = {m: [] for m in STRUCTURE_METRICS}
    tree = [p for p in paths if not _is_split_provision(p)]
    for p in tree:
        named = [c for c in p if c in agencies]
        if len(named) > 1:
            out["nested_agency"].append(" > ".join(p))
        if _ANNOTATION.match(p[-1]):
            out["annotation_section"].append(" > ".join(p))
    for p, n in Counter(tree).items():
        if n > 1:
            out["duplicate_path"].extend([" > ".join(p)] * (n - 1))
    last_seen: dict[tuple[str, ...], int] = {}
    reported: set[tuple[str, ...]] = set()
    for i, p in enumerate(tree):
        parent = p[:-1]
        if not parent:
            continue
        j = last_seen.get(parent)
        if j is not None and parent not in reported:
            if any(q[: len(parent)] != parent for q in tree[j + 1 : i]):
                out["resumed_parent"].append(" > ".join(parent))
                reported.add(parent)
        last_seen[parent] = i
    return out


def _audit_one(args: tuple[str, str]) -> dict:
    repo_s, package_id = args
    from pathlib import Path

    repo = Path(repo_s)
    entry = next(e for e in available_reports(repo) if e.package_id == package_id)
    doc = load_document(repo, entry)
    agencies = load_agency_lexicon(repo) | AGENCY_SUPPLEMENT | AUDIT_LEGISLATIVE_AGENCIES
    truth = account_truth(repo)
    checked = mismatched = orphaned = 0
    examples: list[str] = []
    orphans: list[str] = []
    for s in doc.sections:
        if s.level > 3 or s.path[-1] not in truth or s.path[-1] in STRUCTURAL_EXCEPTIONS:
            continue
        expected = truth[s.path[-1]]
        checked += 1
        names = {expected} | AGENCY_ALIASES.get(expected, set())
        if any(n in p for n in names for p in s.path[:-1]):
            continue
        # Groupings such as FUNDS APPROPRIATED TO THE PRESIDENT legitimately hold other agencies' accounts, so only a named agency counts as a wrong parent.
        wrong = [p for p in s.path[:-1] if p in agencies and p not in GROUPINGS]
        if wrong:
            mismatched += 1
            examples.append(f"{s.path[-1][:45]} under {wrong[-1][:40]!r}, expected {expected[:40]!r}")
        else:
            orphaned += 1
            orphans.append(f"{expected} :: {' > '.join(s.path)}")
    paths = [s.path for s in doc.sections]
    return {
        "package_id": package_id,
        "chamber": entry.chamber,
        "subcommittee": entry.subcommittee,
        "fiscal_year": entry.fiscal_year,
        "sections": len(paths),
        "paths": [list(p) for p in paths],
        "truth": {"checked": checked, "misparented": mismatched, "orphaned": orphaned, "examples": examples, "orphans": orphans},
        "structure": structure_findings(paths, agencies),
    }


def parent_drift(prev: dict, cur: dict) -> list[str]:
    """Headings unique in both adjacent reports whose parents differ; the title tier is ignored because reports renumber titles."""

    def unique_parents(report: dict) -> dict[str, tuple[str, ...]]:
        tree = [tuple(p) for p in report["paths"] if not _is_split_provision(tuple(p))]
        counts = Counter(p[-1] for p in tree)
        return {p[-1]: p[1:-1] for p in tree if counts[p[-1]] == 1 and p[-1] not in TOPICAL}

    a, b = unique_parents(prev), unique_parents(cur)
    return [
        f"{name}: {' > '.join(a[name]) or '(root)'} -> {' > '.join(b[name]) or '(root)'}"
        for name in sorted(a.keys() & b.keys())
        if a[name] != b[name]
    ]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--demo", action="store_true", help="only the six demonstration reports")
    ap.add_argument("--report", action="append", default=[], help="package id (repeatable)")
    ap.add_argument("--json", help="write per-report metrics here")
    ap.add_argument("--examples", type=int, default=8)
    args = ap.parse_args()

    repo = approps_repo()
    wanted = set(args.report) | (set(DEMO_REPORTS) if args.demo else set())
    entries = [e for e in available_reports(repo) if not wanted or e.package_id in wanted]
    with ProcessPoolExecutor() as pool:
        results = list(pool.map(_audit_one, [(str(repo), e.package_id) for e in entries]))
    results.sort(key=lambda r: (r["chamber"], r["subcommittee"], r["fiscal_year"]))

    # Adjacent fiscal years of one chamber/subcommittee, as loaded.
    by_group: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for r in results:
        by_group[(r["chamber"], r["subcommittee"])].append(r)
    drift_total = 0
    drift_examples: list[str] = []
    for group in by_group.values():
        for prev, cur in zip(group, group[1:]):
            found = parent_drift(prev, cur)
            cur["parent_drift"] = found
            drift_total += len(found)
            drift_examples.extend(f"{prev['package_id']}->{cur['package_id']} {f}" for f in found)

    checked = sum(r["truth"]["checked"] for r in results)
    mis = sum(r["truth"]["misparented"] for r in results)
    orph = sum(r["truth"]["orphaned"] for r in results)
    sections = sum(r["sections"] for r in results)
    print(f"reports: {len(results)}   sections: {sections}")
    print(f"\ntruth (USASpending account -> agency): {checked} account sections checked")
    print(f"  misparented: {mis} ({mis / max(checked, 1):.1%})   no agency ancestor: {orph} ({orph / max(checked, 1):.1%})")

    print("\nstructure (label-free):")
    for m in STRUCTURE_METRICS:
        total = sum(len(r["structure"][m]) for r in results)
        worst = Counter({r["package_id"]: len(r["structure"][m]) for r in results if r["structure"][m]})
        print(f"  {m:20} {total:5}   worst: {worst.most_common(4)}")
    print(f"  {'parent_drift':20} {drift_total:5}   (adjacent-year pairs)")

    if args.examples:
        for m in STRUCTURE_METRICS:
            ex = [f"{r['package_id']}: {x}" for r in results for x in r["structure"][m]]
            if ex:
                print(f"\n{m} examples:")
                for x in ex[: args.examples]:
                    print("  ", x[:160])
        if drift_examples:
            print("\nparent_drift examples:")
            for x in drift_examples[: args.examples]:
                print("  ", x[:160])
        truth_ex = [f"{r['package_id']}: {x}" for r in results for x in r["truth"]["examples"]]
        if truth_ex:
            print("\nmisparented examples:")
            for x in truth_ex[: args.examples]:
                print("  ", x)

    if args.json:
        with open(args.json, "w") as fh:
            json.dump([{k: v for k, v in r.items() if k != "paths"} for r in results], fh, indent=1)
    return 0


if __name__ == "__main__":
    sys.exit(main())
