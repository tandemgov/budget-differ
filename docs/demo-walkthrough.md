# Demonstration walkthrough

This walkthrough covers the required demonstration, published at https://tandemgov.github.io/budget-differ/. It covers two House subcommittees across three successive fiscal years, which gives six reports and four year-over-year comparisons.
Every example below links to the generated page, and every claim can be checked against the source report linked from the top of that page.

## The six reports

| Subcommittee | FY2025 | FY2026 | FY2027 |
|---|---|---|---|
| Energy and Water Development | CRPT-118hrpt580 | CRPT-119hrpt213 | CRPT-119hrpt667 |
| Legislative Branch | CRPT-118hrpt555 | CRPT-119hrpt178 | CRPT-119hrpt666 |

GovInfo URLs and SHA-256 hashes of the exact files compared are in [`demo/manifest.json`](../demo/manifest.json).

## Reproduce it

```bash
uv sync
uv run budget-differ demo          # writes demo/ (about a minute)
uv run pytest                      # includes the demo link check and policy regression tests
uv run python scripts/policy_eval.py score
uv run python scripts/policy_eval.py score --set holdout
```

The build is deterministic: rebuilding over the checked-in `demo/` should leave `git status` clean.
The published copy is at https://tandemgov.github.io/budget-differ/; locally, open `demo/index.html` in a browser (no server needed).

## How to read a comparison page

1. **Policy signals in small edits.** The table at the top lists edits of a few words or a single figure that touch directive force, prohibitions, eligibility, conditions, reporting, deadlines, floors and ceilings, shares, or counts. Each row shows the prior-year and proposed language with the changed words marked. Size-based ranking alone would file these as minor or number-only. Signals inside larger rewrites are collapsed below the table.
2. **Changed sections, most significant first.** Every section with its change class (new, dropped, substantive, minor, numbers only, unchanged) and its flag badges.
3. **Details.** Inline word-level diffs, with each flag and its reason under the paragraph it applies to. Unchanged paragraphs are collapsed. Moves, renames, and possible successors are linked.

Filters in the sticky bar hide unchanged or number-only sections, or restrict the page to directives or flagged sections.
The timeline page for each subcommittee shows every account across the three years, and each account links to a history page that shows when each paragraph was added or last changed.

## Representative changes

### Energy-Water, FY2025 → FY2026 ([page](https://tandemgov.github.io/budget-differ/house-energy-water-fy2025-fy2026/))

