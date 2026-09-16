"""Per-line classification of GPO fixed-width report text."""

from __future__ import annotations

import re
from enum import Enum

WRAP_WIDTH = 70  # GPO body text wraps at ~70 columns


class LineKind(Enum):
    BLANK = "blank"
    TABLE_RULE = "table_rule"
    TABLE_MARKER = "table_marker"
    LEADER_LINE = "leader_line"
    HEADING = "heading"
    BODY = "body"


_TABLE_RULE = re.compile(r"^\s*[-=_]{8,}\s*$")
_TABLE_MARKER = re.compile(r"GRAPHIC\(S\)? NOT AVAILABLE|\[In thousands", re.IGNORECASE)
# Dotted leader followed only by money/number columns (or dot-filler/footnote cells) to EOL.
_LEADER_LINE = re.compile(r"\.{4,}\s*[\d,.()$+\-* ]*$")
_HAS_LETTERS = re.compile(r"[A-Za-z]")
# Two or more digit-groups separated by wide gaps in the right half = numeric table row.
_NUMERIC_ROW = re.compile(r"[\d,.()+\-]+\s{2,}[+\-(]?[\d,.()][\d,.()+\-]*[\s*]*$")
# Subtotal/total rows and lines with several digit groups are table content, not headings.
_TOTALISH = re.compile(r"^\s*(TOTAL|SUBTOTAL)\b", re.IGNORECASE)
_MULTI_NUMBER = re.compile(r"\d[\d,]*\s+\d[\d,]*")
_TITLE_LINE = re.compile(r"^TITLE\s+[IVXLC]+\b")


def _indent(line: str) -> int:
    return len(line) - len(line.lstrip())


def _upper_ratio(s: str) -> float:
    letters = [c for c in s if c.isalpha()]
    if not letters:
        return 0.0
    return sum(1 for c in letters if c.isupper()) / len(letters)


def _is_centered(stripped: str, indent: int) -> bool:
    expected = (WRAP_WIDTH - len(stripped)) / 2
    return abs(indent - expected) <= 4


def is_heading_line(line: str) -> bool:
    stripped = line.strip()
    if not stripped or len(stripped) > WRAP_WIDTH:
        return False
    if not _HAS_LETTERS.search(stripped):
        return False
    if stripped.endswith((".", ",", ";", "--")) and not stripped.endswith("etc."):
        return False
    if _LEADER_LINE.search(line) or _TABLE_RULE.match(line):
        return False
    if _TOTALISH.match(stripped) or _MULTI_NUMBER.search(stripped):
        return False
    # A long title wraps at full width and starts near column 0 ("TITLE II--EXECUTIVE OFFICE OF THE PRESIDENT AND FUNDS APPROPRIATED TO") — structural regardless of indentation, unlike everything else.
    if _TITLE_LINE.match(stripped) and _upper_ratio(stripped) >= 0.9:
        return True
    indent = _indent(line)
    # The indent requirement is a centering proxy, which only means anything when the line is short enough to center: a 70-char heading ("FEDERAL PAYMENT TO THE DISTRICT OF COLUMBIA WATER AND SEWER AUTHORITY") prints at column 1.
    # Long lines fall through to the case tests, which prose cannot pass.
    if indent < 6 and len(stripped) <= 58:
        return False
    upper = _upper_ratio(stripped)
    if upper >= 0.9:
        return True
    # Title Case centered sub-heads ("Administrative Provision", "National Defense Programs") — capitalized words (short connectives exempt), centered, no period.
    if _is_centered(stripped, indent) and stripped[0].isupper():
        words = stripped.split()
        if 1 <= len(words) <= 10 and all(w[0].isupper() or len(w) <= 3 for w in words):
            return True
    return False


def classify(line: str) -> LineKind:
    if not line.strip():
        return LineKind.BLANK
    if _TABLE_RULE.match(line):
        return LineKind.TABLE_RULE
    if _TABLE_MARKER.search(line):
        return LineKind.TABLE_MARKER
    if _LEADER_LINE.search(line):
        return LineKind.LEADER_LINE
    if is_heading_line(line):
        return LineKind.HEADING
    return LineKind.BODY


def is_numeric_row(line: str) -> bool:
    """A BODY line that looks like a money-table row (columns of digits at right)."""
    return bool(_NUMERIC_ROW.search(line)) and len(line.rstrip()) > 40
