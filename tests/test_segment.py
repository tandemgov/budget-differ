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
