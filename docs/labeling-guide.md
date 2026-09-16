# Labeling guide: policy-change reference set

This guide defines the labels in `tests/policy_reference/`, which the evaluation (`scripts/policy_eval.py score`) uses to measure whether budget-differ surfaces the changes that matter.
It is written for anyone adjudicating labels: the consultant, a former clerk, or budget staff.

## What a unit is

A unit is one change between a prior-year and a proposed-year committee report, found by re-reading both reports with a plain paragraph splitter that shares no code with the tool's segmenter or aligner.
Paragraphs identical in both years are not units.

- `edited`: an old paragraph and a new paragraph paired as the same passage because their text is similar.
- `added`: a new-year paragraph with no similar prior-year paragraph.
- `removed`: a prior-year paragraph with no similar new-year paragraph.
- `relocated`: identical text that appears under a different nearby heading.

The splitter is deliberately simple, so some units are junk (table fragments, heading lines, contents entries) and some `edited` pairings join two unrelated paragraphs that happen to share boilerplate.
The labels below account for both.

## Judge the report, not the tool

Label from the texts alone.
Do not look at budget-differ's pages or code while labeling; the point is an independent reference.
The report's own text is always fair to consult for context (GovInfo links are in `demo/manifest.json`).

## Fields

`kind` (required), one of:

- `substantive`: a legislative staffer preparing for markup should read this change.
  It alters what the report directs, requests, urges, prohibits, or permits; who or what is eligible or covered; conditions, prerequisites, or approvals; deadlines or reporting and briefing obligations; a funding floor, ceiling, earmark, share, or count; or the scope of a program (for example, "construction" becoming "study").
  Adding or dropping a paragraph that carries any of these is substantive.
  A new or dropped paragraph that only restates background (history of a program, praise, description of the agency) is `editorial`.
- `funding_amount`: the only change is a dollar figure in a sentence that recommends or provides an amount ("The recommendation includes $X for Y"), with no floor/ceiling wording ("not less than", "up to") and no other language change.
  Kept separate because whether a changed narrative dollar figure is "policy" is the client's call; money tables are out of scope entirely.
- `routine_numbers`: fiscal-year rollovers, dates that advance by the same year, and restated totals whose language is otherwise unchanged.
- `renumbering`: section or paragraph numbers changed, text otherwise the same.
- `editorial`: capitalization, punctuation, abbreviations and acronyms, voice ("the Committee directs the Corps" ↔ "the Corps is directed"), synonyms that keep the same force and scope, reordering with no effect, and background prose.
- `moved`: a `relocated` unit whose passage genuinely moved to a different account or heading.
  If the heading difference is an artifact of the splitter, use `editorial`.
- `out_of_scope`: not narrative report language (table rows or headings, contents lines, fragments, page furniture).

`same_passage` (edited units only): `false` when the old and new texts are not the same passage at all, just boilerplate lookalikes.
Still set `kind` for what changed from a reader's point of view, usually `substantive` if either side carries a directive.

`categories` (substantive only): any that apply, from `negation`, `discretion`, `prohibition`, `eligibility`, `condition`, `reporting`, `deadline`, `limit`, `share`, `quantity`, `funding`, `scope`, `new_directive`, `dropped_directive`, `other`.

`rationale`: one sentence, at most about 25 words, naming the specific words that decide the label.

`reviewer`: `draft` for labels written without human review; replace with your name when you adjudicate.

## Hard cases

- "may" → "shall", "encourages" → "directs", "should consider" → "should": `substantive`, category `discretion`.
- Adding "not" or "only": `substantive` (`negation` or `eligibility`).
- "within 90 days" → "within 180 days": `substantive` (`deadline`).
- "not less than $10,000,000" → "not less than $12,000,000": `substantive` (`limit`); the floor is a directive.
- "$10,000,000" → "$12,000,000" with no floor wording: `funding_amount`.
- "fiscal year 2026" → "fiscal year 2027" alone: `routine_numbers`.
- "The Committee notes" → "The Committee is encouraged by": `editorial` unless the sentence also asks the agency to act.
- A directive whose topic lead-in was renamed ("Water Power.--" → "Hydropower and Hydrokinetic.--") with the rest identical: `editorial`, unless the rename narrows or widens the program.

## Committee report language is not statute

These labels describe changes in committee report instructions, which express committee intent and direct agencies by convention and through oversight; they do not amend statutory law.
General provisions quoted from the bill are the exception, and a label on one describes a change in proposed bill text, not in enacted law.
