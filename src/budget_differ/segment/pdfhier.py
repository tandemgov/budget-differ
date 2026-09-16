"""Recover heading tiers from the GPO-typeset PDF twin of a report.

The fixed-width .htm render flattens GPO's typography: every heading level prints as centered ALL CAPS, which is why agency and account headings are indistinguishable there.
The PDF twin of the same locator source keeps the composition font codes, and they encode a reliable partial order:

- bold body font        -> title tier (House TITLE heads)
- full-size caps        -> agency / major-grouping tier (DEPARTMENT OF THE ARMY, ENERGY PROGRAMS, GENERAL PROVISIONS--...)
- small caps            -> everything below (bureaus, accounts, topical sub-heads)

Small-caps styling does not distinguish account from topical heads reliably, so only the caps/bold tier is used as an override signal: a heading the text heuristics left at account level but the PDF prints in full-size caps is a structural parent.

Extraction needs pymupdf (dev dependency); results are cached as JSON per package so the normal pipeline never touches the PDFs again.
"""

from __future__ import annotations

import difflib
import json
import re
from collections import Counter
from pathlib import Path

from budget_differ.segment.headings import TOPICAL, Heading, _kind, normalize_heading

# GPO committee reports set body text in New Century Schoolbook; every other font (Helvetica page furniture, TradeGothic tables, italic lead-ins, BGsddV01 brackets) marks a line that cannot be a section heading.
_ROMAN = "NewCenturySchlbk-Roman"
_BOLD = "NewCenturySchlbk-Bold"

# A centered line qualifies as a heading candidate only when it is horizontally centered and does not fill the column (justified body lines are "centered" too).
_MAX_CENTER_OFF = 30.0
_MAX_FILL = 0.75
# Wrapped-heading continuation lines sit ~2pt below the previous line; distinct stacked headings sit 6-8pt apart (measured on both chambers).
_MERGE_GAP = 4.0
_PAGE_NUMBER = re.compile(r"^\(?\d+\)?$")


def extract_pdf_headings(pdf_path: Path) -> list[dict] | None:
    """Ordered [(tier, text)] heading candidates from the PDF, or None without pymupdf."""
    try:
        import fitz  # type: ignore[import-not-found]
    except ImportError:
        return None

    doc = fitz.open(pdf_path)
    # The body point size anchors the small-caps band; GPO uses 10pt with 7.8pt small caps, but derive it per document to survive era drift.
    size_census: Counter[float] = Counter()
    pages = []
    for page in doc:
        d = page.get_text("dict")
        pages.append((page.rect.width, d))
        for block in d["blocks"]:
            if block.get("type") != 0:
                continue
            for line in block["lines"]:
                for span in line["spans"]:
                    if span["font"] == _ROMAN and span["text"].strip():
                        size_census[round(span["size"], 1)] += 1
    if not size_census:
        return []
    body_size = size_census.most_common(1)[0][0]
    small_band = (0.70 * body_size, 0.88 * body_size)

    raw: list[dict] = []
    for pno, (width, d) in enumerate(pages):
        for block in d["blocks"]:
            if block.get("type") != 0:
                continue
            for line in block["lines"]:
                inked = [s for s in line["spans"] if s["text"].strip()]
                if not inked:
                    continue
                if {s["font"] for s in inked} - {_ROMAN, _BOLD}:
                    continue
                text = re.sub(r"\s+", " ", "".join(s["text"] for s in line["spans"])).strip()
                if not text or _PAGE_NUMBER.match(text):
                    continue
                x0, y0, x1, y1 = line["bbox"]
                if abs((x0 + x1) / 2 - width / 2) > _MAX_CENTER_OFF:
                    continue
                if (x1 - x0) / width > _MAX_FILL:
                    continue
                sizes = {round(s["size"], 1) for s in inked}
                fonts = {s["font"] for s in inked}
                full = {s for s in sizes if abs(s - body_size) < 0.2}
                small = {s for s in sizes if small_band[0] <= s <= small_band[1]}
                if sizes - full - small:
                    continue  # masthead, TOC leaders, and other furniture sizes
                if "...." in text:
                    continue  # dotted-leader TOC/index line
                letters = [c for c in text if c.isalpha()]
                if _BOLD in fonts:
                    tier = "bold"
                elif letters and not all(c.isupper() for c in letters):
                    # True small caps render as uppercase glyphs; any lowercase means front-matter prose or a TOC entry, never a section heading.
                    continue
                elif small:
                    tier = "sc"
                else:
                    if not letters:
                        continue
                    tier = "caps"
                raw.append({"tier": tier, "text": text, "page": pno, "y0": y0, "y1": y1})

    merged: list[dict] = []
    for cand in raw:
        prev = merged[-1] if merged else None
        if (
            prev is not None
            and prev["tier"] == cand["tier"]
            and prev["page"] == cand["page"]
            and 0 <= cand["y0"] - prev["y1"] < _MERGE_GAP
        ):
            prev["text"] += " " + cand["text"]
            prev["y1"] = cand["y1"]
        else:
            merged.append(cand)
    return [{"tier": c["tier"], "text": c["text"]} for c in merged]


def pdf_headings(pdf_path: Path, cache_dir: Path) -> list[dict] | None:
    """Cached extraction: JSON sidecar per package, extracted at most once."""
    if not pdf_path.exists():
        return None
    cache = cache_dir / f"{pdf_path.stem}.json"
    if cache.exists():
        return json.loads(cache.read_text())
    heads = extract_pdf_headings(pdf_path)
    if heads is None:
        return None
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(heads))
    return heads


def _match_key(text: str) -> str:
    # Small-caps size runs can swallow inter-word spacing in extraction, so compare space-free; normalize_heading already unifies case, punctuation, and years.
    return normalize_heading(text).replace(" ", "")


def apply_pdf_tiers(
    headings: list[Heading],
    tiers: list[dict] | None,
    agencies: frozenset[str],
    bureaus: frozenset[str],
) -> None:
    """Promote headings the PDF prints in full-size caps or bold to a structural tier.

    Both sequences are in document order; SequenceMatcher disambiguates repeated heading names by position, exactly like the TOC pass. Only the caps/bold signal is acted on -- it marks agencies and major groupings the text heuristics missed (renamed agencies absent from the lexicon, one-off groupings like ENERGY PROGRAMS). GENERAL PROVISIONS and known topical heads keep their levels: a GP heading promoted to a parent tier would absorb every section after it, and GPO occasionally types INTRODUCTION in full caps.
    """
    if not tiers:
        return
    pdf_keys = [_match_key(t["text"]) for t in tiers]
    htm_keys = [_match_key(h.text) for h in headings]
    sm = difflib.SequenceMatcher(None, pdf_keys, htm_keys, autojunk=False)
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag != "equal":
            continue
        for k in range(i2 - i1):
            h = headings[j1 + k]
            tier = tiers[i1 + k]["tier"]
            if tier not in ("bold", "caps"):
                continue
            if h.is_general_provisions or h.text.upper() in TOPICAL:
                continue
            if h.level >= 3:
                kind = _kind(h.text, agencies, bureaus)
                if kind in ("annotation", "gp"):
                    continue
                h.level = 1 if kind == "agency" else 2
