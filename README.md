# budget-differ

Diff year-over-year appropriations committee report language.

Appropriations bills recur every year with largely similar committee report language, and House reports drop only right before markup. This tool compares a report against the prior year's and produces static HTML pages that rank what changed — new and dropped sections first, then substantive language changes, with number-only changes and unchanged text filtered out of the way.

## Requirements

- [uv](https://docs.astral.sh/uv/)
- A local checkout of [appropriations-committee-reports](../appropriations-committee-reports) with its raw corpus downloaded (`data/raw/`). budget-differ reads that repo's catalog and raw report files directly; it does not fetch anything itself.

If the sibling repo is not at `../appropriations-committee-reports`, set `BUDGET_DIFFER_APPROPS_REPO=/path/to/checkout`.

## Start here

- [docs/demo-walkthrough.md](docs/demo-walkthrough.md): the demonstration (House Energy-Water and Legislative Branch, FY2025–FY2027), how to read a page, and representative changes with links.
- [docs/methodology.md](docs/methodology.md): how segmentation, alignment, differencing, classification, and ranking work; the approaches considered and why this one; failure modes and excluded material.
- [docs/evaluation.md](docs/evaluation.md): measured missed changes, false alarms, and alignment errors against a reference set, and how to adjudicate the (currently draft) labels.
- [docs/labeling-guide.md](docs/labeling-guide.md): definitions for reference labels.
- [docs/acceptance-review.md](docs/acceptance-review.md): the bounded human review needed before sign-off, with a packet generated into `review/`.
- [docs/substantive-definition.md](docs/substantive-definition.md): five boundary questions for the client, with the measured effect of each answer.

The checked-in `demo/` folder is the generated demonstration site, published at https://tandemgov.github.io/budget-differ/ on every push to `main` that changes it; locally, open `demo/index.html` in a browser.

## Setup

1. Install [uv](https://docs.astral.sh/uv/) (Python 3.12+ is fetched automatically).
2. Clone [appropriations-committee-reports](../appropriations-committee-reports) next to this repo and download its raw corpus (`approps discover && approps download`), or point `BUDGET_DIFFER_APPROPS_REPO` at an existing checkout.
3. `uv sync` in this repo.
4. Confirm the demonstration inputs match: `demo/manifest.json` lists each report's GovInfo URL and SHA-256.

## Demonstration and evaluation commands

```bash
uv run budget-differ demo                                   # rebuild demo/ (deterministic; git status stays clean)
uv run pytest                                               # unit, policy regression, golden-pair, and demo link tests
uv run python scripts/policy_eval.py score                  # policy-change evaluation, demonstration comparisons
uv run python scripts/policy_eval.py score --set holdout    # same, held-out FY2023→FY2024 comparisons
uv run python scripts/policy_eval.py review                 # acceptance-review packet in review/ (docs/acceptance-review.md)
uv run python scripts/policy_eval.py score --as funding_amount=substantive   # effect of a definition decision
uv run python scripts/policy_eval.py worksheet              # spreadsheet for human adjudication of all labels
uv run python scripts/policy_eval.py import FILE.csv        # fold adjudicated labels back in, then re-score
```

## Usage

```bash
uv run budget-differ                          # build every valid adjacent-FY pair into out/
uv run budget-differ house                    # one chamber
uv run budget-differ house energy-water       # one subcommittee (catalog slug, case-insensitive)
uv run budget-differ house energy-water 2027  # one target fiscal year
```

Open `out/index.html`. Each pair page has a significance-ranked summary of changed sections, inline word-level diffs (insertions green, deletions red), and filters to hide unchanged or number-only sections or show directives only.

Each report is paired with the same chamber + subcommittee report from the latest earlier fiscal year on disk, so Senate gap years (FY2021, FY2023) fall back further and the page header says which years were compared.

Debug segmentation for one report:

```bash
uv run budget-differ --dump-sections CRPT-119hrpt667
```

## How it works

1. **Segment** (`segment/`): parse the GPO fixed-width text into a title → agency → account section tree; unwrap hard-wrapped paragraphs; drop money-table regions (biased to over-drop — a `⚠ tables skipped` flag marks where); split general provisions into per-section units; tag `Topic.--` directive paragraphs.
   Heading levels come from three signals, later ones overriding earlier ones: typographic heuristics on the fixed-width text, the report's own table of contents, and the PDF twin's font codes (`segment/pdfhier.py`) — the typeset PDF of the same GPO locator source distinguishes agency-tier headings (full-size caps) from account and topical headings (small caps), a distinction the `.htm` render flattens into identical centered ALL CAPS.
   PDF font tiers are extracted once per report (pymupdf, dev dependency) and cached as JSON in `.pdfhier-cache/`; without the PDF or the cache the parser falls back to text heuristics alone.
2. **Align** (`align.py`, `compare.py`): match sections across years by exact normalized heading path, then unique headings, then fuzzy matching constrained to a shared parent, then content-similarity rescue for renames and general-provision renumbering. Dropped+new pairs that are each other's best content match (≥65% overlap, consistent parents) are promoted to real diffs labeled "renamed"; weaker kinships (mutual ≥50%, one-directional ≥60%) render as "possible successor/predecessor" hints so splits and merges stay visible without asserting a match.
3. **Diff + classify** (`diffing.py`, `policy.py`): word-level difflib diffs per paired paragraph; a masking step (dollars → `#`, years → `#Y`) separates number-only changes from language changes by size, and policy-signal rules flag small edits that change negation, discretion, prohibitions, eligibility, conditions, reporting, deadlines, floors and ceilings, shares, counts, or what a provision does — promoting them to substantive with the before/after language and a reason.
4. **Rank** (`significance.py`): changed words × change-class weight, boosted for directives, plus a fixed weight per policy-flag category independent of edit size; new/dropped sections at the top.
5. **Render** (`render/`): self-contained HTML, no server, stdlib templates.

## Development

```bash
uv run pytest                      # unit + golden-pair tests (corpus tests skip if repo absent)
uv run python scripts/sweep.py     # parse the full corpus, report leakage/anomalies
uv run python scripts/hierarchy_audit.py   # misparenting rate vs USASpending account→agency truth
```

Cross-year alignment quality is measured, not eyeballed: `scripts/linkage_eval.py` traces every linkage decision (all passes, accepted and near-miss), auto-labels the unambiguous ends, and scores precision/recall per pass against the adjudicated labels in `tests/linkage_labels.json`, with threshold sweeps for the tunable passes.

```bash
uv run python scripts/linkage_eval.py emit     # trace all pairs -> .linkage-eval/candidates.jsonl
uv run python scripts/linkage_eval.py sample   # stratified batch to adjudicate next
uv run python scripts/linkage_eval.py score    # precision/recall + threshold sweeps
```

## Known limits (v1)

- Money tables are dropped, not diffed — line-item dollars are the sibling repo's job.
- Measured recall on the highest-value units (directive and general-provision lead-ins): **99.84% corpus-wide**; the 116 swallowed lead-ins concentrate in FY2016-era reports. `scripts/sweep.py` tracks this per report alongside the leakage counter.
- A thin tail of table rows (1–8 paragraphs in ~40 of 231 reports) still leaks into diffs.
- Section parentage measured against USASpending account→agency truth: 0.6% misparented corpus-wide (`scripts/hierarchy_audit.py`); the PDF font-tier override (see How it works) and the agency lexicon carry most of that.
- Cross-year alignment (`scripts/linkage_eval.py score`, 2026-09-16): about 100% precision over all labeled candidates, but 86.5% (32 of 37) over the 119 adjudicated borderline candidates; rename promotion is the weakest pass (5 of 8). Blocking misses (true pairs never generated as candidates) are not measured. Details in `docs/methodology.md`.
- Policy-significance classification is measured against a reference set whose labels are still drafts pending human adjudication (`docs/evaluation.md`): on held-out FY2023→FY2024 comparisons it misses 11.5% of substantive changes (22% of small ones) versus 30.5% for size alone, and about 82% of promoted paragraphs were labeled substantive. Scope changes carried by ordinary words ("construction" → "study") are the main miss.
- Section-linkage labels are now matched by content; 104 of the original 151 were restored (80 match a current decision) and 47 without saved text are kept unscored in `tests/linkage_labels_unrecoverable.json`.
- Reports GPO published as text-free stubs (e.g. Senate Labor-HHS FY2026) are skipped with a warning; continuing-resolution conference reports miscataloged as subcommittee reports (e.g. CRPT-116hrpt9) are excluded by title.
- Same-day ingestion of a report not yet in the sibling repo's catalog is v2; for now, run that repo's `approps discover && approps download` first.

## License

Released into the public domain under [CC0 1.0 Universal](LICENSE).
