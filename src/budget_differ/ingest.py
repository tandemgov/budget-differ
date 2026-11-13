"""Ingest a committee-website PDF that GPO has not yet published to GovInfo.

The Senate and House committees post their reports (and Senate "explanatory statements") on their own sites days or weeks before GovInfo carries the .htm render the rest of the pipeline reads.
Those PDFs are the same GPO composition (New Century Schoolbook body, small-caps account heads, 8pt dot-leader funding tables), so this module re-renders one into the fixed-width text GovInfo's .htm would carry:

- headings centered on their own line; small-caps heads in Title Case and full-size caps heads in CAPS, matching how GPO's .htm renders the two tiers;
- paragraphs re-wrapped at GPO's ~65 columns with a 4-space first-line indent, line-end hyphenation removed;
- dot-leader table rows joined with their right-hand amounts on one line;
- page numbers dropped; typographic quotes and dashes mapped to GPO's ASCII forms (`` '' -- ').

The output is wrapped in <html><body><pre> so `extract_pre_text` reads it unchanged, and the source PDF is kept beside it so `pdfhier` can recover heading tiers from the same file.
Prerelease documents are listed in `prerelease/catalog.json` with their source URL and SHA-256; `corpus.load_catalog` merges that list with the approps repo catalog.
"""

from __future__ import annotations

import hashlib
import html
import json
import re
import shutil
import textwrap
from collections import Counter
from pathlib import Path

_ROMAN = "NewCenturySchlbk-Roman"
_PAGE_NUMBER = re.compile(r"^\(?\d+\)?$")
# Start of an enumerated bill unit: "(a)", "(1)", "(A)", "(ii)", or a section.
_ENUMERATOR = re.compile(r"^(\([a-zA-Z0-9]{1,5}\)|S(ec|EC)\.\s)")
_LEADER = re.compile(r"\.{4,}")
_WIDTH = 65
# Smallest point size that can be body type.
_MIN_BODY_SIZE = 9.5
# Running heads and feet sit in the outer 45pt of the page.
_MARGIN = 45.0
# Bump when the conversion changes, so cached conversions are rebuilt.
CONVERTER_VERSION = 16
_RULE = 72

_CHAR_MAP = {
    "‘‘": "``",
    "’’": "''",
    "“": "``",
    "”": "''",
    "‘": "'",
    "’": "'",
    "—": "--",
    "–": "-",
    " ": " ",
    "•": "*",
    # GPO's table font prints + and - signs as these glyphs.
    "∂": "+",
    "¥": "-",
}


def _ascii(text: str) -> str:
    for k, v in _CHAR_MAP.items():
        text = text.replace(k, v)
    return text


def _is_small(span: dict, small_size: float | None, body_font: str = _ROMAN) -> bool:
    return small_size is not None and span["font"] == body_font and abs(span["size"] - small_size) < 0.15


def _line_text(spans: list[dict], small_size: float | None, body_font: str = _ROMAN) -> str:
    """Span text, with small-caps spans lowercased — GPO's .htm prints small-caps headings in Title Case.

    A line set entirely in the small size (no full-size initials) is a caps-in-small-type head, which GPO's .htm prints in CAPS, so it is left as is.
    """
    if not any(not _is_small(s, small_size, body_font) and re.search(r"[A-Za-z]", s["text"]) for s in spans):
        return "".join(s["text"] for s in spans)
    return "".join(s["text"].lower() if _is_small(s, small_size, body_font) else s["text"] for s in spans)


