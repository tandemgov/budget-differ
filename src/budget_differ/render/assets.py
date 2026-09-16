"""Inline CSS and JS for the self-contained diff pages."""

CSS = """
:root {
  --bg: #ffffff; --fg: #1a1a1a; --muted: #6b7280; --border: #e5e7eb;
  --ins-bg: #dcfce7; --ins-fg: #14532d; --del-bg: #fee2e2; --del-fg: #7f1d1d;
  --chip-unchanged: #e5e7eb; --chip-numbers: #dbeafe; --chip-minor: #fef9c3;
  --chip-substantive: #fed7aa; --chip-new: #bbf7d0; --chip-dropped: #fecaca;
  --flag-bg: #ede9fe; --flag-fg: #4c1d95;
  --dot-numbers: #3b82f6; --dot-minor: #ca8a04; --dot-substantive: #ea580c;
  --dot-new: #16a34a; --dot-dropped: #dc2626;
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
.layout.wide { max-width: 100rem; }
main { flex: 1; min-width: 0; max-width: 60rem; }
.layout.wide main { max-width: 82rem; }
.leftcol {
  width: 13rem; flex-shrink: 0; position: sticky; top: 1rem;
  max-height: calc(100vh - 2rem); overflow-y: auto; overscroll-behavior: contain;
  font-family: -apple-system, 'Segoe UI', Helvetica, Arial, sans-serif; font-size: .85rem;
  border-right: 1px solid var(--border); padding-right: 1rem;
}
.leftcol.has-outline { width: 16rem; }
.sidenav a { display: block; color: inherit; text-decoration: none; padding: .18rem .4rem; border-radius: 4px; }
.sidenav a:hover { background: var(--chip-unchanged); }
.sidenav a.current { background: var(--chip-numbers); font-weight: 600; }
.sidenav .navhead {
  font-weight: 700; text-transform: uppercase; letter-spacing: .05em; font-size: .7rem;
  color: var(--muted); margin: .9rem 0 .25rem;
}
.sidenav .navhome { font-weight: 600; }
.navtoggle-box, .navburger { display: none; }
/* With an outline in the column, committee links fold behind their toggle on every screen size. */
.leftcol.has-outline .navburger { display: block; cursor: pointer; font-weight: 600; padding: .18rem .4rem; user-select: none; }
.leftcol.has-outline .navlinks { display: none; }
.leftcol.has-outline .navtoggle-box:checked ~ .navlinks { display: block; }
/* Anchor targets land below the sticky filter bar and its breadcrumb row, not under it. */
.section, .hist-fy, tr[id], .docsec, .drow { scroll-margin-top: 7.5rem; }
.outline { margin-top: .6rem; border-top: 1px solid var(--border); padding-top: .4rem; }
.oltoggle-box { display: none; }
.olhead {
  display: block; font-weight: 700; text-transform: uppercase; letter-spacing: .05em; font-size: .7rem;
  color: var(--muted); margin: .5rem 0 .2rem;
}
.olactions { display: flex; gap: .75rem; margin: 0 0 .35rem; }
.olactions button {
  font: inherit; font-size: .72rem; color: var(--muted); background: none; border: none; padding: 0;
  cursor: pointer; text-decoration: underline dotted;
}
ul.ol { list-style: none; margin: 0; padding: 0 0 0 .95rem; }
ul.ol ul.ol { display: none; padding-left: .85rem; }
li.oli.open > ul.ol { display: block; }
li.oli { position: relative; }
.olcaret {
  position: absolute; left: -.95rem; top: .2rem; width: .9rem; height: 1rem; padding: 0;
  border: none; background: none; color: var(--muted); cursor: pointer; font-size: .7rem; line-height: 1rem;
}
.olcaret::before { content: '▸'; }
li.oli.open > .olcaret::before { content: '▾'; }
a.oll {
  display: block; position: relative; padding: .12rem .35rem .12rem .95rem; border-radius: 4px;
  color: inherit; text-decoration: none; font-size: .8rem; line-height: 1.35;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
a.oll:hover { background: var(--chip-unchanged); }
a.oll::before {
  content: ''; position: absolute; left: .35rem; top: .62em; width: .38rem; height: .38rem; border-radius: 50%;
}
li[data-oc="numbers-only"] > a.oll::before { background: var(--dot-numbers); }
li[data-oc="minor"] > a.oll::before { background: var(--dot-minor); }
li[data-oc="substantive"] > a.oll::before { background: var(--dot-substantive); }
li[data-oc="new"] > a.oll::before { background: var(--dot-new); }
li[data-oc="dropped"] > a.oll::before { background: var(--dot-dropped); }
li[data-oc="unchanged"] > a.oll { color: var(--muted); }
li[data-oc="dropped"] > a.oll { color: var(--muted); text-decoration: line-through; }
li.oli.on-path > a.oll { font-weight: 600; }
a.oll.active { background: var(--chip-numbers); color: var(--fg); }
a.oll.filtered { opacity: .45; }
.viewtabs {
  display: flex; flex-wrap: wrap; gap: .25rem; border-bottom: 1px solid var(--border); margin: 0 0 .25rem;
  font-family: -apple-system, 'Segoe UI', Helvetica, Arial, sans-serif; font-size: .85rem;
}
.viewtab {
  padding: .4rem .85rem; color: var(--muted); text-decoration: none; margin-bottom: -1px;
  border: 1px solid transparent; border-bottom: none; border-radius: 6px 6px 0 0;
}
.viewtab:hover { color: var(--fg); }
.viewtab.current { color: var(--fg); background: var(--bg); border-color: var(--border); font-weight: 600; }
.controls .crumbs {
  flex-basis: 100%; min-height: 1.2em; margin-top: -.5rem; font-size: .78rem; color: var(--muted);
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.crumbs a { color: inherit; text-decoration: none; }
.crumbs a:hover { text-decoration: underline; }
.crumbs a:last-child { color: var(--fg); font-weight: 600; }
.crumbs .sep { margin: 0 .35rem; }
.controls button {
  font: inherit; font-size: .8rem; padding: .1rem .55rem; border: 1px solid var(--border); border-radius: 4px;
  background: var(--bg); color: var(--fg); cursor: pointer;
}
.controls button:hover { background: var(--chip-unchanged); }
.controls .stepper { display: inline-flex; gap: .35rem; }
.doc .drow { display: grid; grid-template-columns: minmax(0, 1fr) 18rem; column-gap: 1.5rem; }
.doc .dtext { min-width: 0; }
.doc .dtext .para { margin: 0; padding: .3rem 0; }
.doc .dtext .para.added-para, .doc .dtext .para.removed-para, .doc .dtext .para.moved-para { margin: .3rem 0; padding: .5rem .75rem; }
.dnote {
  font-family: -apple-system, 'Segoe UI', sans-serif; font-size: .78rem; color: var(--muted);
  border-left: 1px solid var(--border); padding: .35rem 0 .35rem .75rem;
}
.dnote a { color: inherit; }
.dnote .chip { margin-right: .25rem; }
.dnote .flag { margin: .1rem .25rem .1rem 0; }
.dnote .related { font-size: .78rem; margin: .3rem 0; }
.dnote .movenote { margin: 0; }
.dnote ul.flags { font-size: .78rem; }
.dnote .tags { margin: .25rem 0 0; }
.dlinks { margin-top: .2rem; }
.dh { font-family: -apple-system, 'Segoe UI', Helvetica, Arial, sans-serif; font-weight: 700; margin: 1.6rem 0 .2rem; }
.dh.d0 { font-size: 1.3rem; }
.dh.d1 { font-size: 1.12rem; }
.dh.d2 { font-size: 1rem; }
.dh.d3 { font-size: .95rem; font-weight: 600; }
.dh.d4 { font-size: .9rem; font-weight: 600; font-style: italic; }
.docsec.dropped .dh { color: var(--del-fg); text-decoration: line-through; }
.docsec.added .dh { color: var(--ins-fg); }
.doc .moved-away { text-decoration: line-through; }
.doc.no-del del, .doc.no-del .del-row, .doc.no-del .docsec.dropped { display: none; }
.doc.no-ins ins { background: none; color: inherit; padding: 0; }
.doc.no-ins .dtext .para.added-para, .doc.no-ins .dtext .para.moved-para {
  background: none; border-left: none; color: inherit; margin: 0; padding: .3rem 0;
}
.doc.no-ins .docsec.added .dh { color: inherit; }
.doc.no-notes .drow { grid-template-columns: minmax(0, 1fr); }
.doc.no-notes .dnote { display: none; }
@keyframes flash { from { background: color-mix(in srgb, var(--chip-minor) 70%, transparent); } to { background: transparent; } }
.drow.flash { animation: flash 1.2s ease-out; }
.doc .drow.dhead .dnote { padding-top: 1.75rem; }
/* Wide tables: keep the row label pinned while columns scroll. */
.overflow th:first-child, .overflow td:first-child {
  position: sticky; left: 0; background: var(--bg); z-index: 1;
}
@media (max-width: 900px) {
  body { padding: 1rem .75rem; }
  .layout { flex-direction: column; gap: 1rem; }
  .leftcol, .leftcol.has-outline { position: static; width: 100%; max-height: none; border-right: none;
             border-bottom: 1px solid var(--border); padding: 0 0 .75rem; }
  .olhead { cursor: pointer; font-size: .85rem; text-transform: none; letter-spacing: 0; color: var(--fg); padding: .5rem .4rem; margin: 0; }
  .olhead::before { content: '☰  '; }
  .oltoggle-box:not(:checked) ~ .olbody { display: none; }
  a.oll { padding-top: .35rem; padding-bottom: .35rem; white-space: normal; }
  .doc .drow { grid-template-columns: minmax(0, 1fr); }
  .dnote { border-left: none; padding: 0 0 .5rem; }
  .dnote:empty { display: none; }
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
  if (window.budgetOutlineSync) window.budgetOutlineSync();
}
document.querySelectorAll('.controls input').forEach(el => el.addEventListener('change', applyFilters));
applyFilters();
"""

