"""Golden-pair and invariant tests against the sibling corpus (skipped without it)."""

import re

from budget_differ.compare import compare_documents, load_document
from budget_differ.corpus import load_catalog
from budget_differ.models import ChangeClass

from conftest import approps_repo_or_none, requires_corpus


@requires_corpus
def test_self_diff_is_all_unchanged():
    repo = approps_repo_or_none()
    cat = {e.package_id: e for e in load_catalog(repo)}
    doc_a = load_document(repo, cat["CRPT-119hrpt667"])
    doc_b = load_document(repo, cat["CRPT-119hrpt667"])
    pair = compare_documents(doc_a, doc_b)
    assert all(sd.change == ChangeClass.UNCHANGED for sd in pair.sections)


@requires_corpus
def test_house_energy_water_golden_pair():
    repo = approps_repo_or_none()
    cat = {e.package_id: e for e in load_catalog(repo)}
    old = load_document(repo, cat["CRPT-119hrpt213"])  # FY2026
    new = load_document(repo, cat["CRPT-119hrpt667"])  # FY2027
    assert len(old.sections) > 50 and len(new.sections) > 50

    pair = compare_documents(old, new)
    counts = pair.counts()
    total = sum(counts.values())
    # Most sections recur year over year; real drops (GP 506-512, DOE reorg) exist.
    assert counts.get("unchanged", 0) + counts.get("numbers only", 0) > 20
    assert counts.get("dropped", 0) >= 5
    assert counts.get("new", 0) >= 3
    assert counts.get("dropped", 0) + counts.get("new", 0) < total * 0.35

    # FY2027 verifiably ends Title V at Sec. 505; 506-512 must show as dropped.
    dropped_paths = {sd.old.path for sd in pair.sections if sd.change == ChangeClass.REMOVED}
    assert ("TITLE V GENERAL PROVISIONS", "SEC 506") in dropped_paths

    # The FY2027 DOE reorg renamed COAL AND CARBON UTILIZATION -> COAL with partial content carryover: mutual best match at 69% with the same parent, so it must be promoted to a real word-level diff labeled as a rename — not drop+add.
    coal = next(sd for sd in pair.sections if sd.new and sd.new.path[-1] == "COAL")
    assert coal.renamed_from is not None
    assert "COAL AND CARBON UTILIZATION" in coal.renamed_from.upper()
    assert coal.change not in (ChangeClass.ADDED, ChangeClass.REMOVED)
    assert coal.paragraph_diffs  # real paragraph-level diffs exist

    # Below the promote bar, hints remain: at least one dropped/new section still carries a possible-successor/predecessor link.
    assert any(sd.related for sd in pair.sections)

    # The Advanced Materials directive ($25M MDF/Carbon Fiber) moved verbatim from ENERGY EFFICIENCY into CRITICAL MINERALS, MATERIALS, AND MANUFACTURING; it must surface as a paragraph move, not as an unrelated deletion plus addition.
    mdf = next(
        m for m in pair.moves if m.diff.new and "Manufacturing Demonstration" in m.diff.new.text
    )
    assert mdf.old_section_path[-1] == "ENERGY EFFICIENCY"
    assert mdf.new_section_path[-1] == "CRITICAL MINERALS MATERIALS AND MANUFACTURING"
    assert mdf.diff.change == ChangeClass.UNCHANGED


@requires_corpus
def test_hierarchy_flagship_paths():
    """Lineages that each caught a real tree-building bug; pin them."""
    repo = approps_repo_or_none()
    cat = {e.package_id: e for e in load_catalog(repo)}

    fsgg27 = load_document(repo, cat["CRPT-119hrpt623"])  # House FSGG FY2027
    edp = next(s for s in fsgg27.sections if s.path[-1] == "ENTREPRENEURIAL DEVELOPMENT PROGRAMS")
    assert edp.path[0] == "TITLE V INDEPENDENT AGENCIES"  # not the DC title
    assert "SMALL BUSINESS ADMINISTRATION" in edp.path

    # Title II's heading wraps at full width and starts at column 1; OMB must still land under it, not under Title I (Treasury).
    omb = next(
        s for s in fsgg27.sections if "OFFICE OF MANAGEMENT AND BUDGET" in " ".join(s.path)
    )
    assert omb.path[0].startswith("TITLE II EXECUTIVE OFFICE OF THE PRESIDENT")

    srpt61 = load_document(repo, cat["CRPT-118srpt61"])  # Senate FSGG FY2024
    tax = next(s for s in srpt61.sections if s.path[-1] == "TAXPAYER SERVICES")
    assert "INTERNAL REVENUE SERVICE" in tax.path
    assert "TAX ADMINISTRATION" not in " ".join(tax.path)  # not under TIGTA

    srpt206 = load_document(repo, cat["CRPT-118srpt206"])  # Senate FSGG FY2025
    postal = next(
        s for s in srpt206.sections if s.path[-1] == "PAYMENT TO THE POSTAL SERVICE FUND"
    )
    assert "UNITED STATES POSTAL SERVICE" in postal.path
    assert "SMALL BUSINESS ADMINISTRATION" not in postal.path


