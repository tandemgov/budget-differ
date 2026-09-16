"""Parse the report's own table of contents — the authoritative section tree.

Senate CONTENTS blocks nest with 4-space indents and colon-terminated parents; House INDEX TO BILL AND REPORT blocks list titles flush-left and accounts indented.
Body headings matched against TOC entries take their depth from the report itself, demoting the typographic heuristics to fallback.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_TOC_START = re.compile(r"^\s*(CONTENTS|INDEX TO BILL AND REPORT)\s*$")
_LEAF = re.compile(r"^(?P<text>.*?)\.{4,}\s*[\d ]*$")
_PAGE_ONLY = re.compile(r"^[\s\d]+$")
_TITLE_TEXT = re.compile(r"^TITLE\s+[IVXLC]+\b", re.IGNORECASE)
_HEADERISH = re.compile(r"^\s*(Page( Number)?|Bill Report|-+)\s*$", re.IGNORECASE)


@dataclass
class TocEntry:
    depth: int  # indent rank, 0 = shallowest
    text: str
    level: int = -1  # assigned after depth ranks are known


def parse_toc(lines: list[str]) -> list[TocEntry]:
    """Return ordered TOC entries, or [] when no parseable block exists."""
    start = None
    for i, line in enumerate(lines[:400]):
        if _TOC_START.match(line):
            start = i + 1
            break
    if start is None:
        return []

    entries: list[TocEntry] = []
    pending: tuple[int, str] | None = None  # wrapped entry awaiting its continuation
    # The block ends when we drift too far from the last line that anchored it (a dotted-leader leaf or a colon parent) — same tolerance idea as body_bounds.
    last_anchor = start
    i = start
    while i < len(lines) and i - last_anchor < 12:
        raw = lines[i].rstrip()
        i += 1
        if not raw.strip() or _HEADERISH.match(raw) or _PAGE_ONLY.match(raw):
            continue
        indent = len(raw) - len(raw.lstrip())
        text = raw.strip()

        if pending is not None:
            p_indent, p_text = pending
            pending = None
            if indent > p_indent:
                # Continuation fragment of a wrapped entry.
                text = f"{p_text} {text}"
                indent = p_indent
            # Otherwise the pending line was not a TOC entry — drop it.

        if text.endswith(":"):
            # Parent line; "A: B:" nests two parents on one line (Senate).
            last_anchor = i
            parts = [p.strip() for p in text.split(":") if p.strip()]
            for j, part in enumerate(parts):
                entries.append(TocEntry(depth=indent + 4 * j, text=part))
            continue
        m = _LEAF.match(text)
        if m and m.group("text").strip():
            last_anchor = i
            entries.append(TocEntry(depth=indent, text=m.group("text").strip()))
            continue
        if _TITLE_TEXT.match(text):
            last_anchor = i
            entries.append(TocEntry(depth=indent, text=text))
            continue
        # No leader, no colon, not a title line: maybe a wrapped entry's first half.
        pending = (indent, text)

    if len(entries) < 5:
        return []
    return entries
