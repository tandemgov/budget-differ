from budget_differ.diffing import diff_section_pair, mask
from budget_differ.models import ChangeClass, Paragraph, Section


def _section(texts: list[str]) -> Section:
    return Section(
        heading="TEST",
        level=2,
        path=("TITLE I", "TEST"),
        paragraphs=[Paragraph(text=t) for t in texts],
    )


def test_mask_dollars_and_years():
    a = mask("The Committee recommends $48,931,662,000 for fiscal year 2020.")
    b = mask("The Committee recommends $50,000,000,000 for fiscal year 2021.")
    assert a == b


def test_identical_sections_unchanged():
    sd = diff_section_pair(_section(["Alpha beta gamma."]), _section(["Alpha beta gamma."]))
    assert sd.change == ChangeClass.UNCHANGED


def test_numbers_only_change():
    sd = diff_section_pair(
        _section(["The Committee recommends $1,000,000 for 2026."]),
        _section(["The Committee recommends $2,500,000 for 2027."]),
    )
    assert sd.change == ChangeClass.NUMBERS_ONLY


def test_substantive_change():
    sd = diff_section_pair(
        _section(["The Committee supports the program and directs a report on staffing."]),
        _section(
            [
                "The Committee eliminates the program entirely and rescinds all prior "
                "year balances, directing the Department to wind down operations."
            ]
        ),
    )
    assert sd.change == ChangeClass.SUBSTANTIVE
    assert sd.changed_words > 5


def test_added_and_removed_sections():
    assert diff_section_pair(None, _section(["New text."])).change == ChangeClass.ADDED
    assert diff_section_pair(_section(["Old text."]), None).change == ChangeClass.REMOVED


def test_word_opcodes_present_on_change():
    sd = diff_section_pair(
        _section(["The Committee directs a report within 90 days."]),
        _section(["The Committee directs a briefing within 60 days."]),
    )
    pd = sd.paragraph_diffs[0]
    assert pd.opcodes
    tags = {t for t, _, _ in pd.opcodes}
    assert "equal" in tags and ("replace" in tags or "insert" in tags or "delete" in tags)


def test_unrelated_directives_are_not_paired():
    """Two different directives in the same slot must read as one dropped and one new, not as a rewrite of each other."""
    old = Section(
        heading="TEST",
        level=2,
        path=("TITLE I", "TEST"),
        paragraphs=[
            Paragraph(
                "Image Feasibility Study.--The Committee directs the Office of the Clerk to study incorporating images such as blueprints into the bill drafting process.",
                "directive",
                "Image Feasibility Study",
            )
        ],
    )
    new = Section(
        heading="TEST",
        level=2,
        path=("TITLE I", "TEST"),
        paragraphs=[
            Paragraph(
                "Traffic Signals Evaluation.--The Committee requests the Sergeant at Arms evaluate traffic signals at designated entry points to improve safety.",
                "directive",
                "Traffic Signals Evaluation",
            )
        ],
    )
    sd = diff_section_pair(old, new)
    assert sorted(pd.change for pd in sd.paragraph_diffs) == [ChangeClass.ADDED, ChangeClass.REMOVED]
