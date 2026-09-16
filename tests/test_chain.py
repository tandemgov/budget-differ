"""Threading sections across years: stitching guards, row identity, anchors."""

import re
from pathlib import Path

from budget_differ.anchors import section_anchor
from budget_differ.chain import chain_from_docs
from budget_differ.compare import compare_documents
from budget_differ.corpus import CatalogEntry
from budget_differ.models import Document, Paragraph, Section
from budget_differ.render.html import _anchor, render_pair
from budget_differ.render.threads import threads_dir_name


def _doc(fy: int, specs: list[tuple[tuple[str, ...], str]]) -> Document:
    """One section per spec; newlines in the text split paragraphs."""
    doc = Document(package_id=f"PKG{fy}", chamber="house", subcommittee="Test", fiscal_year=fy)
    for i, (path, text) in enumerate(specs):
        paras = [Paragraph(text=t) for t in text.split("\n")]
        doc.sections.append(Section(heading=path[-1], level=len(path) - 1, path=path, paragraphs=paras, order=i))
    return doc


def _entry(fy: int) -> CatalogEntry:
    return CatalogEntry(
        package_id=f"PKG{fy}", congress=119, chamber="house", subcommittee="Test",
        fiscal_year=fy, stage="reported", title=f"FY{fy}", html_url="", pdf_url="",
    )


def _chain(years: dict[int, list[tuple[tuple[str, ...], str]]]):
    fys = sorted(years)
    docs = {fy: _doc(fy, years[fy]) for fy in fys}
    return chain_from_docs("house", "test", fys, docs, {fy: _entry(fy) for fy in fys})


def _row_for(chain, heading: str):
    return next(r for r in chain.rows if any(s.heading == heading for t in r.members for s in t.sections.values()))


FILLER = [
    (("TITLE I", "AGENCY", "ACCOUNT A"), "The Committee recommends funding for account A operations. " * 5),
    (("TITLE I", "AGENCY", "ACCOUNT B"), "The Committee recommends funding for account B construction. " * 5),
]


def test_short_text_inside_long_body_is_not_a_reorganization():
    """The reviewer's case: a one-line provision whose words all recur inside a long unrelated paragraph scores ~100 on token overlap. It is a drop and an add."""
    short = "Section 514 describes certain necessary conditions for reevaluation of project operations."
    long_body = (
        "The Corps is reminded that this project is eligible to compete for additional funding. "
        + short
        + " In accordance with the plan, the Corps shall continue operations at the waterway and "
        "report to the Committee on the necessary conditions for reevaluation of the project. " * 6
    )
    chain = _chain({
        2024: FILLER + [(("TITLE V", "CALIFORNIA"), short)],
        2025: FILLER + [(("TITLE I", "ARMY", "DELAWARE RIVER TO CHESAPEAKE"), long_body)],
    })
    cal, dela = _row_for(chain, "CALIFORNIA"), _row_for(chain, "DELAWARE RIVER TO CHESAPEAKE")
    assert cal is not dela
    assert cal.cells[2025].label == "dropped"
    assert dela.cells[2025].label == "new"


def test_genuine_move_across_titles_is_stitched():
    body = (
        "The Committee continues the provision prohibiting funds from being used for the approval "
        "of a new foreign air carrier permit unless the Secretary certifies compliance. " * 4
    )
    chain = _chain({
        2024: FILLER + [(("TITLE III", "RELATED AGENCIES", "AIR CARRIER PERMITS"), body)],
        2025: FILLER + [(("TITLE IV", "GENERAL PROVISIONS", "FOREIGN AIR CARRIERS"), body + " Amended.")],
    })
    row = _row_for(chain, "AIR CARRIER PERMITS")
    assert row is _row_for(chain, "FOREIGN AIR CARRIERS")
    assert row.cells[2025].label == "reorganized"


def test_section_skipping_a_year_returns():
    body = "The Committee recommends $5,000,000 for the special program and directs a report. " * 4
    spec = (("TITLE I", "AGENCY", "SPECIAL PROGRAM"), body)
    chain = _chain({2024: FILLER + [spec], 2025: FILLER, 2026: FILLER + [spec]})
    row = _row_for(chain, "SPECIAL PROGRAM")
    assert sorted(row.cells) == [2025, 2026]
    assert row.cells[2025].label == "dropped" and row.cells[2026].label == "returned"


