"""Document-order placement and outline nesting for the full-document and ranked pair pages."""

from budget_differ.diffing import diff_section_pair
from budget_differ.models import ChangeClass, Document, PairDiff, Paragraph, Section, SectionDiff
from budget_differ.render.outline import (
    build_outline,
    display_heading,
    document_order,
    paragraph_order,
)


def _sec(*path: str, paras: tuple[str, ...] = ("Text.",)) -> Section:
    return Section(heading=path[-1], level=len(path) - 1, path=path, paragraphs=[Paragraph(t) for t in paras])


def _pair(old: list[Section], new: list[Section], sds: list[SectionDiff]) -> PairDiff:
    return PairDiff(
        new_doc=Document("NEW", "house", "x", 2026, new),
        old_doc=Document("OLD", "house", "x", 2025, old),
        # Significance order is unrelated to document order.
        sections=list(reversed(sds)),
    )


def test_dropped_section_lands_after_its_old_predecessor():
    a_old, b_old, c_old = _sec("T", "A"), _sec("T", "B"), _sec("T", "C")
    a_new, c_new, d_new = _sec("T", "A"), _sec("T", "C"), _sec("T", "D")
    sds = [
        diff_section_pair(a_old, a_new),
        diff_section_pair(b_old, None),
        diff_section_pair(c_old, c_new),
        diff_section_pair(None, d_new),
    ]
    order = [sd.display_path[-1] for sd in document_order(_pair([a_old, b_old, c_old], [a_new, c_new, d_new], sds))]
    assert order == ["A", "B", "C", "D"]


def test_dropped_first_section_leads():
    z_old, a_old = _sec("T", "Z"), _sec("T", "A")
    a_new = _sec("T", "A")
    sds = [diff_section_pair(z_old, None), diff_section_pair(a_old, a_new)]
    order = [sd.display_path[-1] for sd in document_order(_pair([z_old, a_old], [a_new], sds))]
    assert order == ["Z", "A"]


def test_removed_paragraph_follows_its_predecessor():
    old = _sec("T", "A", paras=("One stays here.", "Two goes away entirely now.", "Three stays too."))
    new = _sec("T", "A", paras=("One stays here.", "Three stays too.", "Four is brand new text."))
    sd = diff_section_pair(old, new)
    texts = [(pd.new or pd.old).text for pd in paragraph_order(sd)]
    assert texts == ["One stays here.", "Two goes away entirely now.", "Three stays too.", "Four is brand new text."]
    assert paragraph_order(sd)[1].change == ChangeClass.REMOVED


def test_outline_nests_by_path_and_keeps_document_order():
    secs = [
        _sec("T"),
        _sec("T", "AGENCY", "ACCOUNT"),
        _sec("T", "SEC 101"),
        _sec("T", "AGENCY", "OTHER ACCOUNT"),
    ]
    sds = [diff_section_pair(s, s) for s in secs]
    nodes = build_outline(sds)
    assert [n.key for n in nodes] == ["T"]
    title = nodes[0]
    assert title.sd is sds[0]
    # AGENCY is interrupted by SEC 101, so it appears twice rather than pulling OTHER ACCOUNT above the provision.
    assert [c.key for c in title.children] == ["AGENCY", "SEC 101", "AGENCY"]
    assert title.children[0].sd is None and title.children[0].first_sd() is sds[1]
    assert title.children[2].children[0].sd is sds[3]


def test_duplicate_paths_get_separate_outline_entries():
    secs = [_sec("T", "SALARIES"), _sec("T", "SALARIES")]
    nodes = build_outline([diff_section_pair(s, s) for s in secs])
    assert len(nodes[0].children) == 2


def test_display_heading():
    assert display_heading("TITLE III DEPARTMENT OF ENERGY") == "Title III Department of Energy"
    assert display_heading("Salaries and Expenses") == "Salaries and Expenses"
    assert display_heading("TITLE II--GENERAL PROVISIONS") == "Title II--General Provisions"
    assert display_heading("ISOTOPE R&D AND PRODUCTION") == "Isotope R&D and Production"


def test_split_provision_nests_under_the_heading_it_was_printed_beneath():
    agency = _sec("T", "HOUSE OF REPRESENTATIVES")
    provision = Section(heading="Administrative Provisions — Section 110", level=4, path=("T", "SEC 110"), paragraphs=[Paragraph("Section 110. Text.")], printed_under=("T", "HOUSE OF REPRESENTATIVES", "ADMINISTRATIVE PROVISIONS"))
    nodes = build_outline([diff_section_pair(s, s) for s in (agency, provision)])
    house = nodes[0].children[0]
    assert house.key == "HOUSE OF REPRESENTATIVES"
    assert house.children[0].key == "ADMINISTRATIVE PROVISIONS"
    assert house.children[0].children[0].key == "SEC 110"
