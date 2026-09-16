"""Rank section diffs so the changes that matter surface first."""

from __future__ import annotations

from budget_differ.models import ChangeClass, PairDiff, SectionDiff
from budget_differ.policy import CATEGORY_WEIGHT

CLASS_WEIGHT = {
    ChangeClass.UNCHANGED: 0.0,
    ChangeClass.NUMBERS_ONLY: 0.2,
    ChangeClass.MINOR: 0.5,
    ChangeClass.SUBSTANTIVE: 1.0,
    ChangeClass.ADDED: 2.0,
    ChangeClass.REMOVED: 2.0,
}
DIRECTIVE_BOOST = 1.5
NEW_DROPPED_DIRECTIVE_BOOST = 3.0


def score_sections(pair: PairDiff) -> None:
    for sd in pair.sections:
        sd.score = _score(sd)
    pair.sections.sort(key=lambda sd: (-sd.score, sd.display_path))


def _score(sd: SectionDiff) -> float:
    base = sd.changed_words * CLASS_WEIGHT[sd.change]
    # Policy flags carry weight independent of edit size: one category per paragraph counts once.
    for pd in sd.paragraph_diffs:
        base += sum(CATEGORY_WEIGHT[c] for c in {f.category for f in pd.flags})
    boost = 1.0
    for pd in sd.paragraph_diffs:
        para = pd.new or pd.old
        if para is not None and para.kind == "directive" and pd.change != ChangeClass.UNCHANGED:
            if pd.old is None or pd.new is None:
                boost = max(boost, NEW_DROPPED_DIRECTIVE_BOOST)
            else:
                boost = max(boost, DIRECTIVE_BOOST)
    sec = sd.new or sd.old
    if sec is not None and sd.change in (ChangeClass.ADDED, ChangeClass.REMOVED):
        if any(p.kind == "directive" for p in sec.paragraphs):
            boost = max(boost, NEW_DROPPED_DIRECTIVE_BOOST)
    return base * boost
