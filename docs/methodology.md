# Methodology and assessment

This document explains how budget-differ compares year-over-year appropriations committee reports, why it takes the approach it does, how that approach was evaluated, and where it falls short.
It is written so a reviewer can use and judge the tool without the consultant present.
Measured results are in [evaluation.md](evaluation.md); the step-by-step demonstration is in [demo-walkthrough.md](demo-walkthrough.md).

## What the tool compares, and what it does not claim

Budget-differ compares the narrative language of a committee report with the same subcommittee's report from the latest earlier fiscal year: account narratives, `Topic.--` directives, and descriptions of general provisions.

Committee report language is not statute.
It explains the committee's recommendation and directs, requests, or urges agencies by long-standing convention, enforced through oversight and the next year's bill rather than by law.
A flag such as "may → shall" means the report's instruction to the agency became firmer; it does not mean a statutory requirement changed.
Where a report describes a general provision of the accompanying bill ("Section 305 prohibits …"), a change describes proposed bill text, which becomes law only if enacted in that form.
Nothing in this tool compares enacted law, bill text itself, or explanatory statements accompanying an enacted omnibus.

Excluded material:

- **Money tables.** Comparative statements of budget authority and the dotted-leader funding blocks are detected and dropped, biased toward over-dropping; a `⚠ table region(s) skipped` note marks where. Line-item dollars belong to the sibling `appropriations-committee-reports` project. House comparative statements are images in the GovInfo text rendering and are not recoverable from it at all.
- **Reports without usable text.** GPO occasionally publishes a report as a text-free stub (for example Senate Labor-HHS FY2026); these are skipped with a warning.
- **Miscataloged documents.** Continuing-resolution conference reports cataloged as subcommittee reports (for example CRPT-116hrpt9) are excluded by title.
- **Front and back matter.** The contents, and everything from the chamber compliance sections on (rule citations, changes in existing law, Ramseyer prints) are dropped, because the back matter repeats bill text and would double every general-provision diff.

## Pipeline

### 1. Segmentation (`segment/`)

GovInfo's `.htm` rendering is GPO fixed-width text.
The segmenter classifies each line (heading, body, table rule, dotted leader, blank), drops table regions, unwraps hard-wrapped paragraphs and rejoins hyphenated line breaks, and builds a title → agency → account → topical-heading tree.
Heading levels come from three signals, later ones overriding earlier ones: typography of the fixed-width text, the report's own table of contents, and the font tiers of the typeset PDF of the same report (full-size capitals for agencies, small capitals for accounts), which the text rendering flattens.
Paragraphs opening with a `Topic.--` lead-in are tagged as directives; general provisions are split one section per provision.

Measured: 99.84% recall of directive and general-provision lead-ins corpus-wide (`scripts/sweep.py`); 0.6% of sections misparented against USASpending account-to-agency truth (`scripts/hierarchy_audit.py`).

### 2. Alignment (`align.py`, `compare.py`)

Sections are matched across years in passes that grow less literal: exact heading path; unique headings; fuzzy heading plus content similarity constrained to a shared parent; and content-only rescue for renames and general-provision renumbering.
A dropped section and a new section that are each other's best content match (≥65% overlap, consistent parents) are promoted to a single diff labeled "renamed"; weaker kinships are shown as "possible successor/predecessor" links without asserting a match.
Paragraphs that left one section and reappeared in another are shown as moves, verbatim or edited, rather than as a deletion plus an addition.

