# Acceptance review protocol

This is the bounded human review that turns the draft evaluation into accepted results.
It asks someone familiar with appropriations report language (a former clerk, budget staffer, or the client's designee) to check representative tool results from all four demonstration comparisons, read a few sections directly in the original reports, and record corrections that are then re-scored.
Expect about three hours.

## What is in the packet

Generate or refresh it with:

```bash
uv run python scripts/policy_eval.py review
```

This writes three files in `review/`:

- `review-packet.csv`: 71 rows across the four comparisons, in four groups.
  - **1 missed substantive** (18): every change the draft labels call substantive that the tool does not surface.
  - **2 false alarm** (13): every change a policy flag promoted that the draft labels call editorial, routine, or renumbering.
  - **3 flag, looks right** (24): a seeded sample of promoted changes the draft labels agree with, up to 6 per comparison.
  - **4 quiet, looks right** (16): a seeded sample of small edits the tool left unpromoted and the draft labels call non-substantive, up to 4 per comparison.
- `sections.md`: two randomly chosen changed sections per comparison, with links to the tool's page and to both original PDFs on GovInfo.
- `findings.csv`: a blank template for changes found while reading the originals.

Each packet row shows the tool's result and flags, a link to the exact section on the demonstration page, the word-level changes, both texts, and the draft label with its rationale.

## Steps

1. **Settle the definition first, or note assumptions.** Read [substantive-definition.md](substantive-definition.md). If the client has decided the five boundary questions, apply those decisions; if not, record the reviewer's own judgment in `reviewer_note` so the decisions can be applied later.
2. **Review the packet.** For each row, open `demo_link` if the texts alone are not enough, then fill in:
   - `reviewer_kind`: `substantive`, `funding_amount`, `routine_numbers`, `renumbering`, `editorial`, `moved`, or `out_of_scope` (definitions in [labeling-guide.md](labeling-guide.md));
   - `reviewer_categories` for substantive rows, separated by semicolons;
   - `reviewer_note`: one sentence on what decides it;
   - `tool_verdict`: `right`, `wrong`, or `partly`, meaning whether the page led a reader to the change and described it fairly;
   - `reviewer_name`.
3. **Read sections in the originals.** For each section in `sections.md`, read the prior-year and proposed text in the PDFs, then compare against the tool page. For every change that matters to a staffer, add a row to `review/findings.csv` with the quoted text, why it matters, and `tool_showed_it` = `yes` or `no`. Changes in money tables are out of scope and need not be recorded.
4. **Import and re-score.**

   ```bash
   uv run python scripts/policy_eval.py import review/review-packet.csv
   uv run python scripts/policy_eval.py score
   uv run python scripts/policy_eval.py score --set holdout
   ```

   The import replaces the draft label on every reviewed row and keeps the draft beside it. `score` then reports how many labels are human-adjudicated and the count of reviewer findings the tool did not show.
5. **Commit the evidence.** Commit `review/` and `tests/policy_reference/` so the review is reproducible.
6. **Update the record.** Replace the result tables in [evaluation.md](evaluation.md) with the re-scored figures, add the reviewer's corrections that changed the picture (for example, false alarms that turned out to be real changes), and complete the sign-off below.

## Reading the result

- **Draft agreement.** Rows in groups 3 and 4 where the reviewer agrees with the draft label indicate how far the unreviewed draft labels can be trusted. If agreement is low, extend review beyond the packet before quoting overall rates.
- **Misses that are not misses.** Group 1 rows the reviewer relabels as non-substantive lower the miss count; rows kept substantive are the tool's confirmed misses.
- **Real false alarms.** Group 2 rows the reviewer relabels as substantive were correct flags.
- **Unseen misses.** Findings with `tool_showed_it = no` are changes neither the tool nor the reference caught. Even one here is more important than a percentage point elsewhere, because it measures what the evaluation cannot.

## Sign-off

| | |
|---|---|
| Reviewer and role | |
| Date | |
| Packet rows reviewed | of 71 |
| Sections read in originals | of 8 |
| Draft labels changed | |
| Confirmed misses (group 1 kept substantive) | |
| Confirmed false alarms (group 2 kept non-substantive) | |
| Findings not shown by the tool | |
| Boundary decisions applied (substantive-definition.md) | |
| Remaining misses acceptable for intended use? | |