# Full-document page: display toggles, and a stepper that walks changed paragraphs (buttons, or j/k).
DOC_JS = """
(function () {
  const doc = document.getElementById('doc');
  if (!doc) return;
  const toggles = [['d-del', 'no-del'], ['d-ins', 'no-ins'], ['d-notes', 'no-notes']];
  function applyToggles() {
    for (const [id, cls] of toggles) {
      const el = document.getElementById(id);
      if (el) doc.classList.toggle(cls, !el.checked);
    }
    const n = [...doc.querySelectorAll('.drow.changed')].filter(el => el.offsetParent !== null).length;
    const counter = document.getElementById('fcount');
    if (counter) counter.textContent = `${n} changed paragraph${n === 1 ? '' : 's'}`;
    if (window.budgetOutlineSync) window.budgetOutlineSync();
  }
  toggles.forEach(([id]) => document.getElementById(id)?.addEventListener('change', applyToggles));
  function step(dir) {
    const bar = document.querySelector('.controls');
    const line = (bar ? bar.offsetHeight : 0) + 6;
    const stops = [...doc.querySelectorAll('.drow.changed')].filter(el => el.offsetParent !== null);
    let target = null;
    if (dir > 0) {
      target = stops.find(el => el.getBoundingClientRect().top > line + 2);
    } else {
      for (const el of stops) {
        if (el.getBoundingClientRect().top < line - 2) target = el; else break;
      }
    }
    if (!target) return;
    window.scrollBy(0, target.getBoundingClientRect().top - line);
    target.classList.remove('flash');
    void target.offsetWidth;
    target.classList.add('flash');
  }
  document.getElementById('nextchg')?.addEventListener('click', () => step(1));
  document.getElementById('prevchg')?.addEventListener('click', () => step(-1));
  document.addEventListener('keydown', e => {
    if (e.metaKey || e.ctrlKey || e.altKey || e.target.closest('input, textarea, select')) return;
    if (e.key === 'j') step(1);
    if (e.key === 'k') step(-1);
  });
  applyToggles();
})();
"""