def _rows(page, family: str) -> list[dict]:
    """Physical text rows on a page: lines sharing a baseline are merged left to right (a dot-leader stub and its amount are separate PDF lines).

    Page furniture is dropped first: running heads and feet in the top and bottom margins (bill drafts print a file path, a timestamp, and the bill number there), and bill line numbers, which are set in a face other than the body's.
    """
    raw = []
    height = page.rect.height
    for block in page.get_text("dict")["blocks"]:
        if block.get("type") != 0:
            continue
        for line in block["lines"]:
            spans = [s for s in line["spans"] if s["text"]]
            text = "".join(s["text"] for s in spans).strip()
            if not spans or not text:
                continue
            if line["bbox"][3] < _MARGIN or line["bbox"][1] > height - _MARGIN - 7:
                continue
            if text.isdigit() and not any(s["font"].startswith(family) for s in spans):
                continue
            raw.append({"x0": line["bbox"][0], "x1": line["bbox"][2], "y0": line["bbox"][1], "y": round(line["bbox"][3], 1), "spans": spans})
    raw.sort(key=lambda r: (r["y"], r["x0"]))
    rows: list[dict] = []
    for r in raw:
        if rows and abs(rows[-1]["y"] - r["y"]) < 2.0:
            prev = rows[-1]
            prev["parts"].append(r)
            prev["x1"] = max(prev["x1"], r["x1"])
            continue
        rows.append({"y": r["y"], "y0": r["y0"], "x0": r["x0"], "x1": r["x1"], "parts": [r]})
    for row in rows:
        # Parts within a row go left to right; small-caps runs sit a fraction of a point lower and can sort ahead of the line they belong to.
        row["parts"].sort(key=lambda p: p["x0"])
        row["x0"] = row["parts"][0]["x0"]
        spans: list[dict] = []
        for p in row["parts"]:
            # Words placed as separate PDF lines on one baseline ("REQUIRING" / "AMOUNTS" / ...) carry no space glyph between them.
            if spans and p["x0"] - spans[-1]["bbox"][2] > 1.0 and not spans[-1]["text"].endswith(" ") and not p["spans"][0]["text"].startswith(" "):
                spans.append({**spans[-1], "text": " "})
            spans.extend(p["spans"])
        row["spans"] = spans
        sizes = Counter(round(s["size"], 1) for s in spans for _ in s["text"])
        row["size"] = sizes.most_common(1)[0][0]
        row["fonts"] = {s["font"] for s in spans}
    return rows


def _layout_row(parts: list[dict], left: float, col: float) -> str:
    """One ruled-table row in fixed width: a dot-leader stub keeps GPO's `stub.....amount` form, other cells sit at their column."""
    texts = [("".join(s["text"] for s in p["spans"]).strip(), p["x0"]) for p in parts]
    texts = [(t, x) for t, x in texts if t]
    scale = _RULE / col
    if texts and _LEADER.search(texts[0][0]):
        pad = " " * max(0, round((texts[0][1] - left) / 4))
        stub = pad + _LEADER.sub("", texts[0][0]).rstrip(" .")
        cells = "  ".join(t for t, _ in texts[1:])
        return f"{stub}{'.' * max(4, 56 - len(stub))}{cells.rjust(16)}"
    line = ""
    for t, x in texts:
        at = max(len(line) + (1 if line else 0), round((x - left) * scale))
        line = line.ljust(at) + t
    return line


def _wrap_heading(text: str, width: int) -> list[str]:
    """Wrap a heading so every continuation line opens on a capitalized word: the segmenter only rejoins a wrapped heading whose lines each read as headings ("of Documents" does not)."""
    words = text.split()
    lines: list[str] = []
    while words:
        # The rest fits, or is one word too long for any line (a table title set without spaces): emit it as is.
        if len(" ".join(words)) <= width or len(words) == 1:
            lines.append(" ".join(words))
            break
        fit = 1
        while fit < len(words) and len(" ".join(words[: fit + 1])) <= width:
            fit += 1
        cut = fit
        while cut > 1 and not words[cut][0].isupper():
            cut -= 1
        if cut == 1 and not words[1][0].isupper():
            cut = fit
        lines.append(" ".join(words[:cut]))
        words = words[cut:]
    return lines


