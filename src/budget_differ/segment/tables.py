"""Detect table regions to drop before diffing. Bias: over-drop.

A false table costs one missing paragraph (visible in golden tests); a missed table pollutes every diff with column noise.
"""

from __future__ import annotations

import re

from budget_differ.segment.classify_lines import LineKind, is_numeric_row

_PARA_START = re.compile(r"^\s{2,8}\S")

# State-by-state project tables print each state as a centered label between blocks of the same table.
_STATES = frozenset(
    """ALABAMA ALASKA ARIZONA ARKANSAS CALIFORNIA COLORADO CONNECTICUT DELAWARE FLORIDA GEORGIA HAWAII IDAHO ILLINOIS
    INDIANA IOWA KANSAS KENTUCKY LOUISIANA MAINE MARYLAND MASSACHUSETTS MICHIGAN MINNESOTA MISSISSIPPI MISSOURI MONTANA
    NEBRASKA NEVADA OHIO OKLAHOMA OREGON PENNSYLVANIA TENNESSEE TEXAS UTAH VERMONT VIRGINIA WASHINGTON WISCONSIN WYOMING""".split()
) | {
    "NEW HAMPSHIRE", "NEW JERSEY", "NEW MEXICO", "NEW YORK", "NORTH CAROLINA", "NORTH DAKOTA", "RHODE ISLAND",
    "SOUTH CAROLINA", "SOUTH DAKOTA", "WEST VIRGINIA", "DISTRICT OF COLUMBIA", "PUERTO RICO", "GUAM",
    "VIRGIN ISLANDS", "AMERICAN SAMOA", "NORTHERN MARIANA ISLANDS", "COMMONWEALTH OF THE NORTHERN MARIANA ISLANDS",
}
# A table row broken after its line number ("     30"), its item name printed on the next line.
_ROW_NUMBER = re.compile(r"^\s*\d{1,4}\s*$")
# Continuation lines a wrapped cell may add between two rows.
CELL_WRAP_MAX_LINES = 3
# Heading and blank lines a label row inside a wide table may span.
TABLE_LABEL_MAX_LINES = 10


def _label_rows_in_wide_table(lines: list[str], kinds: list[LineKind], i: int) -> int | None:
    """Index of the next table row when line i opens a run of label rows inside a wide table ("ACTIVITY 1: PAY AND ALLOWANCES"), else None.

    Money summaries print at body width, so requiring wide rows on both sides keeps a real account heading between two summaries."""
    # Look back past blanks and a broken row fragment ("    130") for the table row above.
    above = [p for p in range(max(0, i - TABLE_LABEL_MAX_LINES), i) if kinds[p] != LineKind.BLANK][-3:]
    if not any(len(lines[p].rstrip()) >= WIDE_ROW_MIN_CHARS and _tableish(lines[p], kinds[p]) for p in above):
        return None
    j = i
    while j < len(lines) and j - i < TABLE_LABEL_MAX_LINES and (
        kinds[j] in (LineKind.HEADING, LineKind.BLANK) or _ROW_NUMBER.match(lines[j])
    ):
        j += 1
    if j < len(lines) and len(lines[j].rstrip()) >= WIDE_ROW_MIN_CHARS and _tableish(lines[j], kinds[j]):
        return j
    return None


# Blank lines a state label may sit between.
STATE_LABEL_MAX_GAP = 2


def _state_label_in_table(lines: list[str], kinds: list[LineKind], i: int) -> int | None:
    """Index of the next table row when line i is a state label continuing a table, else None."""
    if lines[i].strip().upper() not in _STATES:
        return None
    j = i + 1
    while j < len(lines) and kinds[j] == LineKind.BLANK and j - i <= STATE_LABEL_MAX_GAP + 1:
        j += 1
    if j < len(lines) and _tableish(lines[j], kinds[j]):
        return j
    return None


# Body text wraps near 70 columns; multi-column project tables print wider rows split by runs of spaces.
WIDE_ROW_MIN_CHARS = 76
_COLUMN_GAP = re.compile(r"\S\s{3,}(?=\S)")


_AMOUNT_AT_END = re.compile(r"\d{1,3}(?:,\d{3})+\s*$")


def _wide_row(line: str) -> bool:
    return len(line.rstrip()) >= WIDE_ROW_MIN_CHARS and len(_COLUMN_GAP.findall(line)) >= 2