def test_general_provision_sections_map_to_their_suffixed_row(tmp_path: Path):
    gp = (("TITLE V", "GENERAL PROVISIONS", "SEC 501"), "Section 501. The Committee continues a provision related to the Arms Trade Treaty.")
    chain = _chain({2024: FILLER + [gp], 2025: FILLER + [gp]})
    row = _row_for(chain, "SEC 501")
    assert row.key[-1] == "B2024", row.key
    keys = chain.section_row_keys()
    _, _, pair, diff = chain.transitions[0]
    sec = next(sd.new for sd in diff.sections if sd.new and sd.new.heading == "SEC 501")
    assert keys[id(sec)] == row.key
    # Every section of every year resolves to a row.
    assert all(id(s) in keys for t in chain.threads for s in t.sections.values())

    section_hrefs = {sid: f"../threads/{'_'.join(k)}.html" for sid, k in keys.items()}
    render_pair(pair, diff, tmp_path, section_hrefs=section_hrefs)
    html = (tmp_path / "index.html").read_text()
    assert f'href="../threads/{"_".join(row.key)}.html">thread history' in html


def test_anchors_unique_for_shared_prefix_and_duplicate_paths(tmp_path: Path):
    deep = ("TITLE I", "CORPS OF ENGINEERS CIVIL", "DEPARTMENT OF THE ARMY", "CONSTRUCTION", "REMAINING ITEMS ACROSS THE PROGRAM")
    specs = [
        ((*deep, "PROJECT FORMULATION AND DELIVERY"), "Formulation text. " * 5),
        ((*deep, "ADDITIONAL FUNDING"), "Additional funding text. " * 5),
        ((*deep, "NEW STARTS"), "New starts text. " * 5),
        (("TITLE II", "DUPLICATE"), "First duplicate body. " * 5),
        (("TITLE II", "DUPLICATE"), "Second duplicate body, different. " * 5),
    ]
    diff = compare_documents(_doc(2026, specs), _doc(2027, specs))
    anchors = [_anchor(sd) for sd in diff.sections]
    assert len(set(anchors)) == len(anchors) == 5
    assert all(len(a) < 80 for a in anchors)
    # Path-only links (moves, related) resolve to the first section with that path.
    first_dup = next(sd for sd in diff.sections if sd.display_path == ("TITLE II", "DUPLICATE"))
    assert _anchor(first_dup) == section_anchor(("TITLE II", "DUPLICATE"))

    render_pair(_pair(2026, 2027), diff, tmp_path)
    html = (tmp_path / "index.html").read_text()
    for a in anchors:
        assert html.count(f'id="{a}"') == 1


def test_move_and_related_links_resolve_to_the_owning_section(tmp_path: Path):
    para = "The Committee directs the Department to report on stewardship activities within 90 days. " * 3
    stub = "The Committee recommends funding for the source account. " * 5
    old = [
        (("TITLE I", "SOURCE ACCOUNT"), stub + "\n" + para),
        (("TITLE II", "DUPLICATE"), "First duplicate body. " * 5),
        (("TITLE II", "DUPLICATE"), "Second duplicate body, different. " * 5),
    ]
    new = [
        (("TITLE I", "SOURCE ACCOUNT"), stub),
        (("TITLE II", "DUPLICATE"), "First duplicate body. " * 5),
        (("TITLE II", "DUPLICATE"), "Second duplicate body, different. " * 5 + "\n" + para),
    ]
    diff = compare_documents(_doc(2026, old), _doc(2027, new))
    move = next(m for m in diff.moves if m.new_section_path == ("TITLE II", "DUPLICATE"))
    assert _anchor(move.new_sd).endswith("-2")

    render_pair(_pair(2026, 2027), diff, tmp_path)
    html = (tmp_path / "index.html").read_text()
    ids = set(re.findall(r'id="(s-[^"]+)"', html))
    targets = re.findall(r'class="movenote">[^<]*<a href="#(s-[^"]+)"', html)
    targets += re.findall(r'class="related">[^<]*<a href="#(s-[^"]+)"', html)
    assert targets and all(t in ids for t in targets), (targets, ids)
    assert _anchor(move.new_sd) in targets


def _pair(old_fy: int, new_fy: int):
    from budget_differ.corpus import Pair

    return Pair(new=_entry(new_fy), old=_entry(old_fy))


def test_thread_dir_is_scoped_to_the_chain_years():
    chain = _chain({2024: FILLER, 2025: FILLER, 2027: FILLER})
    assert threads_dir_name(chain, "test") == "house-test-threads-fy2024-fy2027"
