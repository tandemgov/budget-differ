"""Thread pages: one page per account/provision, followed through time.

The inversion of the pairwise view — the provision is the entity, years are its versions. Top: the latest language with per-paragraph provenance (blame). Below:
the stacked history of word-level diffs, newest first."""

from __future__ import annotations

import hashlib
import re
import shutil
from pathlib import Path

from budget_differ.blame import provenance, transition_maps
from budget_differ.chain import Chain, ChainRow
from budget_differ.models import ChangeClass
from budget_differ.render.assets import CSS
from budget_differ.render.html import _PAGE, _anchor, _esc, _render_section


def thread_filename(row: ChainRow) -> str:
    base = re.sub(r"[^a-z0-9]+", "_", " ".join(row.key).lower()).strip("_")[:90]
    digest = hashlib.md5(" ".join(row.key).encode()).hexdigest()[:6]
    return f"{base}-{digest}.html"


def threads_dir_name(chain: Chain, subcommittee_slug: str) -> str:
    """Range-scoped like the chain page: FY2024–2027 and FY2026–2027 builds of one subcommittee are different histories, and each chain page keeps its own."""
    return f"{chain.chamber}-{subcommittee_slug}-threads-fy{chain.fys[0]}-fy{chain.fys[-1]}"


def render_thread_pages(
    chain: Chain, out_dir: Path, nav_html: str = "<nav></nav>", pair_prefix: str = "../"
) -> dict[tuple[str, ...], str]:
    """Write one page per row; return row.key → filename for chain-page linking.

    The directory is cleaned first: filenames hash the row key, so a hierarchy fix re-keys pages and would otherwise leave stale orphans showing the old tree.
    Callers scope the directory to the chain's year range (threads_dir_name) so a narrower build does not wipe pages a wider chain links to."""
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    maps = transition_maps(chain)
    hrefs: dict[tuple[str, ...], str] = {}
    for row in chain.rows:
        fname = thread_filename(row)
        hrefs[row.key] = fname
        page = _render_thread(chain, row, maps, nav_html, pair_prefix)
        (out_dir / fname).write_text(page)
    return hrefs


def _linked_label(prov, first_fy: int, year_href=lambda fy: f"#h-{fy}") -> str:
    """The provenance badge, each event linked to its year in History or, if the thread has none that year, the pair page."""
    parts: list[str] = []
    if prov.added_fy is not None:
        parts.append(f'<a href="{year_href(prov.added_fy)}">added FY{prov.added_fy}</a>')
    if prov.last_change is not None:
        change, fy = prov.last_change
        if prov.added_fy != fy:
            verb = {
                ChangeClass.NUMBERS_ONLY: "figures updated",
                ChangeClass.MINOR: "tweaked",
            }.get(change, "revised")
            parts.append(f'<a href="{year_href(fy)}">{verb} FY{fy}</a>')
    if prov.moved is not None:
        heading, fy = prov.moved
        parts.append(f'<a href="{year_href(fy)}">moved from {_esc(heading)} (FY{fy})</a>')
    if not parts:
        return f"unchanged since FY{first_fy}"
    return "; ".join(parts)


