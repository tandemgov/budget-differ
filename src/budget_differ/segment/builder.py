"""Assemble a Document: lines → headings + table spans → sections with unwrapped paragraphs."""

from __future__ import annotations

import difflib
import re

from budget_differ.models import Document, Paragraph, Section
from budget_differ.segment.classify_lines import LineKind, classify
from budget_differ.segment.headings import (
    TOPICAL,
    LEGISLATIVE_AGENCIES,
    LEGISLATIVE_BUREAUS,
    Heading,
    _kind,
    assign_levels,
    normalize_heading,
)
from budget_differ.segment.pdfhier import apply_pdf_tiers
from budget_differ.segment.preprocess import body_bounds, extract_pre_text
from budget_differ.segment.tables import table_spans
from budget_differ.segment.toc import _TITLE_TEXT, TocEntry, parse_toc

_PARA_START = re.compile(r"^\s{2,8}\S")
_DIRECTIVE = re.compile(r"^([A-Z][^.]{2,80}?)\.--")
_GP_SECTION = re.compile(r"^Section\s+(\d+[A-Za-z]?)\b")
# Rejoin words hyphen-split at the GPO wrap point, but leave suspended-hyphen constructions ("In- and Out-Bound", "Bio- and Agro-Defense") intact.
_HYPHEN_WRAP = re.compile(r"(?<=[a-z])- (?!(?:and|or)\b)(?=[a-z])")


def segment_report(
    raw_html: str,
    package_id: str = "",
    chamber: str = "",
    subcommittee: str = "",
    fiscal_year: int = 0,
    agencies: frozenset[str] = frozenset(),
    bureaus: frozenset[str] = frozenset(),
    pdf_tiers: list[dict] | None = None,
) -> Document:
    if "LEGISLATIVE" in subcommittee.upper():
        agencies = agencies | LEGISLATIVE_AGENCIES
        bureaus = bureaus | LEGISLATIVE_BUREAUS
    text = extract_pre_text(raw_html)
    lines = text.split("\n")
    toc_entries = parse_toc(lines)  # before front matter is blanked away
    start, end = body_bounds(lines)
    lines = lines[:end]
    kinds = [classify(ln) for ln in lines]
    for i in range(start):  # neutralize front matter without shifting indices
        kinds[i] = LineKind.BLANK
        lines[i] = ""

    spans = table_spans(lines, kinds)
    in_table = set()
    for s, e in spans:
        in_table.update(range(s, e + 1))
    span_starts = {s for s, _ in spans}

    headings = _collect_headings(lines, kinds, in_table, start)
    headings = _join_split_headings(headings, lines, toc_entries, pdf_tiers, agencies, bureaus)
    money_after = set()
    for hi, h in enumerate(headings):
        j = h.line_end + 1
        while j < len(lines) and kinds[j] == LineKind.BLANK:
            j += 1
        if j < len(lines) and kinds[j] in (
            LineKind.LEADER_LINE,
            LineKind.TABLE_RULE,
            LineKind.TABLE_MARKER,
        ):
            money_after.add(hi)
    assign_levels(headings, agencies, bureaus, money_after)
    _apply_toc_levels(headings, toc_entries, agencies, bureaus)
    apply_pdf_tiers(headings, pdf_tiers, agencies, bureaus)

    doc = Document(
        package_id=package_id,
        chamber=chamber,
        subcommittee=subcommittee,
        fiscal_year=fiscal_year,
    )
    current_path: dict[int, str] = {}
    section: Section | None = None
    order = 0
    heading_lines = {i for h in headings for i in range(h.line_start, h.line_end + 1)}
    heading_at = {h.line_start: h for h in headings}

    para_lines: list[str] = []

    def flush_para() -> None:
        nonlocal para_lines
        if not para_lines or section is None:
            para_lines = []
            return
        text = _unwrap(para_lines)
        para_lines = []
        if not text:
            return
        section.paragraphs.append(_make_paragraph(text))

    i = 0
    while i < len(lines):
        if i in heading_at and heading_at[i].is_annotation:
            flush_para()
            i = heading_at[i].line_end + 1
            continue
        if i in heading_at:
            h = heading_at[i]
            flush_para()
            for lvl in [k for k in current_path if k >= h.level]:
                del current_path[lvl]
            current_path[h.level] = normalize_heading(h.text)
            path = tuple(current_path[k] for k in sorted(current_path))
            section = Section(
                heading=re.sub(r"\s+", " ", h.text).strip(),
                level=h.level,
                path=path,
                order=order,
            )
            order += 1
            doc.sections.append(section)
            i = h.line_end + 1
            continue
        if i in heading_lines:
            i += 1
            continue
        if i in in_table:
            if i in span_starts and section is not None:
                section.table_spans += 1
            flush_para()
            i += 1
            continue
        kind = kinds[i]
        line = lines[i]
        if kind == LineKind.BLANK:
            flush_para()
        elif kind == LineKind.BODY:
            if _PARA_START.match(line):
                flush_para()
                para_lines = [line]
            elif para_lines:
                para_lines.append(line)
            elif line.strip():
                para_lines = [line]
        else:
            flush_para()
        i += 1
    flush_para()

    doc.sections = [s for s in doc.sections if s.paragraphs or s.table_spans]
    _split_general_provisions(doc)
    return doc