def _dehyphen_join(lines: list[str], vocab: set[str]) -> str:
    """Join wrapped lines, removing line-end hyphens that split a word (kept when the hyphenated compound is attested elsewhere and the closed form is not)."""
    text = ""
    for ln in lines:
        ln = ln.strip()
        if not text:
            text = ln
            continue
        m = re.search(r"(\w+)-$", text)
        if m and ln[:1].isalpha():
            head = m.group(1)
            tail = re.match(r"[\w']+", ln)
            tail_w = tail.group(0) if tail else ""
            closed = (head + tail_w).lower()
            hyph = f"{head}-{tail_w}".lower()
            # Keep the hyphen for a break before a capitalized name ("Lewis-/Houghton"), inside an existing compound ("day-to-/day"), when only the hyphenated form is attested, or when both halves are words and the closed form is unattested ("zero-/base"); otherwise the hyphen was the typesetter's.
            name = tail_w[:1].isupper() and not tail_w.isupper()
            compound = re.search(r"\w-\w+-$", text) is not None or re.match(r"[\w']+-\w", ln) is not None
            halves = len(head) >= 3 and len(tail_w) >= 3 and head.lower() in vocab and tail_w.lower() in vocab
            # Inside a compound, a whole-word tail keeps the hyphen ("day-to-/day") while a fragment does not ("non-con-/fidential").
            if re.search(r"\w-\w+-$", text) and tail_w.lower() in vocab:
                text = text + ln
            elif closed in vocab and not name:
                text = text[:-1] + ln
            elif name or compound or hyph in vocab or halves:
                text = text + ln
            else:
                text = text[:-1] + ln
        elif text.endswith(("-", "\u2014", "\u2013")):
            # A hyphen before a numeral ("Public Law 95-/94") or a dash ("Traditions.\u2014/The") joins without a space.
            text = text + ln
        else:
            text = f"{text} {ln}"
    return re.sub(r"\s+", " ", text)


