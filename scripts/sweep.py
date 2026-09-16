"""Invariant sweep: segment every raw report in the corpus and report anomalies.

Tracks the two opposite failure modes of table dropping:
- LEAK (precision): table rows surviving into paragraphs, detected by dot/dash runs.
- SWALLOW (recall): directive/GP lead-ins landing inside dropped table spans.

Usage: uv run python scripts/sweep.py
"""

from __future__ import annotations

import re
import sys
import time

from budget_differ.compare import load_document
from budget_differ.config import approps_repo
from budget_differ.corpus import available_reports, raw_path
from budget_differ.segment.classify_lines import classify
from budget_differ.segment.preprocess import body_bounds, extract_pre_text
from budget_differ.segment.tables import table_spans

LEAK = re.compile(r"\.{6,}|-{6,}")
DIRECTIVE = re.compile(r"^\s{1,8}([A-Z][^.\n]{2,80}?)\.--")
GP = re.compile(r"^\s{1,8}Section\s+\d+")


def main() -> int:
    repo = approps_repo()
    reports = available_reports(repo)
    print(f"sweeping {len(reports)} reports")
    t0 = time.time()
    failures = 0
    tot_leads = tot_swallowed = 0
    for entry in reports:
        try:
            doc = load_document(repo, entry)
        except Exception as exc:  # noqa: BLE001 — sweep must not stop
            print(f"CRASH   {entry.package_id}: {exc!r}")
            failures += 1
            continue
        n_sections = len(doc.sections)
        n_paras = sum(len(s.paragraphs) for s in doc.sections)
        leaks = sum(1 for s in doc.sections for p in s.paragraphs if LEAK.search(p.text))

        text = extract_pre_text(raw_path(repo, entry).read_text(errors="replace"))
        lines = text.split("\n")
        start, end = body_bounds(lines)
        body = lines[:end]
        kinds = [classify(ln) for ln in body]
        in_span: set[int] = set()
        for a, b in table_spans(body, kinds):
            in_span.update(range(a, b + 1))
        leads = swallowed = 0
        for i in range(start, end):
            if DIRECTIVE.match(body[i]) or GP.match(body[i]):
                leads += 1
                if i in in_span:
                    swallowed += 1
        tot_leads += leads
        tot_swallowed += swallowed

        problems = []
        if n_sections < 15:
            problems.append(f"only {n_sections} sections")
        if leaks:
            problems.append(f"{leaks} leaking paragraphs")
        if n_paras < 30:
            problems.append(f"only {n_paras} paragraphs")
        if leads and swallowed / leads > 0.02:
            problems.append(f"{swallowed}/{leads} directives swallowed")
        if problems:
            print(f"WARN    {entry.package_id} (FY{entry.fiscal_year} {entry.chamber} "
                  f"{entry.subcommittee}): {', '.join(problems)}")
            failures += 1
    dt = time.time() - t0
    print(f"directive/GP recall: {tot_leads - tot_swallowed}/{tot_leads} "
          f"({(tot_leads - tot_swallowed) / max(tot_leads, 1):.2%}) — "
          f"{tot_swallowed} swallowed by table spans")
    print(f"done in {dt:.1f}s — {failures} report(s) with problems out of {len(reports)}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
