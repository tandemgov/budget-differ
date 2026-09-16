"""Emit self-contained static HTML: one page per report pair plus a top index."""

from __future__ import annotations

import html
from dataclasses import dataclass
from pathlib import Path
from string import Template

from budget_differ.anchors import section_anchor
from budget_differ.corpus import CatalogEntry, Pair
from budget_differ.models import ChangeClass, PairDiff, SectionDiff
from budget_differ.policy import REVIEW, PolicyFlag
from budget_differ.render.assets import CSS, JS, OUTLINE_JS
from budget_differ.render.outline import render_outline

_PAGE = Template(
    """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>$title</title>
<link rel="stylesheet" href="$cssref">
</head>
<body>
<div class="layout$layoutclass">
<div class="leftcol$leftclass">
$nav
$outline
</div>
<main>
$body
</main>
</div>
<script>$js</script>
</body>
</html>
"""
)


def page(
    title: str, cssref: str, js: str, body: str, nav: str, outline: str = "", wide: bool = False
) -> str:
    """The page shell. An outline joins the committee links in the sticky left column; wide pages make room for an annotation column."""
    return _PAGE.substitute(
        title=title,
        cssref=cssref,
        js=js,
        body=body,
        nav=nav,
        outline=outline,
        layoutclass=" wide" if wide else "",
        leftclass=" has-outline" if outline else "",
    )


@dataclass
class NavItem:
    chamber: str
    label: str  # subcommittee display name
    dir: str  # chain page directory, the longitudinal hub for the group


def render_nav(items: list[NavItem], current_dir: str, prefix: str) -> str:
    """Left sidebar: chamber → subcommittee links to each group's longitudinal page."""
    if not items:
        return "<nav></nav>"
    out = ['<nav class="sidenav">']
    # Mobile: the checkbox/label pair collapses the link list behind a "Committees" toggle so 26 links don't precede the content; desktop CSS hides the toggle and always shows the list.
    out.append('<input type="checkbox" id="navtoggle" class="navtoggle-box">')
    out.append(
        f'<a class="navhome{" current" if current_dir == "." else ""}" '
        f'href="{prefix}index.html">All report pairs</a>'
    )
    out.append('<label for="navtoggle" class="navburger">&#9776; Committees</label>')
    out.append('<div class="navlinks">')
    for chamber in ("house", "senate"):
        group = [it for it in items if it.chamber == chamber]
        if not group:
            continue
        out.append(f'<div class="navhead">{chamber.title()}</div>')
        for it in group:
            cls = "navlink current" if it.dir == current_dir else "navlink"
            out.append(
                f'<a class="{cls}" href="{prefix}{_esc(it.dir)}/index.html">{_esc(it.label)}</a>'
            )
    out.append("</div></nav>")
    return "\n".join(out)


def _esc(s: str) -> str:
    return html.escape(s, quote=True)


def _pdf_url(entry: CatalogEntry) -> str:
    """Catalog rows predating pdf_url fall back to the canonical GovInfo content path."""
    return entry.pdf_url or (
        f"https://www.govinfo.gov/content/pkg/{entry.package_id}"
        f"/pdf/{entry.package_id}.pdf"
    )


def _source_links(entry: CatalogEntry) -> str:
    """Package id followed by the source documents themselves — PDF and HTML — then the GovInfo landing page."""
    links = [f'<a href="{_esc(_pdf_url(entry))}">PDF</a>']
    if entry.html_url:
        links.append(f'<a href="{_esc(entry.html_url)}">HTML</a>')
    links.append(
        f'<a href="https://www.govinfo.gov/app/details/{_esc(entry.package_id)}">GovInfo</a>'
    )
    return f'{_esc(entry.package_id)} ({" &middot; ".join(links)})'


def _pdf_link(entry: CatalogEntry, label: str) -> str:
    """Compact form for the chain page, where a dozen years share one line: the label itself is the PDF link."""
    return f'<a href="{_esc(_pdf_url(entry))}">{_esc(label)}</a>'


def _chip(change: ChangeClass) -> str:
    cls = change.label.replace(" ", "-")
    return f'<span class="chip {cls}">{_esc(change.label)}</span>'


