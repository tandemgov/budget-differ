"""Committee-website PDF ingestion (budget_differ.ingest) and the prerelease catalog."""

from __future__ import annotations

from pathlib import Path

import pytest

from budget_differ.ingest import _dehyphen_join, _wrap_heading, load_prerelease, prerelease_dir

fitz = pytest.importorskip("fitz")


@pytest.mark.parametrize(
    ("lines", "vocab", "expected"),
    [
        (["shall be accom-", "plished in the manner"], set(), "shall be accomplished in the manner"),
        (["the Lewis-", "Houghton Award"], set(), "the Lewis-Houghton Award"),
        (["the day-to-", "day operation"], {"day", "today"}, "the day-to-day operation"),
        (["for non-con-", "fidential use"], {"confidential"}, "for non-confidential use"),
        (["Public Law 95-", "94, August 5"], set(), "Public Law 95-94, August 5"),
        (["Traditions.—", "The LOC"], set(), "Traditions.—The LOC"),
        (["home-", "to-work vehicles"], set(), "home-to-work vehicles"),
        (["SENATORS' OFFI-", "CIAL PERSONNEL"], set(), "SENATORS' OFFICIAL PERSONNEL"),
    ],
)
def test_dehyphen_join(lines, vocab, expected):
    assert _dehyphen_join(lines, vocab) == expected


def test_wrapped_heading_lines_open_on_capitals():
    lines = _wrap_heading("Public Information Programs of the Office of Superintendent of Documents", 59)
    assert len(lines) == 2
    assert all(ln[0].isupper() for ln in lines)
    assert " ".join(lines) == "Public Information Programs of the Office of Superintendent of Documents"


def _prerelease(package_id: str) -> Path:
    pdf = prerelease_dir() / f"{package_id}.pdf"
    if not pdf.exists():
        pytest.skip(f"{pdf} not present")
    return pdf


def test_explanatory_statement_converts_to_gpo_layout():
    from budget_differ.ingest import pdf_to_gpo_text

    text = pdf_to_gpo_text(_prerelease("SAPPR-FY2027-LEGBRANCH-ES"))
    lines = text.splitlines()
    # Full-size caps heads stay CAPS; small-caps heads come out in Title Case, centered, as in GovInfo's .htm.
    assert "                                 SENATE" in lines
    assert "                           Expense Allowances" in lines
    # Dot-leader funding summaries keep stub and amount on one line.
    assert any(ln.startswith("Appropriations, 2026....") and ln.endswith("$195,000") for ln in lines)
    # Typographic punctuation is mapped to GPO's ASCII forms, and page folios are gone.
    assert "Member Security.--The Committee" in text
    assert "’" not in text and "—" not in text
    assert "(57)" not in lines


def test_bill_print_drops_line_numbers_and_running_heads():
    from budget_differ.ingest import pdf_to_gpo_text

    text = pdf_to_gpo_text(_prerelease("SAPPR-FY2027-LEGBRANCH-BILL"))
    assert "SEN. APPRO." not in text and "LBFY2027" not in text
    assert "    For the Office of the Vice President, $3,307,000." in text.splitlines()
    assert "    Sec. 101. Notwithstanding any other provision of law, any" in text.splitlines()


def test_prerelease_entries_join_the_catalog():
    from budget_differ.config import approps_repo
    from budget_differ.corpus import load_catalog, raw_path

    entries = load_prerelease()
    if not entries:
        pytest.skip("no prerelease catalog")
    try:
        repo = approps_repo()
    except FileNotFoundError:
        pytest.skip("approps repo absent")
    by_id = {e.package_id: e for e in load_catalog(repo)}
    for row in entries:
        entry = by_id[row["package_id"]]
        assert entry.local_path
        assert raw_path(repo, entry) == prerelease_dir() / row["local_path"]


def _entry(package_id: str, fy: int, local_path: str = ""):
    from budget_differ.corpus import CatalogEntry

    return CatalogEntry(package_id, 119, "senate", "Legislative-Branch", fy, "committee", "", "", local_path=local_path)


def test_prerelease_chain_reads_every_year_from_pdf():
    from budget_differ.chain import like_for_like

    entries = {2025: _entry("A", 2025), 2026: _entry("B", 2026), 2027: _entry("P", 2027, "P.htm")}
    kept, skipped = like_for_like(entries, lambda e: True)
    assert skipped == []
    assert kept[2025].from_pdf and kept[2026].from_pdf and not kept[2027].from_pdf


def test_prerelease_chain_skips_years_without_a_pdf():
    from budget_differ.chain import like_for_like

    entries = {2025: _entry("A", 2025), 2026: _entry("B", 2026), 2027: _entry("P", 2027, "P.htm")}
    kept, skipped = like_for_like(entries, lambda e: e.package_id != "B")
    assert sorted(kept) == [2025, 2027]
    assert [fy for fy, _ in skipped] == [2026]


def test_chain_without_prerelease_is_untouched():
    from budget_differ.chain import like_for_like

    entries = {2025: _entry("A", 2025), 2026: _entry("B", 2026)}
    kept, skipped = like_for_like(entries, lambda e: False)
    assert skipped == [] and not any(e.from_pdf for e in kept.values())
