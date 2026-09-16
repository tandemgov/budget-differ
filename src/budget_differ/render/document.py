"""The full-document view of a pair: the newer report as written, in its own order, redlined against the older one with notes in a right-hand column."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from budget_differ.corpus import Pair
from budget_differ.models import ChangeClass, PairDiff, Paragraph, ParagraphDiff, SectionDiff
from budget_differ.policy import REVIEW
from budget_differ.render.assets import DOC_JS, OUTLINE_JS
from budget_differ.render.html import (
    _anchor,
    _anchor_of,
    _chip,
    _esc,
    _move_note,
    _render_flags,
    _render_word_diff,
    _source_links,
    page,
    view_tabs,
)
from budget_differ.render.outline import document_order, paragraph_order, render_outline

# Headings deeper than this share the smallest heading style.
MAX_HEADING_DEPTH = 4


def render_document(
    pair: Pair,
    diff: PairDiff,
    out_dir: Path,
    nav_html: str = "<nav></nav>",
    section_hrefs: dict[int, str] | None = None,
) -> Path:
    """Write document.html next to the pair's ranked index.html; both pages share section anchors."""
    out_dir.mkdir(parents=True, exist_ok=True)
    old_fy, new_fy = pair.old.fiscal_year or 0, pair.new.fiscal_year or 0
    moves_out = {id(m.diff.old): m for m in diff.moves}
    moves_in = {id(m.diff.new): m for m in diff.moves}
    title = (
        f"{pair.new.subcommittee} ({pair.new.chamber.title()}): "
        f"FY{new_fy} as written, compared with FY{old_fy}"
    )
    sections = [
        _render_doc_section(sd, old_fy, new_fy, moves_out, moves_in, section_hrefs or {})
        for sd in document_order(diff)
    ]
    body = "\n".join(
        [
            f"<h1>{_esc(title)}</h1>",
            '<div class="meta">'
            f"{_source_links(pair.old)} → {_source_links(pair.new)}"
            f"<br>The FY{new_fy} report in its printed order, money tables omitted. "
            f"Insertions are green and FY{old_fy} deletions are struck through; "
            f"sections dropped since FY{old_fy} appear where they stood. "
            "Notes on the right give each change's class, policy signals, and moves.</div>",
            view_tabs(pair, "document"),
            '<div class="controls">'
            f'<label><input type="checkbox" id="d-del" checked> show FY{old_fy} deletions</label>'
            '<label><input type="checkbox" id="d-ins" checked> highlight insertions</label>'
            '<label><input type="checkbox" id="d-notes" checked> notes</label>'
            '<span class="stepper">'
            '<button type="button" id="prevchg" title="previous change (k)">&uarr; prev</button>'
            '<button type="button" id="nextchg" title="next change (j)">next change &darr;</button>'
            "</span>"
            '<span class="fcount" id="fcount"></span>'
            '<div class="crumbs" id="crumbs"></div>'
            "</div>",
            f'<div class="doc" id="doc">{"".join(sections)}</div>',
        ]
    )
    out_path = out_dir / "document.html"
    out_path.write_text(
        page(
            _esc(title),
            "../style.css",
            DOC_JS + OUTLINE_JS,
            body,
            nav_html,
            outline=render_outline(diff),
            wide=True,
        )
    )
    return out_path


def _row(kind: str, text_html: str, note_html: str = "") -> str:
    """One paragraph: text on the left, its note on the right. kind drives the toggles and the change stepper."""
    changed = "" if kind in ("same", "dhead") else " changed"
    return (
        f'<div class="drow {kind}{changed}"><div class="dtext">{text_html}</div>'
        f'<div class="dnote">{note_html}</div></div>'
    )


def _review_flags_note(pd: ParagraphDiff) -> str:
    """Review-tier flags only: the inline redline already shows what a figure changed from and to."""
    return _render_flags(replace(pd, flags=[f for f in pd.flags if f.tier >= REVIEW]))


def _tags_note(tags: list[str]) -> str:
    return f'<div class="tags">contains: {_esc(", ".join(tags))}</div>' if tags else ""