@requires_corpus
def test_senate_report_segments():
    repo = approps_repo_or_none()
    cat = {e.package_id: e for e in load_catalog(repo)}
    doc = load_document(repo, cat["CRPT-116srpt102"])  # Senate Energy-Water FY2020
    assert len(doc.sections) > 30
    text = " ".join(p.text for s in doc.sections for p in s.paragraphs)
    assert "......" not in text  # no leader-table leakage into paragraphs


@requires_corpus
def test_house_energy_water_chain_invariants(tmp_path):
    """FY2024–2027 House Energy-Water: the cases from the timeline review, pinned."""
    from budget_differ.chain import build_chain
    from budget_differ.render.html import _anchor, render_pair

    chain = build_chain(approps_repo_or_none(), "house", "energy-water", 2024, 2027)
    assert chain.fys == [2024, 2025, 2026, 2027]

    # A one-line FY2024 California provision is not the predecessor of an FY2025 Corps waterway paragraph that happens to contain its words.
    def paths(row):
        return {" > ".join(s.path) for t in row.members for s in t.sections.values()}

    cal = next(r for r in chain.rows if "TITLE V WATER FOR CALIFORNIA > SEC 514" in paths(r))
    assert not any("DELAWARE" in p for p in paths(cal))
    assert cal.cells[2025].label == "dropped"

    # Every section of every year belongs to a row, general provisions included, so pair pages can link each one to its thread history.
    keys = chain.section_row_keys()
    for fy, _, _, diff in chain.transitions:
        for sd in diff.sections:
            sec = sd.new or sd.old
            assert id(sec) in keys, (fy, sec.path)
            if sec.path[-1].startswith("SEC "):
                assert keys[id(sec)][-1].startswith("B"), keys[id(sec)]

    # Anchors are unique within each pair page even where long paths share an 80-character prefix.
    for _, _, _, diff in chain.transitions:
        anchors = [_anchor(sd) for sd in diff.sections]
        assert len(set(anchors)) == len(anchors)

    # Move and related-section links resolve to an id on the page, including moves into the second of two duplicate paths.
    for _, _, pair, diff in chain.transitions:
        render_pair(pair, diff, tmp_path / pair.slug())
        html = (tmp_path / pair.slug() / "index.html").read_text()
        ids = set(re.findall(r'id="(s-[^"]+)"', html))
        links = re.findall(r'class="(?:movenote|related)">[^<]*<a href="#(s-[^"]+)"', html)
        assert links and all(t in ids for t in links), [t for t in links if t not in ids]


@requires_corpus
def test_legislative_branch_hierarchy():
    repo = approps_repo_or_none()
    cat = {e.package_id: e for e in load_catalog(repo)}
    doc = load_document(repo, cat["CRPT-119hrpt178"])  # House Legislative Branch FY2026
    paths = [s.path for s in doc.sections]
    agencies = {"CONGRESSIONAL BUDGET OFFICE", "ARCHITECT OF THE CAPITOL", "LIBRARY OF CONGRESS", "GOVERNMENT PUBLISHING OFFICE", "JOINT ITEMS", "HOUSE OF REPRESENTATIVES"}
    # Each agency sits directly under the title, never under the agency printed before it.
    assert not [p for p in paths if sum(c in agencies for c in p) > 1]
    botanic = next(p for p in paths if p[-1] == "BOTANIC GARDEN")
    assert botanic[-2] == "ARCHITECT OF THE CAPITOL"
    assert any(p[-2:] == ("COPYRIGHT OFFICE", "SALARIES AND EXPENSES") for p in paths)
    assert not any(p[-1].startswith(("INCLUDING", "EXCLUDING")) for p in paths)


@requires_corpus
def test_energy_water_hierarchy():
    repo = approps_repo_or_none()
    cat = {e.package_id: e for e in load_catalog(repo)}
    doc = load_document(repo, cat["CRPT-119hrpt213"])  # House Energy-Water FY2026
    paths = [s.path for s in doc.sections]
    # Listed with the other independent agencies in the report's index, so it must not nest under the commission printed before it.
    gla = next(p for p in paths if p[-1] == "GREAT LAKES AUTHORITY")
    assert gla[-2] == "TITLE IV INDEPENDENT AGENCIES"
    # A sentence listing DOE programs wraps into capitalized lines; none may become a section.
    assert not any(";" in s.heading for s in doc.sections)