- **Cost share, 65/35 → 75/25.** The report's statement of how inland waterways construction is split between the general fund and the Inland Waterways Trust Fund changed from 65/35 to 75/25. Flagged as a percentage/share change. [Inland Waterways System](https://tandemgov.github.io/budget-differ/house-energy-water-fy2025-fy2026/#s-title_i_corps_of_engineers_civil-department_of_the_army-inla-cdffa1)
- **Deadline, 30 → 60 days.** The MSIPP report due before a funding opportunity announcement moved from "not later than 30 days" to "not later than 60 days after the date of enactment". Flagged as a deadline. [Defense Environmental Cleanup](https://tandemgov.github.io/budget-differ/house-energy-water-fy2025-fy2026/#s-title_iii_department_of_energy-environmental_and_other_defen-bf3e7c)
- **Funding floors removed and lowered.** In Sustainable Transportation the Clean Cities floor fell from not less than $65,000,000 to $60,000,000, and "not less than" was struck before both the $20,000,000 cooperative-agreement and $40,000,000 grant amounts, so they are no longer minimums. Flagged as floor/ceiling changes. [Sustainable Transportation](https://tandemgov.github.io/budget-differ/house-energy-water-fy2025-fy2026/#s-title_iii_department_of_energy-energy_programs-sustainable_t-9afb29)
- **Provision now modified.** Section 301's description changed from "continues a provision" to "continues and modifies a provision" on requests for proposals, which signals changed bill text. Flagged as a provision effect. [Section 301](https://tandemgov.github.io/budget-differ/house-energy-water-fy2025-fy2026/#s-title_iii_department_of_energy-sec_301-f9d35f)
- **Timeline slip.** The FUSRAP draft Record of Decision moved from fiscal year 2024 to 2026, a two-year slip in a one-year comparison. Flagged as a date moved by more than the report gap. [Formerly Utilized Sites Remedial Action Program](https://tandemgov.github.io/budget-differ/house-energy-water-fy2025-fy2026/#s-title_i_corps_of_engineers_civil-department_of_the_army-form-650ebe)
- **Renumbering handled.** The Calfed Bay-Delta extension moved from Section 203 to Section 205 with identical text and is diffed as a renumbering, not as a dropped provision plus a new one. [Section 205](https://tandemgov.github.io/budget-differ/house-energy-water-fy2025-fy2026/#s-title_ii_department_of_the_interior-sec_205-4641dc-2)

### Energy-Water, FY2026 → FY2027 ([page](https://tandemgov.github.io/budget-differ/house-energy-water-fy2026-fy2027/))

- **Discretion tightened.** EIA was asked to "consider increasing" the detail and frequency of its consumption surveys; the proposed report asks it to "increase" them. Flagged as a discretion change. [Energy Information Administration](https://tandemgov.github.io/budget-differ/house-energy-water-fy2026-fy2027/#s-title_iii_department_of_energy-energy_programs-energy_inform-40420e)
- **Program count.** The Continuing Authorities Program went from $61,500,000 for seven CAP sections to $59,400,000 for nine. [Construction](https://tandemgov.github.io/budget-differ/house-energy-water-fy2026-fy2027/#s-title_i_corps_of_engineers_civil-department_of_the_army-cons-b1ce4e)
- **Floor added.** Mathematical, Computational, and Computer Sciences Research went from "$325,000,000" to "not less than $310,000,000", a lower amount that is now a minimum. [Advanced Scientific Computing Research](https://tandemgov.github.io/budget-differ/house-energy-water-fy2026-fy2027/#s-title_iii_department_of_energy-energy_programs-advanced_scie-9f8bf7)
- **Moved text.** The $25,000,000 Manufacturing Demonstration Facility and Carbon Fiber Technology Center directive moved verbatim from Energy Efficiency into the reorganized Critical Minerals, Materials, and Manufacturing account and is shown as a move. [Energy Efficiency](https://tandemgov.github.io/budget-differ/house-energy-water-fy2026-fy2027/#s-title_iii_department_of_energy-energy_programs-energy_effici-5d9441)

### Legislative Branch, FY2025 → FY2026 ([page](https://tandemgov.github.io/budget-differ/house-legislative-branch-fy2025-fy2026/))

- **Obligation limit, renumbered.** The Library of Congress limit on obligations from reimbursements and revolving funds rose from $318,789,000 to $332,285,000 while the provision was renumbered from Section 118 to 120. The renumbering is paired and the limit is flagged. [Section 120](https://tandemgov.github.io/budget-differ/house-legislative-branch-fy2025-fy2026/#s-title_i_legislative_branch_appropriations-sec_120-7dfc98)

### Legislative Branch, FY2026 → FY2027 ([page](https://tandemgov.github.io/budget-differ/house-legislative-branch-fy2026-fy2027/))

- **Staffing floor, 15 → 18 FTE.** The Capitol Police Inspector General is supported with "no fewer than 18 FTE", up from 15. The dollar floor is unchanged, so size-based ranking filed this as number-only; it is now flagged as a floor. [Salaries](https://tandemgov.github.io/budget-differ/house-legislative-branch-fy2026-fy2027/#s-title_i_legislative_branch_appropriations-united_states_capi-a18c4c)

## What the tool does not catch (examples)

These are real misses and false alarms from the evaluation, shown so reviewers know where to look for themselves.

- **Scope change in ordinary words (missed as a signal).** "When considering new construction starts" became "new study starts", with "project cost sharing agreement" becoming "feasibility cost sharing agreement". The rules see only a wording substitution; this paragraph surfaces as substantive only because other edits in it tripped flags. [New Starts](https://tandemgov.github.io/budget-differ/house-energy-water-fy2025-fy2026/#s-title_i_corps_of_engineers_civil-department_of_the_army-proj-d21590)
- **Addressee change (missed).** Several directives changed their addressee from "the Administration" to "OMB". The rules treat this as an acronym swap.
- **Tone read as direction (false alarm).** "The Committee notes the recent establishment" → "is encouraged by the establishment" raises a discretion flag although nothing is asked of the agency. [Grid Deployment](https://tandemgov.github.io/budget-differ/house-energy-water-fy2025-fy2026/#s-title_iii_department_of_energy-energy_programs-grid_deployme-f27af8)
- **Citation year read as a date (false reason).** "WRDA 2020 and WRDA 2022" → "WRDA 2024" in the inland waterways paragraph raises a date-moved flag; the paragraph is substantive for its cost-share change, but that reason is wrong.

Rates for each kind of error are in [evaluation.md](evaluation.md).

## What this is and is not

Committee report language directs agencies by convention; it does not amend law.
A flag describes a change in the committee's instructions, or, for a general provision's description, a change in proposed bill text.
Money tables are dropped rather than diffed, and flags are prompts to read, not conclusions.
See [methodology.md](methodology.md).