def pdf_to_gpo_text(pdf_path: Path) -> str:
    """Re-render a GPO-composed committee PDF as GovInfo-style fixed-width text."""
    import fitz  # type: ignore[import-not-found]

    doc = fitz.open(pdf_path)
    # The body face is the most-set font: New Century Schoolbook in reports, DeVinne in bills.
    fonts: Counter[tuple[str, float]] = Counter()
    for page in doc:
        for block in page.get_text("dict")["blocks"]:
            for line in block.get("lines", []):
                for s in line["spans"]:
                    fonts[(s["font"], round(s["size"], 1))] += len(s["text"])
    # Body type is never under 9.5pt (10pt reports, 14pt bills); table type is 5-9pt and outweighs the prose in table-heavy reports such as Defense, so it is left out of the vote.
    text_fonts = Counter({k: n for k, n in fonts.items() if k[1] >= _MIN_BODY_SIZE}) or fonts
    body_font, body_size = text_fonts.most_common(1)[0][0]
    family = body_font.split("-")[0]
    census = Counter({sz: n for (f, sz), n in fonts.items() if f == body_font})
    # Small caps are the body-face size just under body (7.8 against 10pt in reports, 10.9 against 14pt in bills); 8pt is report table type.
    small = [sz for sz in census if 0.7 * body_size <= sz < 0.8 * body_size]
    small_size = max(small, key=lambda sz: census[sz]) if small else None
    em = body_size

    pages = [(page.rect.width, _rows(page, family)) for page in doc]
    # Bill prints number their lines (dropped in _rows); body type above 12pt is the giveaway that survives the drop.
    bill_layout = body_size >= 12
    body_rows = [r for _, rows in pages for r in rows if r["size"] == body_size]
    left = Counter(round(r["x0"]) for r in body_rows).most_common(1)[0][0]
    right = Counter(round(r["x1"]) for r in body_rows).most_common(1)[0][0]
    center = (left + right) / 2
    col = right - left

    # Vocabulary for hyphenation decisions: every whole token as printed, before any joining. A line's first token and a hyphen-broken last token may be word fragments ("accom-" / "plished"), so they are left out.
    vocab: set[str] = set()
    for _, rows in pages:
        for r in rows:
            line = "".join(s["text"] for s in r["spans"]).rstrip()
            toks = re.findall(r"[A-Za-z][\w'-]*[A-Za-z]", line)[1:]
            if line.endswith("-") and toks:
                toks = toks[:-1]
            vocab.update(w.lower() for w in toks)

    out: list[str] = []
    para: list[str] = []
    heading: list[str] = []
    last_heading_y: list[float] = []
    after_table: list[bool] = []
    in_ruled: list[bool] = []

    def flush_para() -> None:
        if para:
            text = _ascii(_dehyphen_join(para, vocab))
            if text.startswith(("--", "*")):
                # Dash-list items: GPO's .htm sets them "  --item" with 8-space hanging continuation lines, and a continuation line in Title Case ("Senate Committee on Finance (or to the House and the") reads as a centered heading.
                # One unwrapped line keeps the item's text and cannot pass as a heading (headings never exceed the wrap width).
                out.append("  " + text)
            else:
                out.extend(textwrap.wrap(text, _WIDTH, initial_indent="    ", break_on_hyphens=False, break_long_words=False))
            para.clear()

    def flush_heading() -> None:
        if heading:
            text = _ascii(_dehyphen_join(heading, vocab))
            out.append("")
            for ln in _wrap_heading(text, _WIDTH - 6):
                out.append(ln.center(_WIDTH + 7).rstrip())
            out.append("")
            heading.clear()

    for _, rows in pages:
        for r in rows:
            text = _line_text(r["spans"], small_size, body_font).rstrip()
            plain = "".join(s["text"] for s in r["spans"]).strip()
            # Page furniture: folios top and bottom.
            if _PAGE_NUMBER.match(plain) and r["size"] < body_size + 0.1:
                continue
            # Body-size type in the body faces marks prose or a heading (a small-caps heading still opens on a body-size capital); anything else is table or stub type.
            is_table = not any(
                s["font"].startswith(family) and abs(s["size"] - body_size) < 0.15 and s["text"].strip()
                for s in r["spans"]
            )
            if in_ruled:
                out.extend(["-" * _RULE, ""])
                in_ruled.clear()
            mid = (r["x0"] + r["x1"]) / 2
            width = r["x1"] - r["x0"]
            letters = re.sub(r"[^A-Za-z]", "", plain)
            caps = bool(letters) and letters.isupper()
            centered = abs(mid - center) < 30 and width < 0.85 * col and r["x0"] > left + 12
            all_small = all(_is_small(s, small_size, body_font) for s in r["spans"] if s["text"].strip())
            # A head set entirely in small caps (report sub-heads; every account head in a bill) is a heading, not table type, despite its size.
            if is_table and all_small and caps and (centered or len(letters) >= 12) and not _LEADER.search(plain):
                is_table = False
            if is_table:
                flush_para()
                flush_heading()
                parts = ["".join(s["text"] for s in p["spans"]).strip() for p in r["parts"]]
                if not any(s["font"].startswith(family) for s in r["spans"]):
                    # Ruled-table type (TradeGothic): GPO's .htm sets these between dashed rules with cells laid out by column, which is what the table detector keys on.
                    if not in_ruled:
                        out.extend(["", "-" * _RULE])
                        in_ruled.append(True)
                    out.append(_ascii(_layout_row(r["parts"], left, col)))
                    continue
                if in_ruled:
                    out.extend(["-" * _RULE, ""])
                    in_ruled.clear()
                # Stub indentation carries the outline level (contents, nested table rows): GPO steps 16pt per level in 8pt type, 4 columns in the .htm.
                pad = " " * max(0, round((r["x0"] - left) / 4))
                if len(parts) > 1 and _LEADER.search(parts[0]):
                    stub = pad + _LEADER.sub("", parts[0]).rstrip(" .")
                    amounts = "  ".join(parts[1:])
                    line = f"{stub}{'.' * max(4, 56 - len(stub))}{amounts.rjust(16)}"
                else:
                    line = pad + "  ".join(parts)
                out.append(_ascii(line))
                after_table[:] = [True]
                continue
            has_small = any(_is_small(s, small_size, body_font) and s["text"].strip() for s in r["spans"])
            # A full-width line of capitals is the first line of a wrapped heading — unless it continues an unfinished sentence, as a heading quoted in small caps does in bill text ("under the heading ``SEN-" / "ATE--CONTINGENT EXPENSES OF THE SENATE'' ...").
            mid_sentence = bool(para) and not para[-1].rstrip().endswith((".", ":", ";"))
            if caps and not mid_sentence and (centered or has_small or len(letters) >= 12):
                flush_para()
                # Wrapped-heading continuation lines sit ~2pt below the previous line; distinct stacked headings sit 6-8pt apart (same measure as pdfhier).
                # Bills print every line on one fixed pitch, so there a continuation is recognized by the line above having run out of width instead.
                tight = last_heading_y and -1.0 <= r["y0"] - last_heading_y[0] < 4.0
                # A full line followed by one in another style (full caps over small caps: "OFFICE OF CONGRESSIONAL WORKPLACE RIGHTS" / "Salaries and Expenses") is two headings.
                full = last_heading_y and last_heading_y[1] >= 0.75 * col and (bill_layout or last_heading_y[2] == has_small)
                if heading and not (tight or full):
                    flush_heading()
                heading.append(text)
                last_heading_y[:] = [r["y"], width, has_small]
                continue
            flush_heading()
            if after_table:
                out.append("")
                after_table.clear()
            # Any indented line opens a paragraph (one em in reports; two ems, and deeper for subsections, in bills) — except the two-em hanging continuation lines of a report dash list.
            indent = (r["x0"] - left) / em
            hanging = bool(para) and para[0].lstrip().startswith(("\u2014", "--", "\u2022")) and indent >= 1.5
            # A word broken across lines ("as-" / "sistants") always continues, whatever the next line's indent (bill subsections indent their continuation lines).
            broken = bool(para) and re.search(r"[a-z]-$", para[-1].rstrip()) is not None
            # Bills indent the continuation lines of a nested subsection to its level, so there an indented line opens a paragraph only when it starts an enumerated unit or the line above finished a clause.
            continues = (
                bill_layout
                and bool(para)
                and not _ENUMERATOR.match(plain)
                and not para[-1].rstrip().endswith((".", ":", ";", "--", "\u2014"))
            )
            if indent >= 0.5 and para and not hanging and not broken and not continues:
                flush_para()
            para.append(text)
    flush_para()
    flush_heading()
    # Collapse runs of blank lines.
    lines: list[str] = []
    for ln in out:
        if ln == "" and lines and lines[-1] == "":
            continue
        lines.append(ln)
    return "\n".join(lines).strip("\n") + "\n"


