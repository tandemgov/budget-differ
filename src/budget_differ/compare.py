"""Compose the pipeline: two raw reports → ranked PairDiff."""

from __future__ import annotations

from pathlib import Path

import difflib

from rapidfuzz import fuzz

from budget_differ.align import align_sections, section_similarity
from budget_differ.anchors import assign_anchors
from budget_differ.config import pdfhier_cache_dir
from budget_differ.corpus import (
    CatalogEntry,
    Pair,
    load_agency_lexicon,
    load_bureau_lexicon,
    pdf_path,
    raw_path,
)
from budget_differ.diffing import diff_paragraph_pair, diff_section_pair
from budget_differ.models import (
    ChangeClass,
    Document,
    PairDiff,
    Paragraph,
    ParagraphMove,
    RelatedSection,
    Section,
)
from budget_differ.segment import segment_report
from budget_differ.segment.pdfhier import pdf_headings
from budget_differ.significance import score_sections

# Promote a dropped+new pair to a real matched diff ("renamed from ...") when they are each other's best content match at this overlap or better AND their parents align.
# Measured corpus-wide: below 65 the band fills with boilerplate cross-matches (COMMITTEE PROVISIONS blocks under different accounts); at 65+ with parent consistency it's dominated by genuine renames.
RENAME_PROMOTE = 65.0
# Short texts carry little evidence and shared scaffolding dominates the ratio ("Section N extends the authorization for ..." scored 67 against an unrelated provision in the labeled eval set); below this many characters on either side a promotion must be near-verbatim.
RENAME_SHORT_TEXT = 200
RENAME_SHORT_PROMOTE = 85.0
# Nested headings ("EXPLORATION" in "DEEP SPACE EXPLORATION SYSTEMS") corroborate a rename, so the content bar drops.
RENAME_NESTED_HEADING_PROMOTE = 55.0
# Annotation thresholds for the remaining possible successor/predecessor hints:
# a mutual link is trustworthy at 50+, a one-directional one (splits/merges) needs 60+.
RELATED_MUTUAL_FLOOR = 50.0
RELATED_ONEWAY_FLOOR = 60.0


def load_document(repo: Path, entry: CatalogEntry) -> Document:
    raw = raw_path(repo, entry).read_text(errors="replace")
    return segment_report(
        raw,
        package_id=entry.package_id,
        chamber=entry.chamber,
        subcommittee=entry.subcommittee or "",
        fiscal_year=entry.fiscal_year or 0,
        agencies=load_agency_lexicon(repo),
        bureaus=load_bureau_lexicon(repo),
        pdf_tiers=pdf_headings(pdf_path(repo, entry), pdfhier_cache_dir()),
    )


def compare_documents(old_doc: Document, new_doc: Document) -> PairDiff:
    matched, removed, added = align_sections(old_doc, new_doc)
    delta = max(1, new_doc.fiscal_year - old_doc.fiscal_year) if new_doc.fiscal_year and old_doc.fiscal_year else 1
    promoted = _promote_renames(matched, removed, added)
    pair = PairDiff(new_doc=new_doc, old_doc=old_doc)
    for old_sec, new_sec in matched:
        pair.sections.append(diff_section_pair(old_sec, new_sec, delta))
    for old_sec, new_sec in promoted:
        sd = diff_section_pair(old_sec, new_sec, delta)
        if old_sec.path[-1] != new_sec.path[-1]:
            sd.renamed_from = old_sec.heading
        pair.sections.append(sd)
    for sec in removed:
        pair.sections.append(diff_section_pair(sec, None))
    for sec in added:
        pair.sections.append(diff_section_pair(None, sec))
    _link_related(pair)
    _detect_moves(pair, delta)
    score_sections(pair)
    assign_anchors(pair)
    return pair


# A same-topic directive pair counts as a moved-and-edited paragraph at this ratio.
MOVE_EDIT_RATIO = 0.5