def _toc_levels(
    entries: list[TocEntry], agencies: frozenset[str], bureaus: frozenset[str]
) -> None:
    """The TOC supplies order and parentage; the lexicons anchor semantic tiers.

    Sibling equality is the invariant: entries at the same depth under the same parent share ONE level, anchored by the highest lexicon tier present in the group (agency 1, bureau 2, else 3). Per-entry pinning is what filed FEDERAL CITIZEN SERVICES FUND under its sibling OFFICE OF INSPECTOR GENERAL: the TOC listed them at the same depth, but the bureau lexicon promoted OIG anyway."""
    # Pass A: parentage from depth nesting.
    parent_of: list[int | None] = []
    stack: list[tuple[int, int]] = []  # (depth, index)
    for i, e in enumerate(entries):
        while stack and stack[-1][0] >= e.depth:
            stack.pop()
        parent_of.append(stack[-1][1] if stack else None)
        stack.append((e.depth, i))

    def tier(e: TocEntry) -> int:
        kind = _kind(e.text, agencies, bureaus)
        return {"agency": 1, "bureau": 2}.get(kind, 3)

    # Pass B: one tier per sibling group.
    group_tier: dict[tuple[int | None, int], int] = {}
    for i, e in enumerate(entries):
        key = (parent_of[i], e.depth)
        group_tier[key] = min(group_tier.get(key, 3), tier(e))

    for i, e in enumerate(entries):
        if _TITLE_TEXT.match(e.text):
            e.level = 0
            continue
        parent = parent_of[i]
        parent_level = entries[parent].level if parent is not None else 0
        e.level = max(1, min(3, max(parent_level + 1, group_tier[(parent, e.depth)])))


def _apply_toc_levels(
    headings: list[Heading],
    entries: list[TocEntry],
    agencies: frozenset[str],
    bureaus: frozenset[str],
) -> None:
    """Override heuristic levels with the report's own declared hierarchy. Both sequences are in document order, so SequenceMatcher alignment disambiguates repeated names (each title's ADMINISTRATIVE PROVISIONS, every SALARIES AND EXPENSES) by position; headings absent from the TOC keep their heuristic level.
    GENERAL PROVISIONS headings keep level 3 — promoting one to a parent tier would absorb everything after it. Exact lexicon agencies are never *demoted* by the TOC: Senate CONTENTS blocks list the small related agencies (Smithsonian, Kennedy Center, Commission of Fine Arts) flat at account depth, and flattening them files every account that follows under the last big department."""
    if not entries:
        return
    _toc_levels(entries, agencies, bureaus)
    hnorm = [normalize_heading(h.text) for h in headings]
    tnorm = _toc_keys([e.text for e in entries], hnorm)
    sm = difflib.SequenceMatcher(None, tnorm, hnorm, autojunk=False)
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag != "equal":
            continue
        for k in range(i2 - i1):
            h = headings[j1 + k]
            if h.is_general_provisions:
                continue
            level = entries[i1 + k].level
            if level > h.level and _kind(h.text, agencies, bureaus) == "agency":
                continue
            h.level = level


