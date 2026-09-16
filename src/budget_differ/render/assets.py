"""Inline CSS and JS for the self-contained diff pages."""

CSS = """
:root {
  --bg: #ffffff; --fg: #1a1a1a; --muted: #6b7280; --border: #e5e7eb;
  --ins-bg: #dcfce7; --ins-fg: #14532d; --del-bg: #fee2e2; --del-fg: #7f1d1d;
  --chip-unchanged: #e5e7eb; --chip-numbers: #dbeafe; --chip-minor: #fef9c3;
  --chip-substantive: #fed7aa; --chip-new: #bbf7d0; --chip-dropped: #fecaca;
  --flag-bg: #ede9fe; --flag-fg: #4c1d95;
}
@media (prefers-color-scheme: dark) {
  :root {
    --bg: #111418; --fg: #e5e7eb; --muted: #9ca3af; --border: #2d333b;
    --ins-bg: #113a24; --ins-fg: #86efac; --del-bg: #431418; --del-fg: #fca5a5;
    --chip-unchanged: #2d333b; --chip-numbers: #1e3a5f; --chip-minor: #4d3f10;
    --chip-substantive: #5a3211; --chip-new: #14532d; --chip-dropped: #5f1a1a;
    --flag-bg: #2e1f5e; --flag-fg: #ddd6fe;
  }
}
* { box-sizing: border-box; }
body {
  margin: 0; padding: 2rem 1rem; background: var(--bg); color: var(--fg);
  font: 16px/1.55 Georgia, 'Times New Roman', serif;
}
.layout { display: flex; gap: 2.5rem; max-width: 78rem; margin: 0 auto; align-items: flex-start; }
main { flex: 1; min-width: 0; max-width: 60rem; }
.sidenav {
  width: 13rem; flex-shrink: 0; position: sticky; top: 1rem;
  max-height: calc(100vh - 2rem); overflow-y: auto;
  font-family: -apple-system, 'Segoe UI', Helvetica, Arial, sans-serif; font-size: .85rem;
  border-right: 1px solid var(--border); padding-right: 1rem;
}
.sidenav a { display: block; color: inherit; text-decoration: none; padding: .18rem .4rem; border-radius: 4px; }
.sidenav a:hover { background: var(--chip-unchanged); }
.sidenav a.current { background: var(--chip-numbers); font-weight: 600; }
.sidenav .navhead {
  font-weight: 700; text-transform: uppercase; letter-spacing: .05em; font-size: .7rem;
  color: var(--muted); margin: .9rem 0 .25rem;
}
.sidenav .navhome { font-weight: 600; }
.navtoggle-box, .navburger { display: none; }
/* Anchor targets land below the sticky filter bar, not under it. */
.section, .hist-fy, tr[id] { scroll-margin-top: 5.5rem; }
/* Wide tables: keep the row label pinned while columns scroll. */
.overflow th:first-child, .overflow td:first-child {
  position: sticky; left: 0; background: var(--bg); z-index: 1;
}
@media (max-width: 900px) {
  body { padding: 1rem .75rem; }
  .layout { flex-direction: column; gap: 1rem; }
  .sidenav { position: static; width: auto; max-height: none; border-right: none;
             border-bottom: 1px solid var(--border); padding: 0 0 .75rem; }
  .navburger { display: block; cursor: pointer; font-weight: 600; padding: .5rem .4rem;
               user-select: none; }
  .sidenav .navlinks { display: none; }
  .navtoggle-box:checked ~ .navlinks { display: block; }
  .sidenav a { padding: .5rem .4rem; }
  .chip { font-size: .72rem; padding: .22rem .55rem; }
  .controls { gap: .75rem; font-size: .8rem; }
  .prov a, a.ctx, .movenote a { padding: .15rem 0; display: inline-block; }
}
h1, h2, h3, .meta, .chip, table, .controls { font-family: -apple-system, 'Segoe UI', Helvetica, Arial, sans-serif; }
h1 { font-size: 1.4rem; margin: 0 0 .25rem; }
.meta { color: var(--muted); font-size: .85rem; margin-bottom: 1.5rem; }
.meta a { color: inherit; }
ins { background: var(--ins-bg); color: var(--ins-fg); text-decoration: none; padding: 0 .1em; }
del { background: var(--del-bg); color: var(--del-fg); text-decoration: line-through; padding: 0 .1em; }
.chip {
  display: inline-block; font-size: .7rem; font-weight: 600; text-transform: uppercase;
  letter-spacing: .03em; padding: .1rem .45rem; border-radius: 999px; vertical-align: middle;
}
.chip.unchanged { background: var(--chip-unchanged); }
.chip.numbers-only { background: var(--chip-numbers); }
.chip.minor { background: var(--chip-minor); }
.chip.substantive { background: var(--chip-substantive); }
.chip.new { background: var(--chip-new); }
.chip.dropped { background: var(--chip-dropped); }
.chip.reorganized { background: var(--chip-numbers); }
.chip.returned { background: var(--chip-new); outline: 1px dashed var(--muted); }
table { border-collapse: collapse; width: 100%; font-size: .85rem; }
th, td { text-align: left; padding: .4rem .6rem; border-bottom: 1px solid var(--border); vertical-align: top; }
th { color: var(--muted); font-weight: 600; }
td.num { text-align: right; font-variant-numeric: tabular-nums; }
.crumb { color: var(--muted); }
.section { border-top: 2px solid var(--border); padding: 1.25rem 0; }
.section h3 { margin: 0 0 .2rem; font-size: 1.05rem; }
.section .pathline { color: var(--muted); font-size: .8rem; margin-bottom: .75rem; font-family: -apple-system, 'Segoe UI', sans-serif; }
.para { margin: .6rem 0; }
.para.added-para { background: var(--ins-bg); padding: .5rem .75rem; border-radius: 4px; }
.para.removed-para { background: var(--del-bg); padding: .5rem .75rem; border-radius: 4px; text-decoration: line-through; }
.para.moved-para { border-left: 3px solid var(--muted); padding: .5rem .75rem; border-radius: 4px; color: var(--muted); }
.movenote { font-family: -apple-system, 'Segoe UI', sans-serif; font-size: .8rem; margin-bottom: .3rem; }
.movenote a { color: inherit; }
.timeline { display: flex; flex-wrap: wrap; gap: .75rem 1.25rem; margin: 1rem 0 1.5rem;
            font-family: -apple-system, 'Segoe UI', sans-serif; font-size: .8rem; }
.timeline .tl { white-space: nowrap; }
.heatwrap { height: 5px; background: var(--chip-unchanged); border-radius: 3px;
            margin-top: .25rem; min-width: 3.5rem; overflow: hidden; }
.heat { height: 100%; background: var(--chip-substantive); border-radius: 3px; }
a.ctx { font-family: -apple-system, 'Segoe UI', sans-serif; font-size: .75rem; font-weight: 400;
        color: var(--muted); text-decoration: none; margin-left: .5rem; }
a.ctx:hover { text-decoration: underline; }
.para.blamed { position: relative; }
.prov { display: block; font-family: -apple-system, 'Segoe UI', sans-serif; font-size: .7rem;
        color: var(--muted); text-transform: uppercase; letter-spacing: .04em; margin-bottom: .15rem; }
.prov.hot { color: var(--ins-fg); font-weight: 700; }
.prov a { color: inherit; text-decoration: underline dotted; }
.prov a:hover { text-decoration: underline; }
h4.subhead { font-size: .9rem; margin: 1.1rem 0 .3rem; color: var(--muted);
             text-transform: uppercase; letter-spacing: .04em; }
h3.hist-fy { border-top: 2px solid var(--border); padding-top: 1rem; margin-top: 1.5rem; }
.tables-note { color: var(--muted); font-size: .8rem; font-style: italic; }
.related {
  font-family: -apple-system, 'Segoe UI', sans-serif; font-size: .85rem;
  margin: .3rem 0 .6rem; padding: .35rem .6rem; border-left: 3px solid var(--chip-numbers);
  background: color-mix(in srgb, var(--chip-numbers) 30%, transparent);
}
.related a { color: inherit; }
.controls {
  position: sticky; top: 0; background: var(--bg); padding: .75rem 0; margin-bottom: 1rem;
  border-bottom: 1px solid var(--border); font-size: .85rem; display: flex; gap: 1.25rem; flex-wrap: wrap;
}
.controls label { cursor: pointer; user-select: none; }
.controls .fcount { margin-left: auto; color: var(--muted); font-variant-numeric: tabular-nums; }
details summary { cursor: pointer; color: var(--muted); font-size: .85rem; font-family: -apple-system, 'Segoe UI', sans-serif; }
.hidden { display: none; }
a.secline { color: inherit; }
.overflow { overflow-x: auto; }
.flag {
  display: inline-block; font-family: -apple-system, 'Segoe UI', sans-serif; font-size: .7rem; font-weight: 600;
  padding: .1rem .45rem; margin-left: .3rem; border-radius: 4px; vertical-align: middle;
  background: var(--flag-bg); color: var(--flag-fg); white-space: nowrap;
}
.flag.note { background: var(--chip-unchanged); color: var(--muted); font-weight: 400; }
ul.flags { list-style: none; margin: .35rem 0 0; padding: 0; font-family: -apple-system, 'Segoe UI', sans-serif; font-size: .8rem; }
ul.flags li { margin: .15rem 0; }
ul.flags .flag { margin-left: 0; margin-right: .35rem; }
ul.flags li.note { color: var(--muted); }
.tags { font-family: -apple-system, 'Segoe UI', sans-serif; font-size: .75rem; color: var(--muted); margin-bottom: .25rem; }
.para.removed-para .tags { text-decoration: none; display: block; }
table.policy td.snip { font-family: Georgia, serif; font-size: .85rem; min-width: 14rem; }
table.policy .flag { margin-left: 0; }
.gap { color: var(--muted); }
"""

JS = """
function applyFilters() {
  const hideUnchanged = document.getElementById('f-unchanged')?.checked;
  const hideNumbers = document.getElementById('f-numbers')?.checked;
  const directivesOnly = document.getElementById('f-directives')?.checked;
  const flaggedOnly = document.getElementById('f-flagged')?.checked;
  let shown = 0, total = 0;
  document.querySelectorAll('[data-change]').forEach(el => {
    const c = el.dataset.change;
    const isDirective = el.dataset.directive === '1';
    let hide = false;
    if (hideUnchanged && c === 'unchanged') hide = true;
    if (hideNumbers && c === 'numbers-only') hide = true;
    if (directivesOnly && !isDirective) hide = true;
    if (flaggedOnly && el.dataset.flagged !== '1') hide = true;
    el.classList.toggle('hidden', hide);
    if (el.tagName === 'SECTION') { total += 1; if (!hide) shown += 1; }
  });
  const counter = document.getElementById('fcount');
  if (counter) counter.textContent = shown === total
    ? `showing all ${total} sections`
    : `showing ${shown} of ${total} sections`;
}
document.querySelectorAll('.controls input').forEach(el => el.addEventListener('change', applyFilters));
applyFilters();
"""
