"""Detect table regions to drop before diffing. Bias: over-drop.

A false table costs one missing paragraph (visible in golden tests); a missed table pollutes every diff with column noise.
"""

from __future__ import annotations

import re

from budget_differ.segment.classify_lines import LineKind, is_numeric_row

_PARA_START = re.compile(r"^\s{2,8}\S")


def _tableish(line: str, kind: LineKind) -> bool:
    if kind in (LineKind.TABLE_RULE, LineKind.TABLE_MARKER, LineKind.LEADER_LINE):
        return True
    return kind == LineKind.BODY and is_numeric_row(line)


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
            if j < n and _tableish(lines[j], kinds[j]):
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
            if kind == LineKind.HEADING:
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
