from budget_differ.segment import segment_report

SAMPLE = """<html>
<title>House Report 999-1 - EXAMPLE APPROPRIATIONS BILL, 2027</title>
<body><pre>
[House Report 999-1]

                                CONTENTS

                                                                   Page
Introduction.....................................................     2
Title I..........................................................     3

                              INTRODUCTION

    The Committee recommends funding for the programs described
below.

                     TITLE I--DEPARTMENT OF EXAMPLE

                        OFFICE OF DEMONSTRATIONS

                         SALARIES AND EXPENSES

Appropriations, 2026....................................  $1,000,000
Budget estimate, 2027...................................   1,100,000
Committee recommendation................................   1,200,000

    The Committee recommends $1,200,000 for Salaries and
Expenses, an increase of $200,000 above fiscal year 2026.
    Widget Modernization.--The Committee directs the Office to
report on widget modernization within 90 days.

                           GENERAL PROVISIONS

    Section 101. The bill includes language on transfers of
funds between accounts.
    Section 102. The bill includes language prohibiting
first-class travel.
</pre></body></html>
"""


def _segment():
    return segment_report(SAMPLE, package_id="TEST", chamber="house", fiscal_year=2027)


def test_headings_and_paths():
    doc = _segment()
    paths = [s.path for s in doc.sections]
    assert ("INTRODUCTION",) in paths
    assert any(p[-1] == "SALARIES AND EXPENSES" for p in paths)
    sal = next(s for s in doc.sections if s.path[-1] == "SALARIES AND EXPENSES")
    assert sal.path[0] == "TITLE I DEPARTMENT OF EXAMPLE"
    assert "OFFICE OF DEMONSTRATIONS" in sal.path


def test_money_table_dropped_and_flagged():
    doc = _segment()
    sal = next(s for s in doc.sections if s.path[-1] == "SALARIES AND EXPENSES")
    assert sal.table_spans >= 1
    joined = " ".join(p.text for p in sal.paragraphs)
    assert "Budget estimate" not in joined


def test_paragraph_unwrapped():
    doc = _segment()
    sal = next(s for s in doc.sections if s.path[-1] == "SALARIES AND EXPENSES")
    narrative = sal.paragraphs[0].text
    assert "Salaries and Expenses" in narrative  # rejoined across the hard wrap
    assert "\n" not in narrative


def test_directive_topic_detected():
    doc = _segment()
    sal = next(s for s in doc.sections if s.path[-1] == "SALARIES AND EXPENSES")
    directive = next(p for p in sal.paragraphs if p.kind == "directive")
    assert directive.topic == "Widget Modernization"


def test_general_provisions_split():
    doc = _segment()
    gp_paths = [s.path for s in doc.sections if s.paragraphs and s.paragraphs[0].kind == "gp_section"]
    assert len(gp_paths) == 2
    assert all(p[-1].startswith("SEC") for p in gp_paths)


def test_front_matter_excluded():
    doc = _segment()
    all_text = " ".join(p.text for s in doc.sections for p in s.paragraphs)
    assert "Page" not in all_text.split("CONTENTS")[0] or "CONTENTS" not in all_text


