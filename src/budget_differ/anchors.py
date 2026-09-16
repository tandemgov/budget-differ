"""Section anchors: the fragment id a section gets on its pair page.

Assigned once per PairDiff so every link into the page (summary table, timeline chips, thread history, move notes) agrees on one string.
"""

from __future__ import annotations

import hashlib

from budget_differ.models import PairDiff

# The digest keeps long paths that share a 60-char slug prefix from colliding.
SLUG_CHARS = 60
DIGEST_CHARS = 6


def section_anchor(path: tuple[str, ...]) -> str:
    joined = "-".join(p.lower().replace(" ", "_") for p in path)
    digest = hashlib.md5(" > ".join(path).encode()).hexdigest()[:DIGEST_CHARS]
    return f"s-{joined[:SLUG_CHARS]}-{digest}"


def assign_anchors(pair: PairDiff) -> None:
    """Distinct paths hash apart; duplicate paths (the aligner pairs repeated headings in occurrence order) get an ordinal from the second on."""
    seen: dict[str, int] = {}
    for sd in pair.sections:
        base = section_anchor(sd.display_path)
        n = seen.get(base, 0)
        seen[base] = n + 1
        sd.anchor = base if n == 0 else f"{base}-{n + 1}"
