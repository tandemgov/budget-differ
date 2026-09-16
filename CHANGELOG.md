# Changelog

## [Unreleased]

### Added

- Full-document view for each comparison (`document.html`): the newer report as written, redlined against the prior year, with dropped sections in place and a right-hand notes column.
- A floating outline in document order, marked by change class, and a breadcrumb row for the section in view, on both the ranked and full-document pages.

## [1.0.0] - 2026-09-16

First release: year-over-year diffs of House and Senate appropriations committee report language, with policy-significance flags, a reproducible demonstration, and a measured evaluation.

### Added

- Segmentation of GPO report text into a title → agency → account tree, with heading levels from text typography, the report's table of contents, and the typeset PDF's font tiers; money tables, front matter, and back matter are dropped.
- Cross-year section alignment (exact path, unique heading, fuzzy heading, content rescue), rename promotion, renumbered general provisions, and paragraph moves, including lightly edited moves between reorganized accounts.
- Word-level diffs with a size class and rule-based policy signals (negation, discretion, prohibitions, eligibility, conditions, reporting, deadlines, floors and ceilings, shares, counts, provision effects), each with before/after language and a reason.
- Static HTML output: ranked pair pages opening with policy signals in small edits, filters, per-subcommittee timelines, and per-account history pages.
- `budget-differ demo`: House Energy-Water and Legislative Branch, FY2025–FY2027, with a manifest of source URLs and SHA-256 hashes; the generated site is included in `demo/`.
- `scripts/policy_eval.py`: tool-independent reference units, draft labels (demonstration and held-out sets), baseline scoring, an acceptance-review packet, and CSV adjudication.
- `scripts/linkage_eval.py`: section-linkage evaluation with content-matched adjudicated labels; `scripts/sweep.py` and `scripts/hierarchy_audit.py` for corpus-wide segmentation checks.
- Documentation: methodology and assessment of approaches, evaluation results, labeling guide, definition-of-substantive decision record, acceptance-review protocol, and demonstration walkthrough.

### Known limitations

- All policy-change reference labels are drafts pending human adjudication; see `docs/evaluation.md` and `docs/acceptance-review.md`.
- Five boundary cases in the definition of a substantive change await a client decision; see `docs/substantive-definition.md`.