def _added_row(p: Paragraph, moves_in: dict, tags: list[str], new_fy: int) -> str:
    move = moves_in.get(id(p))
    if move is None:
        return _row(
            "added",
            f'<div class="para added-para">{_esc(p.text)}</div>',
            f'<span class="chip new">new in FY{new_fy}</span>{_tags_note(tags)}',
        )
    edited = move.diff.change != ChangeClass.UNCHANGED
    text = _render_word_diff(move.diff) if edited else _esc(p.text)
    note = _move_note(move, outgoing=False) + (_review_flags_note(move.diff) if edited else "")
    return _row("moved-in", f'<div class="para moved-para">{text}</div>', note)


def _removed_row(p: Paragraph, moves_out: dict, tags: list[str], old_fy: int) -> str:
    move = moves_out.get(id(p))
    if move is None:
        return _row(
            "removed del-row",
            f'<div class="para removed-para">{_esc(p.text)}</div>',
            f'<span class="chip dropped">dropped from FY{old_fy}</span>{_tags_note(tags)}',
        )
    return _row(
        "moved-out del-row",
        f'<div class="para moved-para moved-away">{_esc(p.text)}</div>',
        _move_note(move, outgoing=True),
    )


def _section_note(sd: SectionDiff, old_fy: int, new_fy: int, section_hrefs: dict[int, str]) -> str:
    parts: list[str] = []
    if sd.change != ChangeClass.UNCHANGED:
        parts.append(_chip(sd.change))
    if sd.renamed_from is not None:
        parts.append(
            f'<div class="related">renamed; was &ldquo;{_esc(sd.renamed_from)}&rdquo; in FY{old_fy}</div>'
        )
    if sd.related is not None:
        word, fy = ("successor", new_fy) if sd.change == ChangeClass.REMOVED else ("predecessor", old_fy)
        parts.append(
            f'<div class="related">possible {word} in FY{fy}: '
            f'<a href="#{_anchor_of(sd.related.sd, sd.related.path)}">{_esc(sd.related.heading)}</a> '
            f"({sd.related.overlap:.0f}% content overlap)</div>"
        )
    spans = max(sec.table_spans for sec in (sd.old, sd.new) if sec is not None)
    if spans:
        parts.append(f'<div class="tables-note">&#9888; {spans} money table(s) omitted</div>')
    links = [f'<a href="index.html#{_anchor(sd)}">ranked view</a>']
    href = section_hrefs.get(id(sd.new)) or section_hrefs.get(id(sd.old))
    if href:
        links.append(f'<a href="{_esc(href)}">thread history</a>')
    parts.append(f'<div class="dlinks">{" &middot; ".join(links)}</div>')
    return "".join(parts)


def _render_doc_section(
    sd: SectionDiff,
    old_fy: int,
    new_fy: int,
    moves_out: dict,
    moves_in: dict,
    section_hrefs: dict[int, str],
) -> str:
    sec = sd.new or sd.old
    assert sec is not None
    depth = min(len(sd.display_path) - 1, MAX_HEADING_DEPTH)
    status = {ChangeClass.ADDED: " added", ChangeClass.REMOVED: " dropped"}.get(sd.change, "")
    out = [
        f'<section class="docsec{status}" id="{_anchor(sd)}" data-spy>',
        _row(
            "dhead",
            f'<div class="dh d{depth}">{_esc(sec.heading)}</div>',
            _section_note(sd, old_fy, new_fy, section_hrefs),
        ),
    ]
    if sd.change == ChangeClass.ADDED:
        out.extend(_added_row(p, moves_in, [], new_fy) for p in sec.paragraphs)
    elif sd.change == ChangeClass.REMOVED:
        out.extend(_removed_row(p, moves_out, [], old_fy) for p in sec.paragraphs)
    else:
        for pd in paragraph_order(sd):
            if pd.old is None:
                assert pd.new is not None
                out.append(_added_row(pd.new, moves_in, pd.tags, new_fy))
            elif pd.new is None:
                out.append(_removed_row(pd.old, moves_out, pd.tags, old_fy))
            elif pd.change == ChangeClass.UNCHANGED:
                out.append(_row("same", f'<div class="para">{_esc(pd.new.text)}</div>'))
            else:
                out.append(
                    _row(
                        "edited",
                        f'<div class="para">{_render_word_diff(pd)}</div>',
                        f"{_chip(pd.change)}{_review_flags_note(pd)}",
                    )
                )
    out.append("</section>")
    return "\n".join(out)