def _anchor(sd: SectionDiff) -> str:
    return sd.anchor or section_anchor(sd.display_path)


def _anchor_of(sd: SectionDiff | None, path: tuple[str, ...]) -> str:
    """Anchor of a linked section: its own diff's when known, else the first section on the page with that path."""
    return _anchor(sd) if sd is not None else section_anchor(path)


def _render_word_diff(pd) -> str:
    parts: list[str] = []
    for tag, old_tokens, new_tokens in pd.opcodes:
        if tag == "equal":
            parts.append(_esc(" ".join(old_tokens)))
        else:
            if old_tokens:
                parts.append(f"<del>{_esc(' '.join(old_tokens))}</del>")
            if new_tokens:
                parts.append(f"<ins>{_esc(' '.join(new_tokens))}</ins>")
    return " ".join(parts)


def _move_note(move, outgoing: bool, anchor_base: str = "") -> str:
    if outgoing:
        target, heading = _anchor_of(move.new_sd, move.new_section_path), move.new_section_heading
        arrow, verb = "&#8594;", "moved to"
    else:
        target, heading = _anchor_of(move.old_sd, move.old_section_path), move.old_section_heading
        arrow, verb = "&#8592;", "moved from"
    status = "unchanged" if move.diff.change == ChangeClass.UNCHANGED else "edited"
    return (
        f'<div class="movenote">{arrow} {verb} '
        f'<a href="{anchor_base}#{target}">{_esc(heading)}</a> ({status})</div>'
    )


def _review_flags(sd: SectionDiff) -> list[PolicyFlag]:
    return [f for f in sd.flags if f.tier >= REVIEW]


def _flag_badges(flags: list[PolicyFlag]) -> str:
    cats = sorted({f.label for f in flags if f.tier >= REVIEW})
    return "".join(f'<span class="flag">&#9873; {_esc(c)}</span>' for c in cats)


def _snippet(side: tuple[str, str, str], tag: str) -> str:
    pre, mid, post = side
    mid_html = f"<{tag}>{_esc(mid)}</{tag}>" if mid else f'<span class="gap">&#8248;</span>'
    return f"{_esc(pre)} {mid_html} {_esc(post)}"


def _render_flags(pd) -> str:
    """Flag list under a paired paragraph: category, why it matters, and the before/after language."""
    if not pd.flags:
        return ""
    items = []
    for f in pd.flags:
        cls = "flagitem" if f.tier >= REVIEW else "flagitem note"
        items.append(
            f'<li class="{cls}"><span class="flag{"" if f.tier >= REVIEW else " note"}">'
            f"{'&#9873; ' if f.tier >= REVIEW else ''}{_esc(f.label)}</span> {_esc(f.reason)}</li>"
        )
    return f'<ul class="flags">{"".join(items)}</ul>'


def _render_tags(pd) -> str:
    if not pd.tags:
        return ""
    return f'<div class="tags">contains: {_esc(", ".join(pd.tags))}</div>'


def _has_directive(sd: SectionDiff) -> bool:
    sec = sd.new or sd.old
    assert sec is not None
    if any(p.kind == "directive" for p in sec.paragraphs):
        return True
    return any(
        (pd.new or pd.old).kind == "directive"
        for pd in sd.paragraph_diffs
        if (pd.new or pd.old) is not None
    )


