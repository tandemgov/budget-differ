# Evaluation

This document reports how well budget-differ surfaces changes that matter, measured against a reference set built from the source reports rather than from the tool's own output.
Method and rationale are in [methodology.md](methodology.md); label definitions are in [labeling-guide.md](labeling-guide.md).

## Status of the reference labels

**Every label in the current reference set is a draft.**
Labels were written blind to the tool (the labelers saw only the paired report texts and the labeling guide) by language-model labelers following the guide, then merged unedited.
No human has adjudicated them yet, and the rules being evaluated were written by the same consultant who wrote the labeling guide.
Treat the numbers below as a well-instrumented first estimate, not as validation.
The adjudication workflow at the end of this document replaces draft labels with a reviewer's and re-scores in seconds; each scored summary prints how many labels are human-adjudicated.

The scope sets no numerical acceptance threshold, and none is proposed here as one.
Any threshold should be agreed with the client after human adjudication.

## Reference set construction

For each comparison, both raw reports are re-read with a deliberately simple splitter (indentation and blank lines only) that shares no code with the tool's segmenter, table detector, or aligner.
Paragraphs identical in both years drop out; the rest are paired by text similarity (mutual best match at ≥60) into units: `edited`, `added`, `removed`, or `relocated` (identical text under a different heading).
Because the reference is independent of the tool, it can expose changes the tool lost in segmentation or alignment.
The units themselves are checked in at `tests/policy_reference/units/`; labels are at `tests/policy_reference/<comparison>.json`.

Two sets are labeled:

| Set | Comparisons | Units labeled | Sampling |
|---|---|---|---|
| Demonstration | House Energy-Water FY2025→FY2026, FY2026→FY2027; House Legislative Branch FY2025→FY2026, FY2026→FY2027 | 849 | Legislative Branch: every unit. Energy-Water: every edit of ≤12 words plus a seeded random 80 of the rest, per comparison |
| Held out | House Energy-Water FY2023→FY2024; House Legislative Branch FY2023→FY2024 | 264 | Every edit of ≤12 words plus a seeded random 40 of the rest, per comparison |

The policy rules were developed while reading edits from the demonstration comparisons, so that set is a development set.
The held-out comparisons were extracted and labeled only after the rules were frozen, and no rule was changed after scoring them.
One alignment change (near-verbatim paragraph moves, below) was made after the first held-out score; it was motivated by demonstration-set errors inspected earlier, and both before and after results are reported.

## What is measured

Each labeled unit is located in the tool's output and scored three ways, reported separately.

- **Missed substantive changes.** A unit labeled `substantive` that the tool does not surface: shown as minor or number-only with no review-tier flag, shown as unchanged, or absent from the tool's output (lost in segmentation). New, dropped, and split paragraphs count as surfaced.
- **False alarms.** A unit labeled `editorial`, `routine_numbers`, or `renumbering` that a policy flag promoted to substantive. Size-based substantive classifications of non-substantive edits are reported alongside for comparison.
- **Alignment disagreements.** The tool paired an old paragraph with a different new one (`mispaired`), showed a reference edit as an unrelated drop plus addition (`split`), or paired a paragraph the reference left unpaired (`absorbed`). These are disagreements, not certain tool errors; see the spot check below.

Changes of a narrative dollar figure alone (`funding_amount`) are counted but scored neither as missed nor as false alarms, because whether they are policy is a client decision.
The **baseline** is the tool's own size-only classification (the `literal_change` kept on each paragraph), i.e. the classifier as it stood before policy signals were added.

## Results

Reproduce with `uv run python scripts/policy_eval.py score` and `uv run python scripts/policy_eval.py score --set holdout` (about three seconds each).

### Missed substantive changes

| Set | Substantive units | Missed, current | Missed, size-only baseline | Small edits (≤12 words): missed current / baseline | Lost in segmentation |
|---|---|---|---|---|---|
| Demonstration | 396 | 14 (3.5%) | 54 (13.6%) | 13 / 53 of 92 | 0 |
| Held out | 131 | 14 (10.7%) | 39 (29.8%) | 14 / 39 of 68 | 0 |