def _render_thread(
    chain: Chain, row: ChainRow, maps, nav_html: str, pair_prefix: str
) -> str:
    fys_present = sorted({fy for t in row.members for fy in t.sections})
    latest_fy = max(fys_present)
    first_fy = min(fys_present)
    dropped_after = latest_fy != chain.fys[-1]

    # Timeline strip: one chip per transition linking into the pairwise page, with a change-intensity bar (this thread's changed words that year) underneath.
    words_by_fy: dict[int, int] = {}
    for t in row.members:
        for fy, cell in t.cells.items():
            words_by_fy[fy] = words_by_fy.get(fy, 0) + cell.sd.changed_words
    peak = max(words_by_fy.values(), default=0) or 1
    strip: list[str] = []
    for a, b, pair, _ in chain.transitions:
        cell = row.cells.get(b)
        if cell is None:
            strip.append(f'<span class="tl"><span class="crumb">FY{b}</span> &mdash;</span>')
            continue
        href = f"{pair_prefix}{cell.slug}/index.html#{_anchor(cell.sd)}"
        css = cell.label.replace(" ", "-")
        words = words_by_fy.get(b, 0)
        bar = (
            f'<div class="heatwrap" title="{words:,} words changed">'
            f'<div class="heat" style="width:{max(4, round(100 * words / peak))}%"></div></div>'
        )
        strip.append(
            f'<span class="tl"><span class="crumb">FY{b}</span> '
            f'<a class="secline" href="#h-{b}"><span class="chip {css}">{_esc(cell.label)}</span></a>'
            f"{bar}</span>"
        )

    # Blame: the latest language, each paragraph annotated with its provenance.
    blame: list[str] = [f"<h2>Language as of FY{latest_fy}</h2>"]
    if dropped_after:
        blame.append(
            f'<div class="tables-note">&#9888; last appeared in FY{latest_fy}; '
            "dropped in the following report</div>"
        )
    members = sorted(row.members, key=lambda t: t.latest_section().order)
    history_fys = {b for _, b, _, _ in chain.transitions if any(b in t.cells for t in members)}
    pair_slug = {b: pair.slug() for _, b, pair, _ in chain.transitions}

    def year_href(fy: int) -> str:
        if fy in history_fys or fy not in pair_slug:
            return f"#h-{fy}"
        return f"{pair_prefix}{pair_slug[fy]}/index.html"

    for t in members:
        if latest_fy not in t.sections:
            continue
        sec = t.sections[latest_fy]
        if sec.path[-1] != row.key[-1] and not sec.path[-1].startswith("SEC "):
            blame.append(f'<h4 class="subhead">{_esc(sec.heading)}</h4>')
        for p in sec.paragraphs:
            prov = provenance(maps, chain.fys, p, start_fy=latest_fy)
            label = _linked_label(prov, first_fy, year_href)
            hot = prov.is_hot(chain.fys[-1]) and not dropped_after
            cls = "prov hot" if hot else "prov"
            blame.append(
                f'<div class="para blamed"><span class="{cls}">{label}</span>'
                f"{_esc(p.text)}</div>"
            )

    # History: stacked per-transition diffs, newest first; each year anchored so the blame badges above can deep-link to the diff that made the change, and each heading links out to the same section on the pairwise page for context.
    history: list[str] = ["<h2>History</h2>"]
    for a, b, pair, _ in reversed(chain.transitions):
        cells = [(t, t.cells[b]) for t in members if b in t.cells]
        if not cells:
            continue
        anchor_cell = row.cells.get(b) or cells[0][1]
        ctx = f"{pair_prefix}{anchor_cell.slug}/index.html#{_anchor(anchor_cell.sd)}"
        history.append(
            f'<h3 class="hist-fy" id="h-{b}">FY{a} &rarr; FY{b} '
            f'<a class="ctx" href="{ctx}">view in full report diff &rarr;</a></h3>'
        )
        for t, cell in cells:
            # Successor/move links inside the section reference anchors that live on the pairwise page, not here — give them that page as base.
            base = f"{pair_prefix}{cell.slug}/index.html"
            history.append(_render_section(cell.sd, a, b, anchor_base=base))

    # Numbering/name history: general provisions renumber and accounts rename — say so explicitly instead of letting mixed numbers look like mis-threading.
    label_by_fy = {
        fy: t.sections[fy].path[-1] for t in row.members for fy in t.sections
    }
    runs: list[tuple[str, int, int]] = []
    for fy in sorted(label_by_fy):
        label = label_by_fy[fy]
        if runs and runs[-1][0] == label:
            runs[-1] = (label, runs[-1][1], fy)
        else:
            runs.append((label, fy, fy))
    numbering = ""
    if len(runs) > 1:
        parts = [
            (f"{lab.title()} (FY{a})" if a == b else f"{lab.title()} (FY{a}–FY{b})")
            for lab, a, b in runs
        ]
        numbering = (
            '<div class="related">&#8635; numbering/name history: '
            + " &rarr; ".join(_esc(p) for p in parts)
            + "</div>"
        )

    crumb = " › ".join(row.crumb)
    title = f"{row.heading} — {chain.subcommittee} ({chain.chamber.title()})"
    body = "\n".join(
        [
            f"<h1>{_esc(row.heading)}</h1>",
            f'<div class="meta">{_esc(crumb)}'
            + (f"<br>formerly {_esc(row.formerly)}" if row.formerly else "")
            + f"<br>{_esc(chain.subcommittee)} ({_esc(chain.chamber)}), "
            f"FY{first_fy}&ndash;FY{latest_fy}</div>",
            f'<div class="timeline">{" ".join(strip)}</div>',
            numbering,
            "\n".join(blame),
            "\n".join(history),
        ]
    )
    return _PAGE.substitute(title=_esc(title), cssref="../style.css", js="", body=body, nav=nav_html)