def _render_section(
    sd: SectionDiff,
    old_fy: int,
    new_fy: int,
    moves_out: dict[int, object] | None = None,
    moves_in: dict[int, object] | None = None,
    section_hrefs: dict[int, str] | None = None,
    anchor_base: str = "",
    document_href: str = "document.html",
) -> str:
    """document_href: the pair's full-document page, relative to where this section is rendered."""
    moves_out = moves_out or {}
    moves_in = moves_in or {}
    sec = sd.new or sd.old
    assert sec is not None
    has_directive = _has_directive(sd)
    thread_link = ""
    if section_hrefs:
        # Keyed by id(Section): a bare path cannot name a general provision's row (birth-year suffix) or a sub-head's (rolled into its account).
        href = section_hrefs.get(id(sd.new)) or section_hrefs.get(id(sd.old))
        if href:
            thread_link = f' <a class="ctx" href="{_esc(href)}">thread history &rarr;</a>'
    thread_link += f' <a class="ctx" href="{_esc(document_href)}#{_anchor(sd)}">in full document &rarr;</a>'
    flagged = bool(_review_flags(sd))
    out: list[str] = [
        f'<section class="section" id="{_anchor(sd)}" data-spy data-change="{sd.change.label.replace(" ", "-")}" '
        f'data-directive="{1 if has_directive else 0}" data-flagged="{1 if flagged else 0}">',
        f"<h3>{_esc(sec.heading)} {_chip(sd.change)}{_flag_badges(sd.flags)}{thread_link}</h3>",
        f'<div class="pathline">{_esc(" › ".join(sd.display_path[:-1]))}</div>',
    ]
    notes = []
    if sd.old and sd.old.table_spans:
        notes.append(f"{sd.old.table_spans} table region(s) skipped in prior year")
    if sd.new and sd.new.table_spans:
        notes.append(f"{sd.new.table_spans} table region(s) skipped in proposed year")
    if notes:
        out.append(f'<div class="tables-note">&#9888; {_esc("; ".join(notes))}</div>')

    if sd.renamed_from is not None:
        out.append(
            f'<div class="related">&#10142; renamed &mdash; was &ldquo;{_esc(sd.renamed_from)}&rdquo; '
            f"in FY{old_fy}</div>"
        )
    if sd.related is not None:
        if sd.change == ChangeClass.REMOVED:
            word, fy = "successor", new_fy
        else:
            word, fy = "predecessor", old_fy
        out.append(
            f'<div class="related">&#10142; possible {word} in FY{fy}: '
            f'<a href="{anchor_base}#{_anchor_of(sd.related.sd, sd.related.path)}">{_esc(sd.related.heading)}</a> '
            f"({sd.related.overlap:.0f}% content overlap)</div>"
        )

    if sd.change == ChangeClass.ADDED:
        for p in sec.paragraphs:
            move = moves_in.get(id(p))
            if move is not None:
                body = (
                    _esc(p.text)
                    if move.diff.change == ChangeClass.UNCHANGED
                    else _render_word_diff(move.diff)
                )
                out.append(f'<div class="para moved-para">{_move_note(move, False, anchor_base)}{body}</div>')
            else:
                out.append(f'<div class="para added-para">{_esc(p.text)}</div>')
    elif sd.change == ChangeClass.REMOVED:
        for p in sec.paragraphs:
            move = moves_out.get(id(p))
            if move is not None:
                out.append(
                    f'<div class="para moved-para">{_move_note(move, True, anchor_base)}{_esc(p.text)}</div>'
                )
            else:
                out.append(f'<div class="para removed-para">{_esc(p.text)}</div>')
    else:
        unchanged_run: list[str] = []

        def flush_unchanged() -> None:
            if not unchanged_run:
                return
            n = len(unchanged_run)
            out.append(
                f"<details><summary>{n} unchanged paragraph{'s' if n > 1 else ''}</summary>"
                + "".join(f'<div class="para">{t}</div>' for t in unchanged_run)
                + "</details>"
            )
            unchanged_run.clear()

        for pd in sd.paragraph_diffs:
            if pd.change == ChangeClass.UNCHANGED:
                assert pd.new is not None
                unchanged_run.append(_esc(pd.new.text))
                continue
            flush_unchanged()
            if pd.old is None:
                assert pd.new is not None
                move = moves_in.get(id(pd.new))
                if move is not None:
                    body = (
                        _esc(pd.new.text)
                        if move.diff.change == ChangeClass.UNCHANGED
                        else _render_word_diff(move.diff)
                    )
                    out.append(
                        f'<div class="para moved-para">{_move_note(move, False, anchor_base)}{body}</div>'
                    )
                else:
                    out.append(f'<div class="para added-para">{_render_tags(pd)}{_esc(pd.new.text)}</div>')
            elif pd.new is None:
                move = moves_out.get(id(pd.old))
                if move is not None:
                    out.append(
                        f'<div class="para moved-para">{_move_note(move, True, anchor_base)}'
                        f"{_esc(pd.old.text)}</div>"
                    )
                else:
                    out.append(f'<div class="para removed-para">{_render_tags(pd)}{_esc(pd.old.text)}</div>')
            else:
                out.append(f'<div class="para">{_render_word_diff(pd)}{_render_flags(pd)}</div>')
        flush_unchanged()
    out.append("</section>")
    return "\n".join(out)


