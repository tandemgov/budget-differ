"""Match sections across two years of the same subcommittee report."""

from __future__ import annotations

import re
from collections import defaultdict

from rapidfuzz import fuzz

from budget_differ.models import Document, Section

# Pass 2: fuzzy heading match within a shared parent.
HEADING_WEIGHT = 0.6
CONTENT_WEIGHT = 0.4
# Rechecked 2026-09-16 on restored labels (scripts/linkage_eval.py score): 70 keeps precision at 100%; 65 admits the first false positive.
FUZZY_ACCEPT = 70.0
HEADING_FLOOR = 60.0
# Pass 3: content-only rescue (renames, GP renumbering).
CONTENT_ACCEPT = 80.0
POSITION_PENALTY = 5.0
CONTENT_PREFIX = 2000
# General provisions renumber across years, so a same-number exact match can pair two unrelated provisions; below this content similarity the pair is unmatched and both sides fall through to content rescue.
GP_MIN_SIMILARITY = 55.0
# When the new year's text announces "includes a new provision", the number match is presumed a slot takeover unless content similarity is this high.
GP_TAKEOVER_SIMILARITY = 80.0
# Renumbering collision: templated provisions pass GP_MIN_SIMILARITY on scaffolding, so defer to a much better mutual match.
GP_RENUMBER_BEST = 90.0
GP_RENUMBER_MARGIN = 10.0


def _body(sec: Section, limit: int) -> str:
    return " ".join(p.text for p in sec.paragraphs)[:limit]


# "Section 755. The Committee includes a new provision ..." — the scaffold is shared by every general provision and inflates similarity between unrelated ones; the predicate tail is the identity.
_GP_SCAFFOLD = re.compile(
    r"^(?:Section|Sec\.)\s+\d+[A-Za-z]?\.?\s*(The Committee\s+)?"
    r"(includes|continues|adds|repeats|modifies|provides|is)?\s*(a|the)?\s*(new|language)?\s*"
    r"(provisions?\b|modified from the prior year|carried in the prior year)?[,.]?\s*",
    re.IGNORECASE,
)


def _gp_tail(sec: Section) -> str:
    if not sec.paragraphs:
        return ""
    text = sec.paragraphs[0].text
    m = _GP_SCAFFOLD.match(text)
    tail = text[m.end() :] if m else text
    return tail or text


# A bare "Section 8136 prohibits ..." lead-in that the scaffold regex leaves alone: the number is a slot, not content, so the strict scorer drops it.
_GP_NUMBER = re.compile(r"^(?:Section|Sec\.)\s+\d+[A-Za-z]?\s*[.:]?\s*(--)?\s*", re.IGNORECASE)


def similarity_texts(a: Section, b: Section, limit: int = CONTENT_PREFIX) -> tuple[str, str]:
    """The two texts the similarity scorers compare: scaffold-stripped predicate tails for a pair of general provisions, body prefixes otherwise."""
    if a.path[-1].startswith("SEC ") and b.path[-1].startswith("SEC "):
        ta, tb = _gp_tail(a), _gp_tail(b)
        if ta and tb:
            return ta[:limit], tb[:limit]
    return _body(a, limit), _body(b, limit)


def section_similarity(a: Section, b: Section, limit: int = CONTENT_PREFIX) -> float:
    """Content similarity; general provisions compare scaffold-stripped tails."""
    return fuzz.token_set_ratio(*similarity_texts(a, b, limit))


def section_similarity_strict(a: Section, b: Section, limit: int = CONTENT_PREFIX) -> float:
    """Length-sensitive score on the same texts: token_set_ratio saturates when one text's tokens are a subset of the other's. Provision numbers dropped."""
    ta, tb = similarity_texts(a, b, limit)
    return fuzz.ratio(_GP_NUMBER.sub("", ta), _GP_NUMBER.sub("", tb))


# Trace rejected candidates down to this margin below a pass's accept threshold, so threshold sweeps in the linkage eval can look below the current operating point.
TRACE_MARGIN = 20.0