Per demonstration comparison (current / baseline): Energy-Water FY25→26 7/32 of 104; FY26→27 3/15 of 105; Legislative Branch FY25→26 1/2 of 84; FY26→27 3/5 of 103.
Per held-out comparison: Energy-Water FY23→24 12/35 of 95; Legislative Branch FY23→24 2/4 of 36.
The hierarchy fixes of 2026-09-16 (see [methodology.md](methodology.md#1-segmentation-segment)) moved these from 18 and 15 missed, recovering every unit previously lost in segmentation.

The gain is concentrated where the review said it would be: small edits.
On the held-out set, policy signals cut small-edit misses from 57% to 21%.

### False alarms

| Set | Paragraphs promoted by a flag | Of those, labeled substantive | Non-substantive edits promoted | Non-substantive edits called substantive by size alone |
|---|---|---|---|---|
| Demonstration | 108 | 85.2% | 13 of 182 | 29 |
| Held out | 61 | 82.0% | 8 of 78 | 15 |

Three narrative dollar-only changes were promoted in each set (of 153 and 32).

### Alignment

| Set | Mispaired | Split into drop + add | Absorbed | Moves not shown |
|---|---|---|---|---|
| Demonstration | 3 | 10 | 62 | 1 |
| Held out | 1 | 12 | 9 | 0 |

Absorbed rose from 56 to 62 with the hierarchy fixes: text that sat under a parenthetical subtitle now shares a section with its account, so the tool pairs paragraphs the reference splitter left as separate adds and drops, and some former cross-section moves became in-section edits.
Before near-verbatim move detection was added, splits were 28 (demonstration) and 27 (held out); missed-substantive and false-alarm counts were unchanged by that fix.
Before the renumbering-collision guard, the demonstration set had 10 mispairings, 7 of them renumbered general provisions whose templated wording ("Section N extends the authorization for …") matched a different provision under the same number.

A spot check of `absorbed` disagreements found them mostly on the reference side: the simple splitter leaves a heavily revised directive unpaired (for example the GPO Inspector General directive, now "no less than $7,226,000 to support no fewer than 25 FTE"), while the tool pairs it with its predecessor by topic.
Section-level alignment is measured separately by `scripts/linkage_eval.py`; see the caveat in known issues below.

## What the misses and false alarms look like

Misses, in rough order of frequency:

- **Scope changes in ordinary words.** "new construction starts" → "new study starts"; "the State of Illinois" → "states in the Great Lakes region"; "nuclear demonstration projects" → "nuclear projects"; a program dropped from a list of offices. Rules have no lexical handle on these; some carry a low-tier "wording change" note.
- **Addressee changes.** "the Administration" → "OMB" as the party directed. Labelers called these substantive; the rules treat an acronym swap as editorial.
- **Funding-direction wording** that is neither a floor nor a ceiling: "provides $1,000,000 to continue the program" → "provides funding"; changed amounts that "shall remain available until" a later year. An availability rule was tried and withdrawn because it mostly promoted units labelers called plain dollar changes.
- **Segmentation and alignment losses**: program lists inside table-like regions, and a directive whose `Topic.--` lead-in was removed and so was paired with the wrong neighbor.

False alarms are mostly force or reporting vocabulary inside background prose: "is encouraged by" in praise, "congressionally mandated" as an adjective, "reports that the shoaling has become a hazard", or a count dropped from a description ("approximately 120" projects).
A date-shift flag also fires on citation years ("WRDA 2020 and WRDA 2022" → "WRDA 2024") where the paragraph is substantive for another reason.

## Open definition questions for the client

The labelers split repeatedly on five boundary cases: narrative dollar figures, "The Committee supports" statements, "looks forward to receiving the report", amounts that "shall remain available until" a date, and changes of addressee.
[substantive-definition.md](substantive-definition.md) records each with the tool's current behavior, how the drafts treated it, the measured effect of each answer, and a place for the client's decision.
The largest is the first: counting narrative dollar changes as substantive raises held-out misses from 10.7% to 23.9% unless dollar-amount flags are also promoted (then 8.0%, with 97 rather than 61 promoted paragraphs).

## Adjudicating and extending the labels

For acceptance, use the bounded review in [acceptance-review.md](acceptance-review.md) (about three hours, all four comparisons, including sections read in the original reports).
To adjudicate labels beyond that packet:

```bash
uv run python scripts/policy_eval.py worksheet                 # .policy-eval/worksheet-demo.csv
uv run python scripts/policy_eval.py worksheet --set holdout   # .policy-eval/worksheet-holdout.csv
# open in a spreadsheet; for each row you review fill reviewer_kind, reviewer_categories (;-separated), reviewer_note, reviewer_name
uv run python scripts/policy_eval.py import .policy-eval/worksheet-demo.csv
uv run python scripts/policy_eval.py score
```

Each worksheet row shows the word-level changes, both texts, and the draft label.
Imported rows keep the draft beside the human label, so agreement between draft and human labels can be measured later.
A draft never overwrites a human label on re-merge.

To add a comparison, append it to `SETS` in `scripts/policy_eval.py`, then run `extract`, `sample`, label the batches in `.policy-eval/batches/`, `merge`, and `score`.

## Known issues with the measurement itself

- Labels are drafts (see above); the labelers also disagreed with each other on the ambiguous classes listed, so class boundaries are noisy.
- Energy-Water beyond small edits is sampled, not exhaustive; rates on large edits and new or dropped paragraphs there have wide uncertainty.
- The reference splitter pairs paragraphs by similarity alone; 9 demonstration and held-out pairings were judged "not the same passage" by labelers and are scored only on whether the new text surfaced.
- Section-linkage labels were originally keyed by section path and document order, which a later segmentation change shifted, orphaning 150 of 151. They are now keyed by content (report pair, headings, and text excerpts). 104 were restored from saved candidate texts, of which 80 still match a current linkage decision (the other 24 describe pairings the current aligner no longer considers); 47 had no saved text and are kept, unscored, in `tests/linkage_labels_unrecoverable.json`. Results on the restored labels are in [methodology.md](methodology.md#2-alignment-alignpy-comparepy). Linkage labels were adjudicated in an earlier session; whether that adjudication was human is not recorded.