def render_pair(
    pair: Pair,
    diff: PairDiff,
    out_dir: Path,
    nav_html: str = "<nav></nav>",
    section_hrefs: dict[int, str] | None = None,
) -> Path:
    """section_hrefs: id(Section) → thread-page href, from the chain that owns these diffs (see Chain.section_row_keys)."""
    out_dir.mkdir(parents=True, exist_ok=True)
    counts = diff.counts()
    moves_out = {id(m.diff.old): m for m in diff.moves}
    moves_in = {id(m.diff.new): m for m in diff.moves}
    title = (
        f"{pair.new.subcommittee} ({pair.new.chamber.title()}): "
        f"FY{pair.old.fiscal_year} → FY{pair.new.fiscal_year}"
    )

    summary_rows: list[str] = []
    for sd in diff.sections:
        crumb = " › ".join(sd.display_path[:-1])
        summary_rows.append(
            f'<tr data-change="{sd.change.label.replace(" ", "-")}" '
            f'data-directive="{1 if _has_directive(sd) else 0}" data-flagged="{1 if _review_flags(sd) else 0}">'
            f'<td><a class="secline" href="#{_anchor(sd)}">{_esc((sd.new or sd.old).heading)}</a>'
            f'<br><span class="crumb">{_esc(crumb)}</span></td>'
            f"<td>{_chip(sd.change)}{_flag_badges(sd.flags)}</td>"
            f'<td class="num">{sd.changed_words}</td>'
            "</tr>"
        )

    count_line = ", ".join(
        f"{counts.get(c.label, 0)} {c.label}"
        for c in (
            ChangeClass.ADDED,
            ChangeClass.REMOVED,
            ChangeClass.SUBSTANTIVE,
            ChangeClass.MINOR,
            ChangeClass.NUMBERS_ONLY,
            ChangeClass.UNCHANGED,
        )
    )
    body = "\n".join(
        [
            f"<h1>{_esc(title)}</h1>",
            '<div class="meta">'
            f"{_source_links(pair.old)} → {_source_links(pair.new)}"
            f"<br>{_esc(count_line)}</div>",
            view_tabs(pair, "ranked"),
            '<div class="controls">'
            '<label><input type="checkbox" id="f-unchanged" checked> hide unchanged</label>'
            '<label><input type="checkbox" id="f-numbers"> hide number-only changes</label>'
            '<label><input type="checkbox" id="f-directives"> directives only</label>'
            '<label><input type="checkbox" id="f-flagged"> policy flags only</label>'
            '<span class="fcount" id="fcount"></span>'
            '<div class="crumbs" id="crumbs"></div>'
            "</div>",
            _render_policy_summary(diff),
            "<h2>Changed sections, most significant first</h2>",
            '<div class="overflow"><table><tr><th>Section</th><th>Change</th><th>Words</th></tr>'
            + "".join(summary_rows)
            + "</table></div>",
            "<h2>Details</h2>",
            "\n".join(
                _render_section(
                    sd,
                    pair.old.fiscal_year or 0,
                    pair.new.fiscal_year or 0,
                    moves_out,
                    moves_in,
                    section_hrefs,
                )
                for sd in diff.sections
            ),
        ]
    )
    html_page = page(
        _esc(title), "../style.css", JS + OUTLINE_JS, body, nav_html, outline=render_outline(diff)
    )
    out_path = out_dir / "index.html"
    out_path.write_text(html_page)
    from budget_differ.render.document import render_document

    render_document(pair, diff, out_dir, nav_html, section_hrefs)
    return out_path


