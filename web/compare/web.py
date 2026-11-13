"""Compare two GPO-typeset PDFs with budget-differ, inside the browser (Pyodide, in a Web Worker).

The worker calls `compare`; it returns the ranked and full-document pages as HTML strings, ready for a sandboxed iframe.
Tab and section links between the two pages are rewritten to `data-bd-view` links that a small bridge script turns into messages to the host page, since a sandboxed frame cannot navigate to sibling files.
"""

from __future__ import annotations

import json
import re
import tempfile
from collections import Counter
from pathlib import Path

import fitz

from budget_differ.compare import compare_documents
from budget_differ.corpus import CatalogEntry, Pair
from budget_differ.ingest import pdf_to_gpo_text
from budget_differ.render import render_pair
from budget_differ.render.assets import CSS
from budget_differ.segment import segment_report
from budget_differ.segment.pdfhier import extract_pdf_headings

GPO_FACES = ("NewCenturySchlbk", "DeVinne")

# Runs inside the results frame: forwards view-switch clicks to the host page and scrolls on request.
BRIDGE_JS = (
    "document.addEventListener('click',function(e){var a=e.target.closest('a[data-bd-view]');if(!a)return;"
    "e.preventDefault();parent.postMessage({bd:'view',view:a.getAttribute('data-bd-view'),anchor:a.getAttribute('data-bd-anchor')||''},'*');});"
    "window.addEventListener('message',function(e){if(e.source!==parent||!e.data||e.data.bd!=='scroll')return;"
    "var el=document.getElementById(e.data.anchor);if(el)el.scrollIntoView();});"
)

_LINK = re.compile(r'href="(index|document)\.html(?:#([\w-]*))?"')


class InputError(ValueError):
    """A problem with the dropped files, worded for the person who dropped them."""


def load_lexicon(path: str) -> tuple[frozenset[str], frozenset[str]]:
    data = json.loads(Path(path).read_text())
    return frozenset(data["agencies"]), frozenset(data["bureaus"])


def describe(pdf: Path) -> dict:
    """What the converter needs to know before trusting a file: its body face, bill or report, fiscal year, chamber."""
    try:
        doc = fitz.open(pdf)
    except Exception as exc:  # pymupdf raises several types for unreadable files
        raise InputError("This file could not be opened as a PDF.") from exc
    fonts: Counter[tuple[str, float]] = Counter()
    for page in doc:
        for block in page.get_text("dict")["blocks"]:
            for line in block.get("lines", []):
                for span in line["spans"]:
                    fonts[(span["font"], round(span["size"], 1))] += len(span["text"])
    body = Counter({k: n for k, n in fonts.items() if k[1] >= 9.5}) or fonts
    if not body:
        raise InputError("This PDF has no text layer (it may be a scan), so it can't be compared.")
    (font, size), _ = body.most_common(1)[0]
    head = " ".join(" ".join(doc[i].get_text() for i in range(min(3, len(doc)))).upper().split())
    year = re.search(r"SEPTEMBER 30, (\d{4})|BILL, (\d{4})|APPROPRIATIONS(?: ACT)?, (\d{4})", head)
    senate = any(k in head for k in ("IN THE SENATE", "SENATE REPORT", "SEN. APPRO", "EXPLANATORY STATEMENT"))
    return {
        "font": font,
        "gpo": font.startswith(GPO_FACES),
        "bill": size >= 12,
        "legislative": "LEGISLATIVE BRANCH" in head,
        "fy": int(next(g for g in year.groups() if g)) if year else 0,
        "chamber": "senate" if senate else ("house" if "HOUSE OF REPRESENTATIVES" in head else ""),
    }


def _pages(old: dict, new: dict, old_text: str, new_text: str, pdfs: dict, lexicon: tuple) -> dict:
    agencies, bureaus = lexicon
    sub = "Legislative-Branch" if new["legislative"] else "Appropriations"
    docs = {}
    for side, info, text in (("old", old, old_text), ("new", new, new_text)):
        pdf = pdfs.get(side)
        docs[side] = segment_report(
            "<pre>\n" + text + "</pre>",
            package_id=side,
            chamber=info["chamber"],
            subcommittee=sub,
            fiscal_year=info["fy"],
            agencies=agencies,
            bureaus=bureaus,
            pdf_tiers=extract_pdf_headings(pdf) if pdf else None,
        )
    diff = compare_documents(docs["old"], docs["new"])

    def entry(info: dict) -> CatalogEntry:
        return CatalogEntry(
            info["name"], 0, new["chamber"] or old["chamber"], sub + (" bill text" if new["bill"] else ""),
            info["fy"] or None, "committee", "", "", local_path=info["name"], source="dropped in",
        )

    out = Path(tempfile.mkdtemp())
    render_pair(Pair(new=entry(new), old=entry(old)), diff, out)
    pages = {}
    for name in ("index", "document"):
        html = (out / f"{name}.html").read_text()
        html = html.replace('<link rel="stylesheet" href="../style.css">', f"<style>{CSS}</style>")
        html = _LINK.sub(lambda m: f'href="#{m.group(2) or ""}" data-bd-view="{m.group(1)}" data-bd-anchor="{m.group(2) or ""}"', html)
        html = html.replace("</body>", f"<script>{BRIDGE_JS}</script>\n</body>")
        pages[name] = html
    return {"pages": pages, "counts": diff.counts(), "old": old, "new": new}


def compare(old_pdf: str, new_pdf: str, old_name: str, new_name: str, lexicon_path: str) -> dict:
    """Compare two dropped PDFs; raises InputError with a message for the person when they can't be compared."""
    infos = {}
    for side, path, name in (("old", old_pdf, old_name), ("new", new_pdf, new_name)):
        info = describe(Path(path))
        label = "prior-year" if side == "old" else "this year's"
        if not info["gpo"]:
            raise InputError(
                f"The {label} file ({name}) is set in {info['font']}, not GPO's report or bill type, so it can't be read reliably. "
                "Use a committee report, explanatory statement, or bill PDF from GovInfo or a committee site."
            )
        info["name"] = name
        infos[side] = info
    if infos["old"]["bill"] != infos["new"]["bill"]:
        raise InputError("One file is a bill and the other a report. Compare a bill with a bill, or a report with a report.")
    texts = {side: pdf_to_gpo_text(Path(p)) for side, p in (("old", old_pdf), ("new", new_pdf))}
    return _pages(infos["old"], infos["new"], texts["old"], texts["new"],
                  {"old": Path(old_pdf), "new": Path(new_pdf)}, load_lexicon(lexicon_path))


def compare_texts(old_text: str, new_text: str, lexicon_path: str) -> dict:
    """Self-test entry: compare two GPO-style texts directly (no PDF), so a check can feed hostile text through the renderer."""
    info = {"gpo": True, "bill": False, "legislative": True, "fy": 0, "chamber": "senate", "font": ""}
    return _pages({**info, "name": "old.txt", "fy": 2026}, {**info, "name": "new.txt", "fy": 2027},
                  old_text, new_text, {}, load_lexicon(lexicon_path))
