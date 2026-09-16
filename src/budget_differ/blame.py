"""Paragraph provenance across a chain — blame for report language.

Documents in a chain share Section/Paragraph object identity across transitions, so a paragraph's history is walked by following ParagraphDiff.old references backward through each transition's diff (and its cross-section moves)."""

from __future__ import annotations

from dataclasses import dataclass

from budget_differ.chain import Chain
from budget_differ.models import ChangeClass, Paragraph


@dataclass
class Provenance:
    added_fy: int | None  # None = present since the chain's first year
    last_change: tuple[ChangeClass, int] | None  # most recent non-unchanged edit
    moved: tuple[str, int] | None  # (source section heading, fy)

    def label(self, first_fy: int, latest_fy: int) -> str:
        parts: list[str] = []
        if self.added_fy is not None:
            parts.append(f"added FY{self.added_fy}")
        if self.last_change is not None:
            change, fy = self.last_change
            if not (self.added_fy == fy):
                verb = {
                    ChangeClass.NUMBERS_ONLY: "figures updated",
                    ChangeClass.MINOR: "tweaked",
                }.get(change, "revised")
                parts.append(f"{verb} FY{fy}")
        if self.moved is not None:
            heading, fy = self.moved
            parts.append(f"moved from {heading} (FY{fy})")
        if not parts:
            return f"unchanged since FY{first_fy}"
        return "; ".join(parts)

    def is_hot(self, latest_fy: int) -> bool:
        """Changed in the most recent transition — what a reader scans for."""
        return (
            self.added_fy == latest_fy
            or (self.last_change is not None and self.last_change[1] == latest_fy)
            or (self.moved is not None and self.moved[1] == latest_fy)
        )


def transition_maps(chain: Chain) -> dict[int, dict[int, tuple]]:
    """fy_new → {id(new paragraph): (old paragraph | None, change, moved_from | None)}."""
    maps: dict[int, dict[int, tuple]] = {}
    for _, b, _, diff in chain.transitions:
        m: dict[int, tuple] = {}
        for sd in diff.sections:
            for pd in sd.paragraph_diffs:
                if pd.new is not None:
                    m[id(pd.new)] = (pd.old, pd.change, None)
        for mv in diff.moves:
            if mv.diff.new is not None:
                m[id(mv.diff.new)] = (mv.diff.old, mv.diff.change, mv.old_section_heading)
        maps[b] = m
    return maps


def provenance(
    maps: dict[int, dict[int, tuple]],
    fys: list[int],
    para: Paragraph,
    start_fy: int | None = None,
) -> Provenance:
    """Walk a paragraph backward through the transitions, starting at its own year.

    start_fy is the year the paragraph belongs to (the thread's last year for a dropped thread) — walking from the chain's end would look the paragraph up in transitions it never participated in and misread absence as "added"."""
    added_fy: int | None = None
    last_change: tuple[ChangeClass, int] | None = None
    moved: tuple[str, int] | None = None
    cur = para
    walk = [b for b in fys[1:] if start_fy is None or b <= start_fy]
    for b in reversed(walk):
        entry = maps.get(b, {}).get(id(cur))
        if entry is None:
            # Untracked into this transition: its section was new that year.
            added_fy = b
            break
        old, change, moved_from = entry
        if moved_from is not None and moved is None:
            moved = (moved_from, b)
        if change != ChangeClass.UNCHANGED and last_change is None:
            last_change = (change, b)
        if old is None:
            added_fy = b
            break
        cur = old
    return Provenance(added_fy=added_fy, last_change=last_change, moved=moved)