def _detect_moves(pair: PairDiff, year_delta: int = 1) -> None:
    """Pair loose paragraphs across sections: verbatim, then same-topic directives, then near-verbatim text of any kind.

    Unchanged moves stop counting toward either section's changed words.
    """
    removed = _loose_paragraphs(pair, old_side=True)
    added = _loose_paragraphs(pair, old_side=False)

    # Pass 1: verbatim moves.
    by_text: dict[str, list[tuple[Section, Paragraph, object]]] = {}
    for sec, para, sd in removed:
        by_text.setdefault(para.text, []).append((sec, para, sd))
    still_added = []
    for sec, para, sd in added:
        pool = by_text.get(para.text)
        if pool:
            old_sec, old_para, old_sd = pool.pop(0)
            _record_move(pair, old_sec, old_para, old_sd, sec, para, sd, year_delta)
        else:
            still_added.append((sec, para, sd))
    removed = [t for lst in by_text.values() for t in lst]

    still_added_ids: set[int] = set()
    # Pass 2: same-topic directives, mutual best, edited in place.
    old_by_topic: dict[str, list[tuple[Section, Paragraph, object]]] = {}
    for sec, para, sd in removed:
        if para.topic:
            old_by_topic.setdefault(para.topic.lower(), []).append((sec, para, sd))
    for sec, para, sd in still_added:
        if not para.topic:
            continue
        pool = old_by_topic.get(para.topic.lower(), [])
        best = None
        best_ratio = MOVE_EDIT_RATIO
        for cand in pool:
            ratio = difflib.SequenceMatcher(
                None, cand[1].text, para.text, autojunk=False
            ).ratio()
            if ratio > best_ratio:
                best, best_ratio = cand, ratio
        if best is not None:
            pool.remove(best)
            _record_move(pair, best[0], best[1], best[2], sec, para, sd, year_delta)
            still_added_ids.add(id(para))

    # Pass 3: a paragraph lightly edited while its account was reorganized.
    leftover_old = [t for lst in old_by_topic.values() for t in lst] + [t for t in removed if not t[1].topic]
    leftover_new = [t for t in still_added if id(t[1]) not in still_added_ids]
    _pair_edited_moves(pair, leftover_old, leftover_new, year_delta)


# Move pass 3 bars: mutual best match at this ratio (0-100), similar lengths, and not a one-liner.
MOVE_FUZZY_RATIO = 85.0
MOVE_LENGTH_RATIO = 0.8
MOVE_MIN_WORDS = 12


def _pair_edited_moves(pair: PairDiff, olds: list, news: list, year_delta: int) -> None:
    olds = [t for t in olds if len(t[1].text.split()) >= MOVE_MIN_WORDS]
    news = [t for t in news if len(t[1].text.split()) >= MOVE_MIN_WORDS]
    if not olds or not news:
        return

    def best(text: str, pool: list) -> tuple[int, float]:
        out, score = -1, 0.0
        for k, cand in enumerate(pool):
            other = cand[1].text
            if min(len(text), len(other)) < MOVE_LENGTH_RATIO * max(len(text), len(other)):
                continue
            r = fuzz.ratio(text, other, score_cutoff=MOVE_FUZZY_RATIO)
            if r > score:
                out, score = k, r
        return out, score

    back = [best(t[1].text, olds)[0] for t in news]
    for i, (sec, para, sd) in enumerate(olds):
        j, score = best(para.text, news)
        if j >= 0 and back[j] == i:
            nsec, npara, nsd = news[j]
            if nsd is sd:
                continue  # reordered within one section, not moved
            _record_move(pair, sec, para, sd, nsec, npara, nsd, year_delta)


def _loose_paragraphs(pair: PairDiff, old_side: bool):
    """Paragraphs with no counterpart in their own section: whole dropped/new sections plus one-sided paragraph diffs inside matched sections."""
    out = []
    for sd in pair.sections:
        if old_side and sd.change == ChangeClass.REMOVED:
            out.extend((sd.old, p, sd) for p in sd.old.paragraphs)
        elif not old_side and sd.change == ChangeClass.ADDED:
            out.extend((sd.new, p, sd) for p in sd.new.paragraphs)
        elif sd.old is not None and sd.new is not None:
            for pd in sd.paragraph_diffs:
                if old_side and pd.new is None and pd.old is not None:
                    out.append((sd.old, pd.old, sd))
                elif not old_side and pd.old is None and pd.new is not None:
                    out.append((sd.new, pd.new, sd))
    return out


def _record_move(pair, old_sec, old_para, old_sd, new_sec, new_para, new_sd, year_delta: int = 1) -> None:
    diff = diff_paragraph_pair(old_para, new_para, year_delta)
    pair.moves.append(
        ParagraphMove(
            old_section_heading=old_sec.heading,
            old_section_path=old_sec.path,
            new_section_heading=new_sec.heading,
            new_section_path=new_sec.path,
            diff=diff,
            old_sd=old_sd,
            new_sd=new_sd,
        )
    )
    if diff.change == ChangeClass.UNCHANGED:
        words = len(old_para.text.split())
        for sd in (old_sd, new_sd):
            sd.changed_words = max(0, sd.changed_words - words)


