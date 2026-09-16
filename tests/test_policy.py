"""Regression tests for policy-sensitive edits: small wording changes that must not be filed as minor or number-only."""

import pytest

from budget_differ.diffing import diff_section_pair
from budget_differ.models import ChangeClass, Paragraph, Section
from budget_differ.policy import REVIEW, describe_paragraph


def _pair(old: str, new: str, kind: str = "directive"):
    def sec(text: str) -> Section:
        return Section(heading="T", level=2, path=("TITLE I", "T"), paragraphs=[Paragraph(text, kind, "Topic")])

    sd = diff_section_pair(sec(old), sec(new))
    assert len(sd.paragraph_diffs) == 1
    return sd.paragraph_diffs[0]


def _review(pd) -> set[str]:
    return {f.category for f in pd.flags if f.tier >= REVIEW}


# (old, new, category): the review's four cases first, then edits seen in the demonstration reports.
POLICY_EDITS = [
    (
        "The Committee directs the Department to fund the program.",
        "The Committee directs the Department to not fund the program.",
        "negation",
    ),
    (
        "The Secretary may issue guidance on the program.",
        "The Secretary shall issue guidance on the program.",
        "discretion",
    ),
    (
        "The Committee directs the Department to provide a report within 90 days of enactment.",
        "The Committee directs the Department to provide a report within 180 days of enactment.",
        "deadline",
    ),
    (
        "The demonstration shall be limited to 10 sites.",
        "The demonstration shall be limited to 100 sites.",
        "limit",
    ),
    (
        "The Committee directs the Department to brief the Committee not later than 30 days after enactment of this Act.",
        "The Committee directs the Department to brief the Committee not later than 60 days after the date of enactment of this Act.",
        "deadline",
    ),
    (
        "Inland waterways construction is funded 65 percent from the general fund and 35 percent from the Trust Fund.",
        "Inland waterways construction is funded 75 percent from the general fund and 25 percent from the Trust Fund.",
        "share",
    ),
    (
        "The recommendation provides not less than $65,000,000 for deployment through the Clean Cities program.",
        "The recommendation provides not less than $60,000,000 for deployment through the Clean Cities program.",
        "limit",
    ),
    (
        "The recommendation includes up to $20,000,000 to continue these efforts.",
        "The recommendation includes $10,000,000 to continue these efforts.",
        "limit",
    ),
    (
        "The recommendation includes $3,000,000 for this program to support additional flights.",
        "The recommendation includes $3,000,000 for this program to support only additional flights.",
        "eligibility",
    ),
    (
        "The Office of Inspector General supports no fewer than 15 FTE within the office.",
        "The Office of Inspector General supports no fewer than 18 FTE within the office.",
        "limit",
    ),
    (
        "The Committee encourages EIA to consider increasing the detail and frequency of these surveys.",
        "The Committee encourages EIA to increase the detail and frequency of these surveys.",
        "discretion",
    ),
    (
        "Funds may be used for the cleanup of the site.",
        "None of the funds may be used for the cleanup of the site.",
        "prohibition",
    ),
    (
        "The Corps shall award the contract.",
        "The Corps shall award the contract unless the Secretary certifies a cost overrun.",
        "condition",
    ),
    (
        "The Committee directs the agency to consult with stakeholders.",
        "The Committee directs the agency to consult with stakeholders and submit a report on the results.",
        "reporting",
    ),
    (
        "The recommendation includes $3,400,000 for the project, which is expected to be complete in fiscal year 2027.",
        "The recommendation includes $3,400,000 for the project, which is expected to be complete in fiscal year 2030.",
        "deadline",
    ),
    (
        "Section 118 limits to $318,789,000 the amount that may be obligated during fiscal year 2025.",
        "Section 118 limits to $332,285,000 the amount that may be obligated during fiscal year 2025.",
        "limit",
    ),
    (
        "Section 301 continues a provision regarding reprogramming notifications.",
        "Section 301 continues and modifies a provision regarding reprogramming notifications.",
        "provision",
    ),
    (
        "The recommendation includes $61,500,000 for seven sections to undertake small projects.",
        "The recommendation includes $61,500,000 for nine sections to undertake small projects.",
        "quantity",
    ),
]


@pytest.mark.parametrize("old,new,category", POLICY_EDITS)
def test_policy_edit_flagged_and_promoted(old, new, category):
    pd = _pair(old, new)
    assert category in _review(pd), [(f.category, f.reason) for f in pd.flags]
    assert pd.change == ChangeClass.SUBSTANTIVE
    flag = next(f for f in pd.flags if f.category == category)
    # Every flag carries the language it is about on both sides, so a reader can verify it.
    assert flag.reason
    assert flag.before[1] or flag.after[1]


def test_reviewer_cases_were_previously_filed_low():
    """The size-only class is kept alongside the promoted one; these are the classifications the review found indefensible."""
    literal = [_pair(old, new).literal_change for old, new, _ in POLICY_EDITS[:4]]
    assert literal == [ChangeClass.MINOR, ChangeClass.MINOR, ChangeClass.NUMBERS_ONLY, ChangeClass.NUMBERS_ONLY]


EDITORIAL_EDITS = [
    ("The nation's ports are critical.", "The Nation's ports are critical."),
    ("The Committee supports biofilm based research.", "The Committee supports biofilm-based research."),
    (
        "The Committee directs the Corps to brief the Committee on the results.",
        "The Corps is directed to brief the Committee on the results.",
    ),
    (
        "The Department of Energy shall coordinate with the National Nuclear Security Administration.",
        "The Department of Energy shall coordinate with NNSA.",
    ),
    ("The Committee continues to support the program in fiscal year 2026.", "The Committee continues to support the program in fiscal year 2027."),
    ("Section 317 of this Act extends the authority.", "Section 313 of this Act extends the authority."),
    (
        "Of the total, $28,200,000 shall remain available until September 30, 2029.",
        "Of the total, $28,200,000 shall remain available until September 30, 2030.",
    ),
    ("The recommendation includes $12,040,000 for Nuclear Waste Disposal.", "The Committee recommends $12,040,000 for Nuclear Waste Disposal."),
]


@pytest.mark.parametrize("old,new", EDITORIAL_EDITS)
def test_editorial_edit_not_promoted(old, new):
    pd = _pair(old, new)
    assert not _review(pd), [(f.category, f.reason) for f in pd.flags]
    assert pd.change in (ChangeClass.MINOR, ChangeClass.NUMBERS_ONLY)


def test_plain_dollar_change_is_annotated_not_promoted():
    pd = _pair("Of the amount, $25,000,000 is for dam safety.", "Of the amount, $20,000,000 is for dam safety.")
    assert pd.change == ChangeClass.NUMBERS_ONLY
    assert [f.category for f in pd.flags] == ["funding"]
    assert "$25,000,000 → $20,000,000" in pd.flags[0].reason


def test_unexplained_substitution_is_noted():
    pd = _pair(
        "Funds are provided for the construction project at the site.",
        "Funds are provided for the feasibility study at the site.",
    )
    assert "wording" in {f.category for f in pd.flags}


def test_describe_new_paragraph():
    tags = describe_paragraph(
        "None of the funds may be used to close the office. The Committee directs a report within 90 days."
    )
    assert "prohibition" in tags
    assert "deadline" in tags
    assert "reporting requirement" in tags
