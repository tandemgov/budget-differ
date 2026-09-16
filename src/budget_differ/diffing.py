"""Paragraph pairing, word-level diffs, and change classification."""

from __future__ import annotations

import difflib
import re

from budget_differ.policy import REVIEW, describe_paragraph, flag_edit, max_tier
from budget_differ.models import (
    ChangeClass,
    Paragraph,
    ParagraphDiff,
    Section,
    SectionDiff,
)

MINOR_MAX_CHANGED_WORDS = 5
REPAIR_RATIO = 0.5

_DOLLAR = re.compile(r"\$?\b\d[\d,]*(?:\.\d+)?\b")
_YEAR = re.compile(r"\b(?:19|20)\d{2}\b")
_DATE = re.compile(
    r"\b(?:January|February|March|April|May|June|July|August|September|October|November|December)"
    r"\s+#(?:,\s*#Y)?",
)


def mask(text: str) -> str:
    """Replace dollar amounts, years, and dates with placeholders so a change in figures alone doesn't read as a language change."""
    t = _YEAR.sub("#Y", text)
    t = _DOLLAR.sub("#", t)
    t = _DATE.sub("#D", t)
    return t


def _para_key(p: Paragraph) -> str:
    if p.topic:
        return f"{p.kind}:{p.topic.lower()}"
    return mask(p.text.lower())[:120]


def diff_section_pair(old: Section | None, new: Section | None, year_delta: int = 1) -> SectionDiff:
    """year_delta: fiscal years between the two reports, so a date that advances by exactly that much reads as a routine rollover."""
    if old is None:
        assert new is not None
        return SectionDiff(
            old=None,
            new=new,
            change=ChangeClass.ADDED,
            changed_words=sum(len(p.text.split()) for p in new.paragraphs),
        )
    if new is None:
        return SectionDiff(
            old=old,
            new=None,
            change=ChangeClass.REMOVED,
            changed_words=sum(len(p.text.split()) for p in old.paragraphs),
        )

    para_diffs = _pair_paragraphs(old.paragraphs, new.paragraphs, year_delta)
    change = ChangeClass.UNCHANGED
    changed_words = 0
    for pd in para_diffs:
        if pd.old is None or pd.new is None:
            change = max(change, ChangeClass.SUBSTANTIVE)
        else:
            change = max(change, pd.change)
        changed_words += pd.changed_words
    return SectionDiff(
        old=old, new=new, change=change, paragraph_diffs=para_diffs, changed_words=changed_words
    )


def _pair_paragraphs(olds: list[Paragraph], news: list[Paragraph], year_delta: int = 1) -> list[ParagraphDiff]:
    old_keys = [_para_key(p) for p in olds]
    new_keys = [_para_key(p) for p in news]
    sm = difflib.SequenceMatcher(None, old_keys, new_keys, autojunk=False)
    out: list[ParagraphDiff] = []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            for di in range(i2 - i1):
                out.append(_diff_paragraph(olds[i1 + di], news[j1 + di], year_delta))
        elif tag == "replace":
            out.extend(_repair(olds[i1:i2], news[j1:j2], year_delta))
        elif tag == "delete":
            for p in olds[i1:i2]:
                out.append(
                    ParagraphDiff(
                        old=p,
                        new=None,
                        change=ChangeClass.REMOVED,
                        changed_words=len(p.text.split()),
                        tags=describe_paragraph(p.text),
                    )
                )
        elif tag == "insert":
            for p in news[j1:j2]:
                out.append(
                    ParagraphDiff(
                        old=None,
                        new=p,
                        change=ChangeClass.ADDED,
                        changed_words=len(p.text.split()),
                        tags=describe_paragraph(p.text),
                    )
                )
    return out


def _repair(olds: list[Paragraph], news: list[Paragraph], year_delta: int = 1) -> list[ParagraphDiff]:
    """Re-pair a replace block by best text similarity, leaving leftovers as add/remove."""
    scored: list[tuple[float, int, int]] = []
    for i, op in enumerate(olds):
        for j, np in enumerate(news):
            # Word sequences, not a character bag: any two English paragraphs share half their letters, which paired unrelated directives.
            sm = difflib.SequenceMatcher(None, op.text.split(), np.text.split(), autojunk=False)
            if sm.quick_ratio() < REPAIR_RATIO:
                continue
            ratio = sm.ratio()
            if ratio >= REPAIR_RATIO:
                scored.append((ratio, i, j))
    used_i: set[int] = set()
    used_j: set[int] = set()
    pairs: dict[int, int] = {}
    for ratio, i, j in sorted(scored, key=lambda t: -t[0]):
        if i in used_i or j in used_j:
            continue
        used_i.add(i)
        used_j.add(j)
        pairs[i] = j
    out: list[ParagraphDiff] = []
    for i, op in enumerate(olds):
        if i in pairs:
            out.append(_diff_paragraph(op, news[pairs[i]], year_delta))
        else:
            out.append(
                ParagraphDiff(
                    old=op, new=None, change=ChangeClass.REMOVED,
                    changed_words=len(op.text.split()), tags=describe_paragraph(op.text),
                )
            )
    for j, np in enumerate(news):
        if j not in used_j:
            out.append(
                ParagraphDiff(
                    old=None, new=np, change=ChangeClass.ADDED,
                    changed_words=len(np.text.split()), tags=describe_paragraph(np.text),
                )
            )
    return out


def diff_paragraph_pair(old: Paragraph, new: Paragraph, year_delta: int = 1) -> ParagraphDiff:
    """Public entry for diffing one paragraph against another (used by move detection)."""
    return _diff_paragraph(old, new, year_delta)


def _diff_paragraph(old: Paragraph, new: Paragraph, year_delta: int = 1) -> ParagraphDiff:
    if old.text == new.text:
        return ParagraphDiff(old=old, new=new, change=ChangeClass.UNCHANGED)

    old_tokens = old.text.split()
    new_tokens = new.text.split()
    sm = difflib.SequenceMatcher(None, old_tokens, new_tokens, autojunk=False)
    opcodes: list[tuple[str, list[str], list[str]]] = []
    changed = 0
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        opcodes.append((tag, old_tokens[i1:i2], new_tokens[j1:j2]))
        if tag != "equal":
            changed += max(i2 - i1, j2 - j1)

    masked_old = mask(old.text)
    masked_new = mask(new.text)
    if masked_old == masked_new:
        change = ChangeClass.NUMBERS_ONLY
    else:
        sim = difflib.SequenceMatcher(None, masked_old, masked_new, autojunk=False).ratio()
        if sim >= 0.97 or changed <= MINOR_MAX_CHANGED_WORDS:
            change = ChangeClass.MINOR
        else:
            change = ChangeClass.SUBSTANTIVE
    literal = change
    flags = flag_edit(old.text, new.text, opcodes, year_delta)
    if max_tier(flags) >= REVIEW:
        change = max(change, ChangeClass.SUBSTANTIVE)
    return ParagraphDiff(
        old=old,
        new=new,
        change=change,
        opcodes=opcodes,
        changed_words=changed,
        flags=flags,
        literal_change=literal,
    )