# Outline: scroll-spy highlight, breadcrumbs for the section in view, expand/collapse, and unhiding a filtered-out section when it is jumped to.
OUTLINE_JS = """
(function () {
  const ol = document.querySelector('.outline');
  if (!ol) return;
  const column = ol.closest('.leftcol');
  const crumbs = document.getElementById('crumbs');
  const spies = [...document.querySelectorAll('[data-spy]')];
  const links = new Map();
  ol.querySelectorAll('a.oll').forEach(a => {
    const id = a.getAttribute('href').slice(1);
    if (!links.has(id) || a.classList.contains('own')) links.set(id, a);
  });
  function reveal(id) {
    const el = id && document.getElementById(id);
    if (el && el.classList.contains('hidden')) {
      el.classList.remove('hidden');
      return true;
    }
    return false;
  }
  ol.addEventListener('click', e => {
    const caret = e.target.closest('.olcaret');
    if (caret) { caret.parentElement.classList.toggle('open'); return; }
    const bulk = e.target.closest('[data-ol]');
    if (bulk) {
      ol.querySelectorAll('li.has-kids').forEach(li => li.classList.toggle('open', bulk.dataset.ol === 'expand'));
      return;
    }
    const a = e.target.closest('a.oll');
    if (a) {
      reveal(a.getAttribute('href').slice(1));
      const box = document.getElementById('oltoggle');
      if (box) box.checked = false;
    }
  });
  function onHash() {
    const id = decodeURIComponent(location.hash.slice(1));
    if (reveal(id)) document.getElementById(id).scrollIntoView();
  }
  window.addEventListener('hashchange', onHash);
  let current;
  function activate(id) {
    if (id === current) return;
    current = id;
    ol.querySelectorAll('a.oll.active').forEach(a => a.classList.remove('active'));
    ol.querySelectorAll('li.on-path').forEach(li => li.classList.remove('on-path'));
    const link = id ? links.get(id) : null;
    const trail = [];
    if (link) {
      link.classList.add('active');
      for (let li = link.parentElement; li; li = li.parentElement.closest('li.oli')) {
        li.classList.add('on-path');
        if (li !== link.parentElement) li.classList.add('open');
        trail.unshift(li.querySelector(':scope > a.oll'));
      }
      if (column && column.scrollHeight > column.clientHeight) {
        const r = link.getBoundingClientRect(), box = column.getBoundingClientRect();
        if (r.top < box.top + 40 || r.bottom > box.bottom - 20) column.scrollTop += r.top - box.top - box.height / 3;
      }
    }
    if (!crumbs) return;
    crumbs.replaceChildren();
    trail.forEach((l, i) => {
      if (i) {
        const sep = document.createElement('span');
        sep.className = 'sep';
        sep.textContent = '\u203A';
        crumbs.append(sep);
      }
      const a = document.createElement('a');
      a.href = l.getAttribute('href');
      a.textContent = l.textContent;
      crumbs.append(a);
    });
  }
  function spy() {
    const bar = document.querySelector('.controls');
    // Generous enough that a section landed on by an anchor jump (scroll-margin-top) already counts as in view.
    const line = (bar ? bar.offsetHeight : 0) + 48;
    let id = null;
    for (const s of spies) {
      if (s.offsetParent === null) continue;
      if (s.getBoundingClientRect().top <= line) id = s.id; else break;
    }
    activate(id);
  }
  let queued = false;
  function schedule() {
    if (queued) return;
    queued = true;
    requestAnimationFrame(() => { queued = false; spy(); });
  }
  window.addEventListener('scroll', schedule, { passive: true });
  window.addEventListener('resize', schedule);
  window.budgetOutlineSync = function () {
    links.forEach((a, id) => {
      const el = document.getElementById(id);
      a.classList.toggle('filtered', !el || el.offsetParent === null);
    });
    current = undefined;
    schedule();
  };
  onHash();
  window.budgetOutlineSync();
})();
"""