def view_tabs(pair: Pair, current: str) -> str:
    """Switch between the significance-ranked page and the full document; both share section anchors, so a fragment carries across."""
    tabs = [
        ("ranked", "index.html", "Ranked changes"),
        ("document", "document.html", f"Full FY{pair.new.fiscal_year} document, annotated"),
    ]
    links = "".join(
        f'<a class="viewtab current" aria-current="page" href="{href}">{label}</a>'
        if key == current
        else f'<a class="viewtab" href="{href}">{label}</a>'
        for key, href, label in tabs
    )
    return f'<div class="viewtabs">{links}</div>'


def _render_policy_summary(diff: PairDiff) -> str:
    """Review-tier flags up front, small edits first: the changes a size-ranked list would bury."""
    small: list[str] = []
    large: list[str] = []
    for sd in diff.sections:
        heading = (sd.new or sd.old).heading
        for pd in sd.paragraph_diffs:
            for f in pd.flags:
                if f.tier < REVIEW:
                    continue
                row = (
                    "<tr>"
                    f'<td><span class="flag">&#9873; {_esc(f.label)}</span><br><span class="crumb">{_esc(f.reason)}</span></td>'
                    f'<td><a class="secline" href="#{_anchor(sd)}">{_esc(heading)}</a></td>'
                    f'<td class="snip">{_snippet(f.before, "del")}</td>'
                    f'<td class="snip">{_snippet(f.after, "ins")}</td>'
                    "</tr>"
                )
                if pd.literal_change in (ChangeClass.MINOR, ChangeClass.NUMBERS_ONLY):
                    small.append(row)
                else:
                    large.append(row)
    if not small and not large:
        return ""
    head = "<tr><th>Signal</th><th>Section</th><th>Prior year</th><th>Proposed</th></tr>"
    parts = [
        f"<h2>Policy signals in small edits ({len(small)})</h2>",
        '<p class="meta">Edits of a few words or a figure that touch negation, discretion, prohibitions, eligibility, conditions, reporting, deadlines, funding floors and ceilings, shares, or counts. '
        "Size-based ranking alone would file these as minor or number-only. "
        "Flags are rule-based prompts for review, not conclusions; verify against the source report.</p>",
    ]
    if small:
        parts.append(f'<div class="overflow"><table class="policy">{head}{"".join(small)}</table></div>')
    if large:
        parts.append(
            f"<details><summary>{len(large)} more signal(s) inside larger rewrites</summary>"
            f'<div class="overflow"><table class="policy">{head}{"".join(large)}</table></div></details>'
        )
    return "\n".join(parts)


_CHAIN_JS = """
function applyChain() {
  const quiet = document.getElementById('c-quiet')?.checked;
  let shown = 0, total = 0;
  document.querySelectorAll('tr[data-active]').forEach(el => {
    const hide = quiet && el.dataset.active === '0';
    el.classList.toggle('hidden', hide);
    total += 1; if (!hide) shown += 1;
  });
  const counter = document.getElementById('fcount');
  if (counter) counter.textContent = shown === total
    ? `showing all ${total} rows`
    : `showing ${shown} of ${total} rows`;
}
document.querySelectorAll('.controls input').forEach(el => el.addEventListener('change', applyChain));
applyChain();
"""

_QUIET = {ChangeClass.UNCHANGED, ChangeClass.NUMBERS_ONLY}