def _body(sec: Section) -> str:
    return " ".join(p.text for p in sec.paragraphs)[:2000]


def _best_matches(
    removed: list[Section], added: list[Section]
) -> dict[int, tuple[Section, float]]:
    """id(section) → (best counterpart on the other side within the same title, score)."""
    best: dict[int, tuple[Section, float]] = {}
    for group, pool in ((removed, added), (added, removed)):
        for sec in group:
            for other in pool:
                if other.path[0] != sec.path[0]:
                    continue
                score = section_similarity(sec, other)
                if id(sec) not in best or score > best[id(sec)][1]:
                    best[id(sec)] = (other, score)
    return best


def _promote_renames(
    matched: list[tuple[Section, Section]],
    removed: list[Section],
    added: list[Section],
) -> list[tuple[Section, Section]]:
    """Pull mutual-best, parent-consistent rename pairs out of removed/added."""
    matched_paths = {o.path: n.path for o, n in matched}
    best = _best_matches(removed, added)
    promoted: list[tuple[Section, Section]] = []
    for old_sec in list(removed):
        entry = best.get(id(old_sec))
        if entry is None or entry[1] < min(RENAME_PROMOTE, RENAME_NESTED_HEADING_PROMOTE):
            continue
        new_sec, score = entry
        if score < _promote_bar(old_sec, new_sec):
            continue
        back = best.get(id(new_sec))
        if back is None or back[0] is not old_sec:
            continue
        old_parent, new_parent = old_sec.path[:-1], new_sec.path[:-1]
        shorter = min(len(old_parent), len(new_parent))
        parent_ok = (
            old_parent == new_parent
            or matched_paths.get(old_parent) == new_parent
            # Reports insert/remove grouping tiers between years (ENERGY PROGRAMS appearing over DOE's accounts one year and not the next) — a shared parent prefix is the same lineage.
            or old_parent[:shorter] == new_parent[:shorter]
        )
        if not parent_ok:
            continue
        promoted.append((old_sec, new_sec))
        removed.remove(old_sec)
        added.remove(new_sec)
    return promoted


def _promote_bar(old_sec: Section, new_sec: Section) -> float:
    if any(len(_body(sec)) < RENAME_SHORT_TEXT for sec in (old_sec, new_sec)):
        return RENAME_SHORT_PROMOTE
    if _nested_headings(old_sec, new_sec) and old_sec.path[:-1] == new_sec.path[:-1]:
        return RENAME_NESTED_HEADING_PROMOTE
    return RENAME_PROMOTE


def _nested_headings(a: Section, b: Section) -> bool:
    wa, wb = set(a.path[-1].split()), set(b.path[-1].split())
    shorter = min(wa, wb, key=len)
    return bool(shorter) and not a.path[-1].startswith("SEC ") and (wa <= wb or wb <= wa)


def _link_related(pair: PairDiff) -> None:
    """Cross-link remaining dropped and new sections that likely reorganized. A mutual link is annotated from 50; a one-directional one (splits/merges) needs 60."""
    removed = [sd.old for sd in pair.sections if sd.change == ChangeClass.REMOVED]
    added = [sd.new for sd in pair.sections if sd.change == ChangeClass.ADDED]
    best = _best_matches(
        [s for s in removed if s is not None], [s for s in added if s is not None]
    )
    sd_of = {id(sd.old or sd.new): sd for sd in pair.sections}
    for sd in pair.sections:
        if sd.change not in (ChangeClass.REMOVED, ChangeClass.ADDED):
            continue
        sec = sd.old or sd.new
        assert sec is not None
        entry = best.get(id(sec))
        if entry is None:
            continue
        other, score = entry
        back = best.get(id(other))
        mutual = back is not None and back[0] is sec
        floor = RELATED_MUTUAL_FLOOR if mutual else RELATED_ONEWAY_FLOOR
        if score >= floor:
            sd.related = RelatedSection(
                heading=other.heading, path=other.path, overlap=score, sd=sd_of.get(id(other))
            )


def compare_pair(repo: Path, pair: Pair) -> PairDiff:
    return compare_documents(load_document(repo, pair.old), load_document(repo, pair.new))
