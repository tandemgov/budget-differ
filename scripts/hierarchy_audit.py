"""Audit section parentage against USASpending ground truth.

For every account-level section whose heading exactly matches a federal account title with an unambiguous managing agency, check that the section's assigned agency ancestor is that agency. Reports the corpus-wide misparenting rate — the systematic version of spotting a Postal Service account filed under SBA by hand.

Usage: uv run python scripts/hierarchy_audit.py
"""

from __future__ import annotations

import json
import re
import sys
from collections import Counter

from budget_differ.compare import load_document
from budget_differ.config import approps_repo
from budget_differ.corpus import _norm, available_reports

# USASpending records the agency's *current* name; older reports print the name in force at the time. Credit historical names as correct parentage.
AGENCY_ALIASES: dict[str, set[str]] = {
    "U S AGENCY FOR GLOBAL MEDIA": {"BROADCASTING BOARD OF GOVERNORS"},
}

# Accounts whose managing agency (execution) legitimately differs from their appropriations-report placement: State/Foreign Ops appropriates IMET and FMF under Department of State even though Defense executes them. Structure under State is correct parsing, not misparenting.
STRUCTURAL_EXCEPTIONS = {
    "INTERNATIONAL MILITARY EDUCATION AND TRAINING",
    "FOREIGN MILITARY FINANCING PROGRAM",
}


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


def main() -> int:
    repo = approps_repo()
    truth = account_truth(repo)
    print(f"ground truth: {len(truth)} unambiguous account titles")

    from budget_differ.corpus import load_agency_lexicon

    known_agencies = load_agency_lexicon(repo)
    checked = mismatched = orphaned = 0
    offenders: Counter[str] = Counter()
    examples: list[str] = []
    for entry in available_reports(repo):
        doc = load_document(repo, entry)
        for s in doc.sections:
            if s.level > 3 or s.path[-1] not in truth:
                continue
            if s.path[-1] in STRUCTURAL_EXCEPTIONS:
                continue
            expected = truth[s.path[-1]]
            checked += 1
            ancestors = s.path[:-1]
            names = {expected} | AGENCY_ALIASES.get(expected, set())
            if any(n in p for n in names for p in ancestors):
                continue  # correctly parented (agency named in lineage)
            wrong = [p for p in ancestors if p in known_agencies]
            if wrong:
                mismatched += 1
                offenders[entry.package_id] += 1
                if len(examples) < 12:
                    examples.append(
                        f"{entry.package_id}: {s.path[-1][:45]} under "
                        f"{wrong[-1][:40]!r}, expected {expected[:40]!r}"
                    )
            else:
                orphaned += 1

    ok = checked - mismatched - orphaned
    print(f"account sections checked against truth: {checked}")
    print(f"  correctly parented: {ok} ({ok / max(checked,1):.1%})")
    print(f"  MISPARENTED:        {mismatched} ({mismatched / max(checked,1):.1%})")
    print(f"  no agency ancestor: {orphaned} ({orphaned / max(checked,1):.1%})")
    print("\nworst reports:", offenders.most_common(5))
    print("\nexamples:")
    for e in examples:
        print("  ", e)
    return 0


if __name__ == "__main__":
    sys.exit(main())