def render_chain(
    chain,
    out_dir: Path,
    nav_html: str = "<nav></nav>",
    thread_hrefs: dict[tuple[str, ...], str] | None = None,
) -> Path:
    """One row per threaded section, one column per year transition, each cell a change chip linking into the pairwise page."""
    out_dir.mkdir(parents=True, exist_ok=True)
    title = (
        f"{chain.subcommittee} ({chain.chamber.title()}): "
        f"FY{chain.fys[0]} → FY{chain.fys[-1]} year over year"
    )
    # Change-intensity heatmap: total changed words per transition, as a bar in each column header.
    totals = {
        b: sum(sd.changed_words for sd in diff.sections)
        for _, b, _, diff in chain.transitions
    }
    peak = max(totals.values()) or 1
    cols = "".join(
        f"<th>FY{a}→FY{b}"
        f'<div class="heatwrap"><div class="heat" style="width:{max(4, round(100 * totals[b] / peak))}%"></div></div>'
        f'<span class="crumb">{totals[b]:,} words changed</span></th>'
        for a, b, _, _ in chain.transitions
    )

    _quiet_labels = {"unchanged", "numbers only"}
    rows: list[str] = []
    for row in chain.rows:
        active = any(c.label not in _quiet_labels for c in row.cells.values())
        cells: list[str] = []
        for a, b, pair, _ in chain.transitions:
            cell = row.cells.get(b)
            if cell is None:
                # account not alive across this transition
                cells.append('<td class="num">&mdash;</td>')
                continue
            href = f"../{cell.slug}/index.html#{_anchor(cell.sd)}"
            css = cell.label.replace(" ", "-")
            chip = f'<span class="chip {css}">{_esc(cell.label)}</span>'
            note = '<br><span class="crumb">renamed</span>' if cell.renamed else ""
            cells.append(f'<td><a class="secline" href="{href}">{chip}</a>{note}</td>')
        label = _esc(row.heading)
        if thread_hrefs and row.key in thread_hrefs:
            label = f'<a class="secline" href="{_esc(thread_hrefs[row.key])}">{label}</a>'
        if row.formerly:
            label += f'<br><span class="crumb">formerly {_esc(row.formerly)}</span>'
        rows.append(
            f'<tr data-active="{1 if active else 0}">'
            f'<td>{label}<br><span class="crumb">{_esc(" › ".join(row.crumb))}</span></td>'
            + "".join(cells)
            + "</tr>"
        )

    n_transitions = len(chain.transitions)
    body = "\n".join(
        [
            f"<h1>{_esc(title)}</h1>",
            '<div class="meta">'
            + " → ".join(
                f"FY{fy} ({_pdf_link(chain.entries[fy], chain.entries[fy].package_id)})"
                for fy in chain.fys
            )
            + " &mdash; each package id links to the report PDF"
            + f"<br>{len(chain.rows)} accounts &amp; provisions across {n_transitions} transitions"
            " (topical sub-heads roll up into their account); each chip links to that"
            " year pair's full diff.</div>",
            '<div class="controls">'
            '<label><input type="checkbox" id="c-quiet" checked> hide quiet rows'
            " (unchanged / number-only throughout)</label>"
            '<span class="fcount" id="fcount"></span>'
            "</div>",
            f'<div class="overflow"><table><tr><th>Section</th>{cols}</tr>'
            + "".join(rows)
            + "</table></div>",
        ]
    )
    out_path = out_dir / "index.html"
    out_path.write_text(page(_esc(title), "../style.css", _CHAIN_JS, body, nav_html))
    return out_path


def render_top_index(
    rows: list[tuple[Pair, dict[str, int], str]],
    out_dir: Path,
    nav_html: str = "<nav></nav>",
) -> Path:
    """rows: (pair, counts, relative href)."""
    table_rows = []
    for pair, counts, href in rows:
        changed = sum(v for k, v in counts.items() if k != "unchanged")
        table_rows.append(
            "<tr>"
            f'<td><a class="secline" href="{_esc(href)}">{_esc(pair.new.subcommittee or "")}'
            f" ({_esc(pair.new.chamber)}) FY{pair.old.fiscal_year} → FY{pair.new.fiscal_year}</a>"
            f'<br><a class="crumb" href="{_esc(href.replace("index.html", "document.html"))}">'
            f"full FY{pair.new.fiscal_year} document, annotated</a></td>"
            f'<td class="num">{changed}</td>'
            f'<td class="num">{counts.get("new", 0)}</td>'
            f'<td class="num">{counts.get("dropped", 0)}</td>'
            "</tr>"
        )
    body = "\n".join(
        [
            "<h1>Appropriations report language diffs</h1>",
            '<div class="meta">Year-over-year changes in committee report language.</div>',
            '<div class="overflow"><table>'
            "<tr><th>Report pair</th><th>Changed sections</th><th>New</th><th>Dropped</th></tr>"
            + "".join(table_rows)
            + "</table></div>",
        ]
    )
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "index.html"
    out_path.write_text(page("budget-differ index", "style.css", "", body, nav_html))
    return out_path
