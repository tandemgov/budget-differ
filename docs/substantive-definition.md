# Definition of "substantive": decision record

The tool's measured accuracy depends on what counts as a substantive change, and five boundary cases are not settled by the scope.
The draft labelers split on them, which is itself evidence that they need a client decision rather than more labeling.
For each question this record gives the current tool behavior, how the draft labels treated it, the measured effect where it can be computed, and a place to record the decision.

Counts are over draft-labeled units; measured rows come from `uv run python scripts/policy_eval.py score` (add `--set holdout` for the held-out set).
Pattern-based counts (questions 2–5) are approximate.

## 1. Narrative dollar figures for a named program

> "The recommendation includes $25,000,000 for dam safety" → "$20,000,000 for dam safety", with no floor or ceiling wording.

- **Tool today:** annotated as "dollar amount" but not promoted; the section stays number-only. Floors and ceilings ("not less than", "up to") are promoted.
- **Draft labels:** a separate kind, `funding_amount` (153 demonstration units, 32 held-out), scored neither as missed nor as false alarms.
- **Effect of each answer (held-out set):**

| Decision | Substantive units | Missed | Flag precision | Paragraphs promoted |
|---|---|---|---|---|
| Not substantive (current) | 131 | 14 (10.7%) | 82.0% | 61 |
| Substantive, tool unchanged | 163 | 39 (23.9%) | 86.9% | 61 |
| Substantive, and promote dollar-amount flags (`policy.FUNDING_TIER = REVIEW`) | 163 | 13 (8.0%) | 86.6% | 97 |

  On the demonstration set the three rows are 14/396 (3.5%), 140/549 (25.5%), and 14/549 (2.6%) missed.
  Reproduce the middle row with `score --as funding_amount=substantive`.
- **Consideration:** money tables are out of scope and belong to the sibling project; a narrative figure often restates a table line, but when it names a specific program it is how the committee directs funding within an account.

**Decision:** ______ **Decided by / date:** ______

## 2. "The Committee supports X" with no direction to the agency

> A new or dropped paragraph stating support for a program, with no "directs", "urges", "encourages", or "expects".

- **Tool today:** a new or dropped paragraph always surfaces as new/dropped; an edit to one surfaces only if it trips another rule.
- **Draft labels:** split by subcommittee. About 34 such units in the demonstration set: mostly `substantive` in Energy-Water (18 of 23), `editorial` in Legislative Branch (10 of 11).
- **Consideration:** support statements are how report language signals funding intent without a directive; treating them as substantive raises recall targets for edits the rules cannot see.

**Decision:** ______ **Decided by / date:** ______

## 3. "The Committee looks forward to receiving the report"

> A prior year's "The Committee directs a report within 90 days" becomes "The Committee looks forward to receiving the report."

- **Tool today:** the removal of "directs … within 90 days" flags a discretion and deadline change on the edited paragraph; a standalone "looks forward" paragraph is not flagged.
- **Draft labels:** split. About 43 units mention "looks forward" or "awaits" in the demonstration set: 23 `substantive`, 20 `editorial`.
- **Consideration:** usually an acknowledgment that a prior directive continues, not a new requirement.

**Decision:** ______ **Decided by / date:** ______

## 4. Amounts that "shall remain available until" a later date

> "Of the total, $28,200,000 shall remain available until September 30, 2029" → "$10,000,000 … until September 30, 2030".

- **Tool today:** the year advancing by the report gap is routine; the amount change is a dollar-amount annotation (see question 1). A rule treating these as set-asides was tried and withdrawn because it mostly promoted units labeled plain dollar changes.
- **Draft labels:** split. About 25 units across both sets: 9 `substantive`, 16 `funding_amount`.
- **Consideration:** multi-year availability is a real constraint on agency flexibility, but these sentences typically restate bill text.

**Decision:** ______ **Decided by / date:** ______

## 5. A change of addressee

> "The Committee reminds the Administration …" → "reminds OMB …"; "GDO to coordinate with the Office of Electricity" → "the Department".

- **Tool today:** treated as an acronym swap or wording change, not promoted.
- **Draft labels:** `substantive` when noticed (at least 4 demonstration units; the tool missed 3 of them).
- **Consideration:** narrowing or widening who is directed can matter for oversight, but most instances follow reorganizations or house style.

**Decision:** ______ **Decided by / date:** ______

## After deciding

1. Update `docs/labeling-guide.md` with each decision so future labels follow it.
2. Relabel affected units: export `uv run python scripts/policy_eval.py worksheet`, correct the rows, and `import` it (human labels are never overwritten by drafts).
3. If a decision changes tool behavior (for example question 1), make the change, add a regression case to `tests/test_policy.py`, and re-run both `score` commands.
4. Record whether the remaining misses (see "What the misses and false alarms look like" in [evaluation.md](evaluation.md)) are acceptable for the intended use.

**Remaining misses acceptable for intended use:** ______ **Decided by / date:** ______
