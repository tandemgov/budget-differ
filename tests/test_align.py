from budget_differ.align import align_sections
from budget_differ.models import Document, Paragraph, Section


def _doc(specs: list[tuple[tuple[str, ...], str]]) -> Document:
    doc = Document(package_id="X", chamber="house", subcommittee="test", fiscal_year=2027)
    for i, (path, text) in enumerate(specs):
        doc.sections.append(
            Section(
                heading=path[-1],
                level=len(path) - 1,
                path=path,
                paragraphs=[Paragraph(text=text)],
                order=i,
            )
        )
    return doc


def test_exact_path_match():
    old = _doc([(("TITLE I", "ACCOUNT A"), "text a"), (("TITLE I", "ACCOUNT B"), "text b")])
    new = _doc([(("TITLE I", "ACCOUNT A"), "text a2"), (("TITLE I", "ACCOUNT B"), "text b2")])
    matched, removed, added = align_sections(old, new)
    assert len(matched) == 2 and not removed and not added


def test_unique_heading_match_survives_parent_drift():
    old = _doc([(("TITLE I", "EXPENSES", "SPECIAL PROGRAM"), "the program text")])
    new = _doc([(("TITLE I", "SPECIAL PROGRAM"), "the program text revised")])
    matched, removed, added = align_sections(old, new)
    assert len(matched) == 1 and not removed and not added


def test_added_and_removed_detected():
    old = _doc([(("TITLE I", "OLD ONLY"), "x" * 50)])
    new = _doc([(("TITLE I", "NEW ONLY"), "y" * 50)])
    matched, removed, added = align_sections(old, new)
    assert not matched and len(removed) == 1 and len(added) == 1


def test_fuzzy_rename_same_parent():
    body = (
        "The Committee recommends funding for water infrastructure projects including "
        "levees, dredging, and coastal resiliency across the nation." * 3
    )
    old = _doc([(("TITLE I", "WATER INFRASTRUCTURE PROGRAM"), body)])
    new = _doc([(("TITLE I", "WATER INFRASTRUCTURE FINANCE PROGRAM"), body + " Updated.")])
    matched, removed, added = align_sections(old, new)
    assert len(matched) == 1 and not removed and not added


def test_lightly_edited_paragraph_moved_to_reorganized_account_is_a_move():
    """A paragraph edited by a word while moving to another account reads as a move, not a drop plus an addition."""
    from budget_differ.compare import compare_documents
    from budget_differ.models import Document, Paragraph, Section

    body = (
        "The Committee directs the Department to continue to conduct research and development on high-precision "
        "hydrogen-sensing technologies for leakage mitigation and safety at production and storage facilities."
    )
    stay_a = Paragraph("The Committee supports the program and its ongoing research activities across the laboratories.")
    stay_b = Paragraph("The recommendation continues support for methane emissions quantification at producing wells nationwide.")

    def doc(fy: int, a: list[Paragraph], b: list[Paragraph]) -> Document:
        return Document(
            package_id=f"P{fy}",
            chamber="house",
            subcommittee="energy-water",
            fiscal_year=fy,
            sections=[
                Section(heading="OFFICE A", level=2, path=("TITLE III", "OFFICE A"), paragraphs=a, order=0),
                Section(heading="OFFICE B", level=2, path=("TITLE III", "OFFICE B"), paragraphs=b, order=1),
            ],
        )

    old = doc(2026, [stay_a], [Paragraph(body), stay_b])
    new = doc(2027, [stay_a, Paragraph(body.replace("continue to conduct", "conduct"))], [stay_b])
    pair = compare_documents(old, new)
    assert len(pair.moves) == 1
    assert pair.moves[0].diff.old.text == body