_PARENTHETICAL = re.compile(r"\([^)]*\)")
# A TOC entry may differ from its body heading by this many leading-aligned words ("... Leadership Fund" over "... LEADERSHIP").
TOC_SNAP_MAX_EXTRA_WORDS = 2


def _toc_keys(texts: list[str], heading_keys: list[str]) -> list[str]:
    """Normalized TOC entries, each snapped to the body heading it names in qualified form ("Architect of the Capitol (except Senate Office Buildings)").

    An unmatched TOC entry leaves its heading at the heuristic level, which nested agencies under their predecessor."""
    counts: dict[str, int] = {}
    for h in heading_keys:
        counts[h] = counts.get(h, 0) + 1
    out = []
    for text in texts:
        key = normalize_heading(_PARENTHETICAL.sub(" ", text))
        if key not in counts:
            # Only an unambiguous snap to a heading printed once: a loose prefix match moved whole agencies under the wrong department.
            related = [
                h
                for h in counts
                if counts[h] == 1
                and (h.startswith(key + " ") or key.startswith(h + " "))
                and abs(len(h.split()) - len(key.split())) <= TOC_SNAP_MAX_EXTRA_WORDS
            ]
            if len(related) == 1:
                key = related[0]
        out.append(key)
    return out


def _is_prose(line: str) -> bool:
    """Running sentence text, as opposed to a table row whose cells also classify as body."""
    # Semicolons count: a sentence listing capitalized program names ("Environmental Cleanup; Uranium Enrichment") has few lowercase words.
    return "...." not in line and (";" in line or len(re.findall(r"\b[a-z]{2,}\b", line)) >= 3)


# Blank lines that may separate the two halves of one wrapped heading in the fixed-width render.
SPLIT_HEADING_MAX_GAP = 3


def _join_split_headings(
    headings: list[Heading],
    lines: list[str],
    toc_entries: list[TocEntry],
    pdf_tiers: list[dict] | None,
    agencies: frozenset[str],
    bureaus: frozenset[str],
) -> list[Heading]:
    """Rejoin a wrapped heading the .htm render split across blank lines ("...Interns in House Leadership" / "Offices").

    Stacked headings are also blank-separated, so a join needs evidence: the PDF or TOC prints the joined form, or the pair passes _wrapped_pair."""
    known = {normalize_heading(t["text"]).replace(" ", "") for t in pdf_tiers or []}
    known |= {normalize_heading(_PARENTHETICAL.sub(" ", e.text)).replace(" ", "") for e in toc_entries}
    out: list[Heading] = []
    for h in headings:
        prev = out[-1] if out else None
        if (
            prev is not None
            and 0 < h.line_start - prev.line_end - 1 <= SPLIT_HEADING_MAX_GAP
            and not any(ln.strip() for ln in lines[prev.line_end + 1 : h.line_start])
        ):
            joined = f"{prev.text} {h.text}"
            key = normalize_heading(joined).replace(" ", "")
            # An agency or bureau over its account is a stack even when the PDF sets the two lines close enough to read as one.
            parent_like = _kind(prev.text, agencies, bureaus) in ("title", "gp", "annotation", "agency", "bureau")
            if not parent_like and (
                (key in known and normalize_heading(prev.text).replace(" ", "") not in known) or _wrapped_pair(prev, h)
            ):
                out[-1] = Heading(text=joined, level=-1, line_start=prev.line_start, line_end=h.line_end)
                continue
        out.append(h)
    return out


# A first half this long has hit the centered-heading wrap width; a stacked parent heading rarely does.
WRAPPED_HALF_MIN_CHARS = 50
_TRAILING_CONNECTIVE = re.compile(r"\b(and|or|of|for|the|to|in|on)$", re.IGNORECASE)


def _wrapped_pair(first: Heading, second: Heading) -> bool:
    """A full-width first half and a one-word tail (or a tail after a dangling connective) in the same case style."""
    tail = second.text.strip()
    if len(first.text) < WRAPPED_HALF_MIN_CHARS or "...." in first.text:
        return False
    if tail.startswith("(") or tail.upper() in TOPICAL or first.text.isupper() != tail.isupper():
        return False
    if len(tail.split()) > 1 and not _TRAILING_CONNECTIVE.search(first.text.strip()):
        return False
    return True