Measured by `scripts/linkage_eval.py score` (2026-09-16), with two views that should be read together.
Over all 26,324 labeled candidates (mostly auto-labeled unambiguous pairs), precision on accepted matches is about 100% and recall 99.8%.
Over only the 119 adjudicated borderline candidates, precision is 86.5% (32 of 37 accepted) and recall 45.7%; the rename-promotion pass is the weakest (5 of 8 accepted renames correct), and its same/different labels interleave across scores from 55 to 86, so no threshold change fixes it.
The fuzzy-heading pass is deliberately conservative (85.8% recall over labeled candidates at 100% precision).
Earlier figures in this repository ("~99.8% precision over labeled candidates", "151 adjudicated") predate a segmentation change that orphaned the adjudicated labels and are historical; see [evaluation.md](evaluation.md#known-issues-with-the-measurement-itself).

### 3. Differencing (`diffing.py`)

Within a matched section, paragraphs are aligned by directive topic or by a masked text key, and the leftovers of a replaced block are re-paired only when their word sequences are at least 50% similar.
Each paired paragraph gets a word-level diff (insertions and deletions), rendered inline.

### 4. Classification (`diffing.py`, `policy.py`)

Each paragraph change receives two independent signals.

**Size class.**
Figures are masked (dollar amounts, numbers, years, dates); a change that disappears under the mask is *numbers only*, a change of at most five words or 97% similarity is *minor*, anything larger is *substantive*, and paragraphs with no counterpart are *new* or *dropped*.
Size alone is a poor proxy for importance: adding "not" is a one-word change.

**Policy signals.**
The word-level diff is inspected for edits to language families that carry directive or legal force, each raising a flag that keeps the before/after words and a one-line reason:

| Family | Examples of what fires |
|---|---|
| negation | "not", "no", "without" added or removed |
| discretion / force | shift among mandatory (shall, must, directs, requires), expectation (expects, should), hortatory (urges, encourages, requests), and permissive (may, allows, authorizes) wording |
| prohibition | "none of the funds", "prohibits", "may not", "restrict" |
| eligibility / scope | "eligible", "only", "limited to", "priority", "except" |
| condition | "unless", "subject to", "prior to", "in consultation with", "approval" |
| reporting requirement | report, briefing, notify, certify, submit |
| deadline | a changed number before days/months/years, or "not later than"/"within" wording |
| floor / ceiling | a changed figure after "not less than", "up to", "no fewer than", or that wording added or removed |
| percentage / share | a changed figure before "percent" |
| program quantity | a changed count before a noun ("seven sections" → "nine sections") |

Lexical families are gated at paragraph level, so rewording that keeps the same force ("the Committee directs the Corps" → "the Corps is directed") stays quiet.
Numbers are judged by context instead of being masked away; fiscal-year rollovers and section-number citations are recognized as routine.
A review-tier flag promotes the paragraph to *substantive*, and the size-only class is kept alongside for evaluation.
Two lower-tier annotations do not promote: a changed dollar figure with no floor or ceiling wording ("dollar amount"), and a content-word substitution that the editorial rules (case, punctuation, hyphenation, plurals, stopwords, acronym expansion, voice) cannot explain ("wording change").
New and dropped paragraphs are tagged with the families they contain ("contains: prohibition, deadline").

### 5. Ranking (`significance.py`)

Sections are ordered by changed words weighted by class, boosted when directives change and tripled for new or dropped directives, plus a fixed weight per policy flag category that is independent of edit size, so a one-word negation outranks a long editorial rewrite.

### 6. Output (`render/`)

Static HTML with no server: a pair page per comparison (a "policy signals in small edits" table first, then the ranked section list, then inline diffs with flags beneath each changed paragraph), a timeline page per subcommittee across years, and a history page per account or provision.
Filters hide unchanged or number-only sections, or show directives or flagged sections only.
Every page links to the source PDF and HTML on GovInfo.

## Approaches considered

| Approach | Strengths | Weaknesses for legislative review |
|---|---|---|
| **Literal diff** (redline of the two documents) | Complete, exact, familiar; nothing hidden. | Hundreds of pages of redline with renumbering, moves, and table churn; no priority; importance is left entirely to the reader, which is the problem the tool exists to solve. |
| **Literal diff ranked by edit size** (the tool before this assessment) | Cheap, deterministic, removes noise from fiscal-year rollovers. | Systematically buries the smallest, most consequential edits: "not", "may → shall", "90 → 180 days", a dropped "not less than". |
| **Policy-specific rules** (chosen, layered on the ranked diff) | Transparent: every flag names the words and the rule. Deterministic and reproducible, runs offline in seconds on markup morning, no report text leaves the machine, failure modes are enumerable and testable. | Only sees what its lexicons describe; misses meaning changes carried by ordinary words ("construction" → "study", "environmental infrastructure" → "flood damage reduction"); lexical families can over-fire inside long rewrites; English-specific and needs upkeep as drafting conventions drift. |
| **Semantic similarity** (sentence embeddings) | Robust alignment across paraphrase, splits, and merges; could catch scope substitutions by embedding distance. | Distance is not significance: "may" and "shall" embed as near neighbors; opaque scores are hard to defend to a member or clerk; model and version drift change results over time. |
| **LLM classification or summarization** | Reads scope and intent changes rules cannot; can explain a change in plain English and cite it. | Non-deterministic; can assert changes that are not there; each claim must still be verified against the text; cost, latency, and data-handling approvals in a House or Senate office; evaluation must be repeated whenever the model changes. |

### Why rules on top of a literal diff suit this use

A committee clerk or member's staff member needs to find changes quickly, and must be able to defend every one of them by pointing at the words.
Rules satisfy that directly: each flag is a verifiable claim about specific words, the full redline stays one click away so nothing is hidden by the ranking, and a missed flag is a known class of miss (a meaning change carried by ordinary words) rather than an unexplained model judgment.
The tool is a triage layer, not an interpreter: flags are prompts to read, and the ranked diff remains the record.

A semantic or LLM pass is best used as a second opinion over what rules leave behind, specifically paragraphs the "wording change" annotation marks and new or dropped paragraphs, with its output presented as a suggestion and its claims checked against the diff.
The evaluation harness in `scripts/policy_eval.py` measures such an addition the same way it measures the rules, so it can be adopted only if it earns its place.

## Known failure modes

- **Scope substitutions in ordinary words** are not flagged as policy; they appear only as a low-tier "wording change" annotation (for example "construction project" → "feasibility study").
- **Lexical over-firing in long rewrites.** When a paragraph is substantially rewritten, family counts differ for incidental reasons and flags fire; these are listed separately ("signals inside larger rewrites") so they do not crowd the small-edit table.
- **Offsetting swaps.** A "shall → may" in one sentence and "may → shall" in another of the same paragraph leave family counts equal and raise no discretion flag.
- **Tone versus direction.** "Recommends" and "requests" are ambiguous between a direction and a funding recommendation; "recommends $X" is excluded, other uses count as hortatory.
- **Dollar changes** without floor or ceiling wording are annotated but not promoted; whether a changed narrative dollar figure is itself a policy change is a client decision.
- **Segmentation losses.** Text inside dropped table regions is not diffed, and a thin tail of table rows (1–8 paragraphs in about 40 of 231 reports) leaks into diffs as noise.
- **Alignment.** Renames below the promotion bar show as drop plus add with a "possible successor" hint; above it, a promoted rename can pair a split account with only one of its successors or a broad account with a narrow sub-heading (3 of 8 adjudicated promotions). Paragraphs re-paired inside a matched section can still pair two directives on related topics.
- **Blocking misses** in alignment (true matches never generated as candidates) are not measured.

## Reproducing and extending the evaluation

See [evaluation.md](evaluation.md) for results, the reference-set construction, and how to adjudicate or extend the labels.
The labeling rules are in [labeling-guide.md](labeling-guide.md).