def _center(text: str) -> str:
    return " " * max(6, (70 - len(text)) // 2) + text


def _report(body_lines: list[str]) -> str:
    return "<html><body><pre>\n" + "\n".join(body_lines) + "\n</pre></body></html>"


LEG_BRANCH = _report(
    [
        _center("TITLE I--LEGISLATIVE BRANCH APPROPRIATIONS"),
        "",
        _center("CONGRESSIONAL BUDGET OFFICE"),
        "",
        _center("Salaries and Expenses"),
        "",
        "    The Committee recommends funding for the Congressional Budget",
        "Office.",
        "",
        _center("ARCHITECT OF THE CAPITOL"),
        "",
        _center("Capital Construction and Operations"),
        "",
        "    The Committee recommends funding for capital construction.",
        "",
        _center("Capitol Police Buildings, Grounds, and Security"),
        "",
        "    The Committee recommends funding for Capitol Police buildings.",
        "",
        _center("Botanic Garden"),
        "",
        "    The Committee recommends funding for the Botanic Garden.",
        "    Road Conditions Surrounding the House Office Buildings.--To",
        "mitigate traffic concerns, the Committee encourages the AOC to act.",
        "",
        _center("LIBRARY OF CONGRESS"),
        "",
        _center("Copyright Office"),
        "",
        _center("Salaries and Expenses"),
        "",
        _center("(INCLUDING TRANSFER OF FUNDS)"),
        "",
        "    The Committee recommends funding for the Copyright Office.",
    ]
)


def _leg_paths():
    doc = segment_report(LEG_BRANCH, package_id="LEG", chamber="house", subcommittee="Legislative-Branch", fiscal_year=2027)
    return {s.heading: s.path for s in doc.sections}


def test_legislative_agencies_are_siblings():
    paths = _leg_paths()
    assert "CONGRESSIONAL BUDGET OFFICE" not in paths["Capital Construction and Operations"]
    assert paths["Capital Construction and Operations"][-2] == "ARCHITECT OF THE CAPITOL"


def test_account_named_after_agency_is_not_a_bureau():
    paths = _leg_paths()
    # CAPITOL POLICE + trailing words is an Architect of the Capitol account, not a sub-entity that would adopt Botanic Garden.
    assert paths["Botanic Garden"][-2] == "ARCHITECT OF THE CAPITOL"


def test_legislative_bureau_owns_its_account_and_parenthetical_merges():
    doc = segment_report(LEG_BRANCH, package_id="LEG", chamber="house", subcommittee="Legislative-Branch", fiscal_year=2027)
    copyright_se = [s for s in doc.sections if s.path[-2:] == ("COPYRIGHT OFFICE", "SALARIES AND EXPENSES")]
    assert len(copyright_se) == 1
    assert "Copyright Office" in copyright_se[0].paragraphs[0].text
    assert not any("INCLUDING" in s.path[-1] for s in doc.sections)


def test_directive_lead_in_is_not_a_heading():
    paths = _leg_paths()
    assert not any("ROAD CONDITIONS" in p[-1] for p in paths.values())


def test_legislative_names_only_pin_in_legislative_reports():
    # Other subcommittees print SENATE and HOUSE OF REPRESENTATIVES over committee-procedure sections; there the names must not pin the agency tier.
    doc = segment_report(LEG_BRANCH, package_id="X", chamber="house", subcommittee="Energy-Water", fiscal_year=2027)
    cbo = next(s for s in doc.sections if s.paragraphs and "Congressional Budget" in s.paragraphs[0].text)
    assert cbo.level != 1 and all(s.level != 1 for s in doc.sections)


def test_capitalized_prose_line_is_not_a_heading():
    doc = segment_report(
        _report(
            [
                _center("TITLE III--DEPARTMENT OF ENERGY"),
                "",
                "    Funds recommended in Title III provide for all Department",
                "of Energy programs, including Environmental Cleanup; Uranium",
                "Decommissioning Fund; Science; Nuclear Waste Disposal; Advanced",
                "Research Projects Agency--Energy; and the Office of the",
                "Inspector General.",
            ]
        ),
        package_id="DOE",
        chamber="house",
        fiscal_year=2027,
    )
    assert [s.path for s in doc.sections] == [("TITLE III DEPARTMENT OF ENERGY",)]


def test_toc_parent_with_page_number_does_not_swallow_next_entry():
    from budget_differ.segment.toc import parse_toc

    lines = [
        "INDEX TO BILL AND REPORT",
        "",
        "Title I--Legislative Branch Appropriations.................     2",
        "        House of Representatives...........................     3",
        "        Joint Items:                                           14",
        "                Joint Economic Committee...................    14",
        "                Office of the Attending Physician..........    13",
        "        Architect of the Capitol (except Senate Office ",
        "            Buildings).....................................    20",
    ]
    texts = [e.text for e in parse_toc(lines)]
    assert "Joint Items:" not in texts and "Joint Items" in texts
    assert "Joint Economic Committee" in texts


def test_toc_entry_snaps_to_qualified_body_heading():
    from budget_differ.segment.builder import _toc_keys

    headings = ["ARCHITECT OF THE CAPITOL", "CONGRESSIONAL OFFICE FOR INTERNATIONAL LEADERSHIP", "SALARIES AND EXPENSES", "SALARIES AND EXPENSES"]
    keys = _toc_keys(
        [
            "Architect of the Capitol (except Senate Office Buildings)",
            "Congressional Office for International Leadership Fund",
            "Salaries",
        ],
        headings,
    )
    assert keys[:2] == ["ARCHITECT OF THE CAPITOL", "CONGRESSIONAL OFFICE FOR INTERNATIONAL LEADERSHIP"]
    # Never snap to a heading printed more than once.
    assert keys[2] == "SALARIES"


def test_wrapped_heading_split_by_blank_lines_rejoins():
    doc = segment_report(
        _report(
            [
                _center("TITLE I--LEGISLATIVE BRANCH APPROPRIATIONS"),
                "",
                _center("HOUSE OF REPRESENTATIVES"),
                "",
                "       Allowance for Compensation of Interns in House Leadership",
                "",
                "",
                _center("Offices"),
                "",
                "    The Committee recommends funding for interns.",
            ]
        ),
        package_id="LEG",
        chamber="house",
        subcommittee="Legislative-Branch",
        fiscal_year=2027,
    )
    assert doc.sections[-1].path[-1] == "ALLOWANCE FOR COMPENSATION OF INTERNS IN HOUSE LEADERSHIP OFFICES"


def test_wrapped_contents_entry_is_not_a_heading():
    # Body bounds can start inside the contents; the first half of a wrapped entry must not become an agency that adopts the report.
    doc = segment_report(
        _report(
            [
                "        Congressional Office for International Leadership ",
                "            Fund...........................................    32    29",
                "Title II--General Provisions...............................    33    29",
                "",
                _center("HIGHLIGHTS OF THE BILL"),
                "",
                "    The Committee recommendation totals $5,440,881,000.",
            ]
        ),
        package_id="LEG",
        chamber="house",
        subcommittee="Legislative-Branch",
        fiscal_year=2027,
    )
    assert [s.path for s in doc.sections] == [("HIGHLIGHTS OF THE BILL",)]


def _plain(lines: list[str], **kw):
    kw.setdefault("package_id", "T")
    kw.setdefault("chamber", "house")
    kw.setdefault("fiscal_year", 2027)
    return segment_report(_report(lines), **kw)


def test_wrapped_cells_in_a_wide_project_table_are_not_headings():
    row = "Department of Housing and    Economic           Operation We Care and Neighborhood          MI         520,000"
    doc = _plain(
        [
            _center("COMMUNITY PROJECT FUNDING"),
            "",
            "    The Committee recommends the following projects.",
            "",
            "-" * 110,
            row,
            " Urban Development            Development        Revitalization",
            "                              Initiatives",
            row,
            "                              Initiatives",
            row,
        ]
    )
    assert [s.path[-1] for s in doc.sections] == ["COMMUNITY PROJECT FUNDING"]


def test_state_labels_inside_a_project_table_are_not_headings():
    doc = _plain(
        [
            _center("OPERATION AND MAINTENANCE"),
            "",
            "    The Committee recommends the following amounts.",
            "",
            "FT PECK DAM AND LAKE, MT...........          10,371          10,371",
            "LIBBY DAM, MT......................           2,035           2,035",
            " ",
            _center("NEBRASKA"),
            " ",
            "HARLAN COUNTY LAKE, NE.............           4,746           4,746",
            "SALT CREEK AND TRIBUTARIES, NE.....           1,393           1,393\x1e",
        ]
    )
    assert [s.path[-1] for s in doc.sections] == ["OPERATION AND MAINTENANCE"]


def test_fiscal_year_column_header_is_not_a_heading():
    from budget_differ.segment.classify_lines import is_heading_line

    assert not is_heading_line(_center("FY 2019          FY 2020"))
    assert is_heading_line(_center("National Institutes of Health (NIH)"))


def test_trailing_acronym_does_not_change_the_alignment_key():
    from budget_differ.segment.headings import normalize_heading

    assert normalize_heading("Veterans Health Administration (VHA)") == normalize_heading("VETERANS HEALTH ADMINISTRATION")
    assert normalize_heading("(RESCISSION)") == "RESCISSION"


def test_sec_style_provisions_split_and_keep_their_continuations():
    doc = _plain(
        [
            _center("TITLE VII--GENERAL PROVISIONS"),
            "",
            "    Sec. 7075 includes language carried in the prior year",
            "regarding funds.",
            "    Sec. 7076 includes language modified from the prior year",
            "regarding spend plans.",
            "    The regional security initiatives to be addressed in the",
            "spend plans shall include the Trans-Sahara Counterterrorism",
            "Partnership.",
        ]
    )
    provisions = {s.path[-1]: s for s in doc.sections if s.path[-1].startswith("SEC ")}
    assert set(provisions) == {"SEC 7075", "SEC 7076"}
    assert len(provisions["SEC 7076"].paragraphs) == 2
    assert provisions["SEC 7076"].printed_under == ("TITLE VII GENERAL PROVISIONS",)


def test_component_over_recurring_account_owns_it():
    doc = _plain(
        [
            _center("TITLE III--THE JUDICIARY"),
            "",
            _center("Supreme Court of the United States"),
            "",
            _center("SALARIES AND EXPENSES"),
            "",
            "    The Committee recommends funding for the Supreme Court.",
            "",
            _center("CARE OF THE BUILDING AND GROUNDS"),
            "",
            "    The Committee recommends funding for the building.",
            "",
            _center("United States Court of International Trade"),
            "",
            _center("SALARIES AND EXPENSES"),
            "",
            "    The Committee recommends funding for the Court of International Trade.",
        ]
    )
    paths = [s.path for s in doc.sections if s.paragraphs]
    assert paths[1] == ("TITLE III THE JUDICIARY", "SUPREME COURT OF THE UNITED STATES", "CARE OF THE BUILDING AND GROUNDS")
    assert paths[2] == ("TITLE III THE JUDICIARY", "UNITED STATES COURT OF INTERNATIONAL TRADE", "SALARIES AND EXPENSES")


def test_agency_named_topic_before_the_first_title_does_not_adopt_the_intro():
    doc = _plain(
        [
            _center("Department of Veterans Affairs"),
            "",
            "    The Committee notes coordination with the Department.",
            "",
            _center("Joint Strike Fighter"),
            "",
            "    The Committee remains concerned about sustainment costs.",
            "",
            _center("TITLE I"),
            "",
            _center("MILITARY PERSONNEL"),
            "",
            "    The Committee recommends funding.",
        ],
        agencies=frozenset({"DEPARTMENT OF VETERANS AFFAIRS"}),
    )
    jsf = next(s for s in doc.sections if s.heading == "Joint Strike Fighter")
    assert "DEPARTMENT OF VETERANS AFFAIRS" not in jsf.path


def test_caps_grouping_owns_the_small_caps_agency_below_it():
    lines = [
        _center("TITLE I--DEPARTMENT OF STATE AND RELATED AGENCY"),
        "",
        _center("RELATED AGENCY"),
        "",
        _center("Broadcasting Board of Governors"),
        "",
        _center("INTERNATIONAL BROADCASTING OPERATIONS"),
        "",
        "    The Committee recommends funding for broadcasting.",
        "",
        _center("RELATED PROGRAMS"),
        "",
        _center("The Asia Foundation"),
        "",
        "    The Committee recommends funding for the Foundation.",
    ]
    tiers = [
        {"tier": "caps", "text": "TITLE I—DEPARTMENT OF STATE AND RELATED AGENCY"},
        {"tier": "caps", "text": "RELATED AGENCY"},
        {"tier": "sc", "text": "BROADCASTING BOARD OF GOVERNORS"},
        {"tier": "sc", "text": "INTERNATIONAL BROADCASTING OPERATIONS"},
        {"tier": "caps", "text": "RELATED PROGRAMS"},
        {"tier": "sc", "text": "THE ASIA FOUNDATION"},
    ]
    doc = _plain(lines, pdf_tiers=tiers)
    paths = {s.heading: s.path for s in doc.sections}
    assert paths["INTERNATIONAL BROADCASTING OPERATIONS"][1:] == ("RELATED AGENCY", "BROADCASTING BOARD OF GOVERNORS", "INTERNATIONAL BROADCASTING OPERATIONS")
    assert paths["The Asia Foundation"][1:] == ("RELATED PROGRAMS", "THE ASIA FOUNDATION")