def _columnar_row(line: str) -> bool:
    """A body-width project-table row: space-separated columns ending in a dollar amount ("MT   Lolo National   7,334,000")."""
    return len(_COLUMN_GAP.findall(line)) >= 2 and bool(_AMOUNT_AT_END.search(line))


def _tableish(line: str, kind: LineKind) -> bool:
    if kind in (LineKind.TABLE_RULE, LineKind.TABLE_MARKER, LineKind.LEADER_LINE):
        return True
    return kind in (LineKind.BODY, LineKind.HEADING) and (is_numeric_row(line) or _wide_row(line) or _columnar_row(line))


_LOWER_WORD = re.compile(r"\b[a-z]{2,}\b")


def _is_prose_para_start(line: str) -> bool:
    """Prose = mostly letters, OR a couple of lowercase words — the latter catches sentences that open with a dollar figure ("The Committee recommends $1,516,685,000 for...") whose letter ratio a big number drags down."""
    if not _PARA_START.match(line) or is_numeric_row(line):
        return False
    stripped = line.strip()
    letters = sum(1 for c in stripped if c.isalpha() or c.isspace())
    if letters / max(len(stripped), 1) > 0.7:
        return True
    return len(_LOWER_WORD.findall(line)) >= 2


def table_spans(lines: list[str], kinds: list[LineKind]) -> list[tuple[int, int]]:
    """Return inclusive (start, end) index spans of table regions.

    Enter on an explicit rule/marker, or on 2+ consecutive table-ish lines (numeric rows, dotted-leader rows). A lone leader line is dropped as a 1-line span. Exit on a heading or a prose paragraph start; state-name headings inside comparative tables briefly exit, and the following rows immediately re-enter.
    """
    spans: list[tuple[int, int]] = []
    n = len(lines)
    i = 0
    while i < n:
        kind = kinds[i]
        enter = False
        if kind in (LineKind.TABLE_RULE, LineKind.TABLE_MARKER):
            enter = True
        elif _tableish(lines[i], kind):
            j = i + 1
            while j < n and kinds[j] == LineKind.BLANK:
                j += 1
            # Rows whose cells wrap put a few continuation lines between them.
            k = j
            while k < n and k - j < CELL_WRAP_MAX_LINES and kinds[k] != LineKind.BLANK and not _tableish(lines[k], kinds[k]):
                k += 1
            if (j < n and _tableish(lines[j], kinds[j])) or (_columnar_row(lines[i]) and k < n and _columnar_row(lines[k])):
                enter = True
            elif kind == LineKind.LEADER_LINE:
                spans.append((i, i))
                i += 1
                continue
        if not enter:
            i += 1
            continue

        start = i
        i += 1
        blanks = 0
        while i < n:
            kind = kinds[i]
            if kind == LineKind.HEADING and (
                (nxt := _state_label_in_table(lines, kinds, i)) is not None
                or (nxt := _label_rows_in_wide_table(lines, kinds, i)) is not None
            ):
                blanks = 0
                i = nxt
                continue
            if kind == LineKind.HEADING:
                # A wrapped cell ("Initiatives", "University") classifies as a heading; real headings are set off by blank lines, cells sit between rows.
                k = i
                while k + 1 < n and kinds[k + 1] == LineKind.HEADING:
                    k += 1
                m = k + 1
                while m < n and m - k <= CELL_WRAP_MAX_LINES and kinds[m] == LineKind.BODY and not _tableish(lines[m], kinds[m]):
                    m += 1
                if lines[i - 1].strip() and m < n and _tableish(lines[m], kinds[m]):
                    blanks = 0
                    i = m
                    continue
                break
            if kind == LineKind.BLANK:
                blanks += 1
                i += 1
                continue
            if kind == LineKind.BODY and blanks >= 1 and _is_prose_para_start(lines[i]):
                break
            blanks = 0
            i += 1
        spans.append((start, i - 1))
    return _merge(spans)


def _merge(spans: list[tuple[int, int]]) -> list[tuple[int, int]]:
    merged: list[tuple[int, int]] = []
    for s, e in sorted(spans):
        if merged and s <= merged[-1][1] + 1:
            merged[-1] = (merged[-1][0], max(merged[-1][1], e))
        else:
            merged.append((s, e))
    return merged
