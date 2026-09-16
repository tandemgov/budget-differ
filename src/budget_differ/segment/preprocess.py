"""Slice the GPO <pre> text and find the narrative body bounds."""

from __future__ import annotations

import html
import re

# Index/table-of-contents entry: dotted leader ending in a page number.
_INDEX_LINE = re.compile(r"\.{5,}\s*\d+\s*$")
_CONTENTS = re.compile(r"^\s*(C\s?O\s?N\s?T\s?E\s?N\s?T\s?S|CONTENTS|INDEX TO BILL AND REPORT)\s*$")
_TITLE_HEADING = re.compile(r"^\s+TITLE\s+[IVXLC]+")

# Back matter starts at these compliance/boilerplate headings (chamber rules sections, ramseyer prints, changes-in-existing-law) — after them the bill text repeats, which would double-diff every general provision. Prefix match on an indented line: the headings wrap and vary in case, while prose continuations sit at column 0.
_BACK_MATTER = re.compile(
    r"^\s+("
    r"HOUSE OF REPRESENTATIVES REPORT REQUIREMENTS"
    r"|CHANGES IN (THE )?(APPLICATION OF )?EXISTING LAW"
    r"|COMPLIANCE WITH PARAGRAPH"
    r"|COMPLIANCE WITH RULE"
    r"|BUDGETARY IMPACT OF BILL"
    r")",
    re.IGNORECASE,
)


def extract_pre_text(raw: str) -> str:
    """Return the unescaped plain text between <pre> and </pre>."""
    m = re.search(r"<pre>(.*)</pre>", raw, re.DOTALL | re.IGNORECASE)
    text = m.group(1) if m else raw
    return html.unescape(text)


def body_bounds(lines: list[str]) -> tuple[int, int]:
    """Return (start, end) line indices of the narrative body.

    Start: after the CONTENTS/index block — the last dotted-leader index line reached by scanning forward from CONTENTS with a tolerance gap. Falls back to 0.
    End: the first back-matter compliance heading, else len(lines).
    """
    start = 0
    contents_idx = None
    for i, line in enumerate(lines[:400]):
        if _CONTENTS.match(line):
            contents_idx = i
            break
    if contents_idx is not None:
        last_leader = contents_idx
        i = contents_idx + 1
        while i < len(lines) and i - last_leader < 15:
            if _INDEX_LINE.search(lines[i]):
                last_leader = i
            i += 1
        start = last_leader + 1

    end = len(lines)
    for i in range(start, len(lines)):
        # Dotted-leader guard: a wrapped table-of-contents entry can carry the same phrase ("Changes in the Application of Existing Law......") — skip those.
        if _BACK_MATTER.match(lines[i]) and "...." not in lines[i]:
            end = i
            break
    return start, end