def align_sections(
    old_doc: Document,
    new_doc: Document,
    trace: list[dict] | None = None,
) -> tuple[list[tuple[Section, Section]], list[Section], list[Section]]:
    """Return (matched old→new pairs, removed old sections, added new sections).

    When `trace` is a list, every linkage decision is appended to it as a dict {pass, score, accepted, old, new} (Section objects) — the raw material for the labeled linkage evaluation in scripts/linkage_eval.py.
    """

    def _trace(pass_name: str, score: float, accepted: bool, os_: Section, ns: Section) -> None:
        if trace is not None:
            trace.append(
                {"pass": pass_name, "score": score, "accepted": accepted, "old": os_, "new": ns}
            )

    matched: list[tuple[Section, Section]] = []
    old_free = list(old_doc.sections)
    new_free = list(new_doc.sections)

    # Pass 1: exact normalized-path match, paired in occurrence order.
    old_by_path: dict[tuple[str, ...], list[Section]] = defaultdict(list)
    for s in old_free:
        old_by_path[s.path].append(s)
    still_new: list[Section] = []
    for s in new_free:
        candidates = old_by_path.get(s.path)
        if candidates:
            matched.append((candidates.pop(0), s))
        else:
            still_new.append(s)
    new_free = still_new
    old_free = [s for lst in old_by_path.values() for s in lst]

    # GP guard: a SEC-keyed exact match survives only when the content agrees. Two failure modes: renumbering collisions (different provisions sharing Sec. 114 across years, dissimilar content), and slot takeovers — the report itself announces "includes a new provision ..." while reusing the number, so an announced-new paragraph must clear a much higher bar to count as the same provision (committees do carry the "new provision" phrasing into later years verbatim, which high similarity identifies).
    old_secs = [s for s in old_doc.sections if s.path[-1].startswith("SEC ")]
    new_secs = [s for s in new_doc.sections if s.path[-1].startswith("SEC ")]
    kept: list[tuple[Section, Section]] = []
    for os_, ns in matched:
        if ns.path[-1].startswith("SEC "):
            sim = section_similarity(os_, ns)
            if _renumbered_elsewhere(os_, ns, old_secs, new_secs):
                _trace("gp_guard", sim, False, os_, ns)
                old_free.append(os_)
                new_free.append(ns)
                continue
            announces_new = bool(
                ns.paragraphs
                and re.search(r"\bnew provision\b", ns.paragraphs[0].text[:200], re.I)
            )
            if sim < GP_MIN_SIMILARITY or (announces_new and sim < GP_TAKEOVER_SIMILARITY):
                _trace("gp_guard", sim, False, os_, ns)
                old_free.append(os_)
                new_free.append(ns)
                continue
        kept.append((os_, ns))
    matched = kept
    # Traced only now: a SEC-keyed pair the GP guard unwound was never a match.
    for os_, ns in matched:
        _trace("exact", 100.0, True, os_, ns)

    # Pass 1.5: unique-heading match. Heading levels drift across years (a heading is a parent one year and a sibling the next), which perturbs paths. If a normalized heading occurs exactly once among the unmatched on both sides, pair them.
    # SEC-keyed sections are excluded: a general provision's number is not its identity (renumbering), so those must pair by content in the later passes.
    old_unique = _unique_by_heading([s for s in old_free if not s.path[-1].startswith("SEC ")])
    new_unique = _unique_by_heading([s for s in new_free if not s.path[-1].startswith("SEC ")])
    for heading, ns in new_unique.items():
        os_ = old_unique.get(heading)
        if os_ is not None:
            matched.append((os_, ns))
            _trace("unique_heading", 100.0, True, os_, ns)
    matched_ids = {id(s) for pair in matched for s in pair}
    old_free = [s for s in old_free if id(s) not in matched_ids]
    new_free = [s for s in new_free if id(s) not in matched_ids]

    # Passes 2 and 3 operate within a shared parent path; pass 4 retries the content scorer within the shared top-level title (heading-level drift shifts parents, and the >=80 content threshold plus mutual-best guards against cross-matching).
    for pass_name, scorer, accept, bucket in (
        ("fuzzy_heading", _fuzzy_heading_score, FUZZY_ACCEPT, -1),
        ("content_parent", _content_score, CONTENT_ACCEPT, -1),
        ("content_title", _content_score, CONTENT_ACCEPT, 1),
    ):
        old_by_parent: dict[tuple[str, ...], list[Section]] = defaultdict(list)
        for s in old_free:
            old_by_parent[s.path[:bucket]].append(s)
        pairs: list[tuple[float, Section, Section]] = []
        for ns in new_free:
            for os_ in old_by_parent.get(ns.path[:bucket], []):
                score = scorer(os_, ns)
                if score is not None and score >= accept - TRACE_MARGIN:
                    pairs.append((score, os_, ns))
        used_old: set[int] = set()
        used_new: set[int] = set()
        for score, os_, ns in sorted(pairs, key=lambda t: -t[0]):
            if id(os_) in used_old or id(ns) in used_new:
                continue
            if score >= accept:
                used_old.add(id(os_))
                used_new.add(id(ns))
                matched.append((os_, ns))
                _trace(pass_name, score, True, os_, ns)
            else:
                # Below the operating point but within the trace margin: a labeled near-miss for the evaluation set.
                _trace(pass_name, score, False, os_, ns)
        old_free = [s for s in old_free if id(s) not in used_old]
        new_free = [s for s in new_free if id(s) not in used_new]

    matched.sort(key=lambda pair: pair[1].order)
    return matched, old_free, new_free