def converted_text(pdf_path: Path) -> str:
    """GPO-style .htm text for a PDF, cached by the PDF's SHA-256 next to the pdfhier cache."""
    from budget_differ.config import pdfhier_cache_dir

    digest = hashlib.sha256(pdf_path.read_bytes()).hexdigest()[:16]
    cache = pdfhier_cache_dir() / "converted" / f"{pdf_path.stem}-{digest}-v{CONVERTER_VERSION}.htm"
    if cache.exists():
        return cache.read_text()
    write_gpo_htm(pdf_to_gpo_text(pdf_path), pdf_path.stem, cache)
    return cache.read_text()


def write_gpo_htm(text: str, title: str, out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        f"<html>\n<title>{html.escape(title)}</title>\n<body><pre>\n{html.escape(text, quote=False)}</pre></body>\n</html>\n"
    )


def prerelease_dir() -> Path:
    return Path(__file__).resolve().parents[2] / "prerelease"


def prerelease_catalog_path() -> Path:
    return prerelease_dir() / "catalog.json"


def load_prerelease() -> list[dict]:
    path = prerelease_catalog_path()
    return json.loads(path.read_text()) if path.exists() else []


def ingest(
    pdf: Path,
    package_id: str,
    chamber: str,
    subcommittee: str,
    fiscal_year: int,
    congress: int,
    title: str,
    url: str = "",
    date_issued: str = "",
    kind: str = "report",
    source: str = "committee website (prerelease; not yet on GovInfo)",
) -> Path:
    """Convert a committee PDF into prerelease/<package_id>.htm (+ .pdf) and upsert its catalog entry."""
    root = prerelease_dir()
    root.mkdir(parents=True, exist_ok=True)
    pdf_dst = root / f"{package_id}.pdf"
    if pdf.resolve() != pdf_dst.resolve():
        shutil.copyfile(pdf, pdf_dst)
    htm = root / f"{package_id}.htm"
    write_gpo_htm(pdf_to_gpo_text(pdf_dst), title, htm)
    entry = {
        "package_id": package_id,
        "congress": congress,
        "chamber": chamber,
        "title": title,
        "subcommittee": subcommittee,
        "fiscal_year": fiscal_year,
        "stage": "committee",
        "kind": kind,
        "date_issued": date_issued,
        "source": source,
        "pdf_url": url,
        "pdf_sha256": hashlib.sha256(pdf_dst.read_bytes()).hexdigest(),
        "local_path": f"{package_id}.htm",
    }
    entries = [e for e in load_prerelease() if e["package_id"] != package_id] + [entry]
    entries.sort(key=lambda e: e["package_id"])
    prerelease_catalog_path().write_text(json.dumps(entries, indent=2) + "\n")
    return htm