def _collect_headings(
    lines: list[str], kinds: list[LineKind], in_table: set[int], start: int
) -> list[Heading]:
    headings: list[Heading] = []
    i = start
    n = len(lines)
    while i < n:
        # A low-indent "heading" with text on the line directly above is a wrapped prose continuation whose words happen to capitalize ("Academy and the new Congressional Member Leadership Development") — real headings are preceded by a blank line or another heading.
        if (
            kinds[i] == LineKind.HEADING
            and len(lines[i]) - len(lines[i].lstrip()) < 6
            and i > 0
            and lines[i - 1].strip()
            and kinds[i - 1] != LineKind.HEADING
            and (
                len(re.findall(r"\b[a-z]{2,}\b", lines[i])) >= 2
                # Or prose on both sides: a mid-paragraph line of capitalized list items ("Decommissioning Fund; Science; Nuclear Waste Disposal; Advanced").
                or (
                    i + 1 < n
                    and kinds[i + 1] == LineKind.BODY
                    and (_is_prose(lines[i - 1]) or _is_prose(lines[i + 1]) or _is_prose(lines[i]))
                )
            )
        ):
            kinds[i] = LineKind.BODY
        # First half of a wrapped contents entry, seen when the body bounds start inside the contents.
        if (
            kinds[i] == LineKind.HEADING
            and i + 1 < n
            and kinds[i + 1] == LineKind.LEADER_LINE
            and len(lines[i + 1]) - len(lines[i + 1].lstrip()) > len(lines[i]) - len(lines[i].lstrip())
        ):
            kinds[i] = LineKind.BODY
        if kinds[i] == LineKind.HEADING and i not in in_table:
            j = i
            while j + 1 < n and kinds[j + 1] == LineKind.HEADING and j + 1 not in in_table:
                j += 1
            text = re.sub(r"\s+", " ", " ".join(ln.strip() for ln in lines[i : j + 1])).strip()
            headings.append(Heading(text=text, level=-1, line_start=i, line_end=j))
            i = j + 1
        else:
            i += 1
    return headings


def _unwrap(para_lines: list[str]) -> str:
    text = " ".join(ln.strip() for ln in para_lines)
    text = re.sub(r"\s+", " ", text).strip()
    return _HYPHEN_WRAP.sub("", text)


def _make_paragraph(text: str) -> Paragraph:
    m = _GP_SECTION.match(text)
    if m:
        return Paragraph(text=text, kind="gp_section", topic=f"Section {m.group(1)}")
    m = _DIRECTIVE.match(text)
    if m:
        return Paragraph(text=text, kind="directive", topic=m.group(1).strip())
    return Paragraph(text=text)


def _split_general_provisions(doc: Document) -> None:
    """Explode each GP paragraph into its own child section so add/remove/renumber is visible at section granularity."""
    out: list[Section] = []
    for sec in doc.sections:
        gp_paras = [p for p in sec.paragraphs if p.kind == "gp_section"]
        # A lone "Section N ..." paragraph is only a provision when it sits under a provisions heading (e.g. the per-agency "Administrative Provision" blocks); elsewhere it's likely narrative citing an existing section of law.
        min_split = 1 if "PROVISION" in sec.heading.upper() else 2
        if len(gp_paras) < min_split:
            out.append(sec)
            continue
        rest = [p for p in sec.paragraphs if p.kind != "gp_section"]
        sec_copy = Section(
            heading=sec.heading,
            level=sec.level,
            path=sec.path,
            paragraphs=rest,
            table_spans=sec.table_spans,
            order=sec.order,
        )
        out.append(sec_copy)
        for p in gp_paras:
            assert p.topic
            # Key on (title, SEC n): section numbers are title-scoped and stable across years, while intermediate heading levels drift (see align pass notes).
            out.append(
                Section(
                    heading=f"{sec.heading} — {p.topic}",
                    level=4,
                    path=(sec.path[0], p.topic.upper().replace("SECTION", "SEC")),
                    paragraphs=[p],
                    order=sec.order,
                )
            )
    doc.sections = [s for s in out if s.paragraphs or s.table_spans]