def _best_strict(sec: Section, pool: list[Section]) -> tuple[Section | None, float]:
    best, best_score = None, -1.0
    for other in pool:
        if other.path[0] != sec.path[0]:
            continue
        score = section_similarity_strict(sec, other)
        if score > best_score:
            best, best_score = other, score
    return best, best_score


def _renumbered_elsewhere(os_: Section, ns: Section, old_secs: list[Section], new_secs: list[Section]) -> bool:
    """True when the old or new provision of a same-number pair clearly belongs with a different-numbered provision in the other year."""
    here = section_similarity_strict(os_, ns)
    for sec, pool, back_pool, partner in ((os_, new_secs, old_secs, ns), (ns, old_secs, new_secs, os_)):
        best, score = _best_strict(sec, pool)
        if best is None or best is partner or score < GP_RENUMBER_BEST or score - here < GP_RENUMBER_MARGIN:
            continue
        back, _ = _best_strict(best, back_pool)
        if back is sec:
            return True
    return False


def _unique_by_heading(sections: list[Section]) -> dict[str, Section]:
    counts: dict[str, list[Section]] = defaultdict(list)
    for s in sections:
        counts[s.path[-1]].append(s)
    return {h: lst[0] for h, lst in counts.items() if len(lst) == 1}


def _fuzzy_heading_score(old: Section, new: Section) -> float | None:
    # A general provision's heading is its number — no identity signal, and "SEC 747" vs "SEC 748" scores deceptively high. SEC sections re-pair only through the content-based passes.
    if old.path[-1].startswith("SEC ") or new.path[-1].startswith("SEC "):
        return None
    heading = fuzz.token_sort_ratio(old.path[-1], new.path[-1])
    if heading < HEADING_FLOOR:
        return None
    content = fuzz.ratio(_body(old, 1500), _body(new, 1500))
    return HEADING_WEIGHT * heading + CONTENT_WEIGHT * content


def _content_score(old: Section, new: Section) -> float | None:
    score = section_similarity(old, new)
    return score - POSITION_PENALTY * abs(_rel_order(old) - _rel_order(new)) * 10


def _rel_order(sec: Section) -> float:
    # Orders are document-wide; normalize roughly to [0, 1] per thousand sections.
    return sec.order / 1000.0
