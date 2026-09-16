"""Entry point: build the static diff site from the approps corpus.

Usage:
    uv run budget-differ                          # every valid adjacent-FY pair
    uv run budget-differ house                    # one chamber
    uv run budget-differ house energy-water       # one subcommittee
    uv run budget-differ house energy-water 2027  # one target fiscal year
    uv run budget-differ house energy-water 2024-2027   # year-over-year chain view
    uv run budget-differ --dump-sections CRPT-119hrpt667   # debug segmentation JSON
    uv run budget-differ demo [OUT_DIR]           # the acceptance demonstration (default: demo/)
"""

from __future__ import annotations

import json
import os
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import asdict
from pathlib import Path

from budget_differ.compare import compare_documents, load_document
from budget_differ.config import approps_repo
from budget_differ.corpus import available_reports, discover_pairs, load_catalog, raw_path
from budget_differ.render import render_pair, render_top_index


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    repo = approps_repo()

    if args and args[0] == "demo":
        out = Path(args[1]) if len(args) > 1 else Path("demo")
        return build_demo(repo, out)

    if args and args[0] == "--dump-sections":
        if len(args) < 2:
            print("usage: budget-differ --dump-sections PACKAGE_ID", file=sys.stderr)
            return 2
        return _dump_sections(repo, args[1])

    chamber = subcommittee = None
    fiscal_year = None
    if args:
        chamber = args[0].lower()
        if chamber not in ("house", "senate"):
            print(f"unknown chamber {chamber!r} (expected house or senate)", file=sys.stderr)
            return 2
    if len(args) > 1:
        subcommittee = args[1]
    if len(args) > 2:
        if "-" in args[2]:
            if not (chamber and subcommittee):
                print("chain view needs chamber and subcommittee, e.g. "
                      "budget-differ house legislative-branch 2024-2027", file=sys.stderr)
                return 2
            lo, hi = args[2].split("-", 1)
            return _build_chain(repo, chamber, subcommittee, int(lo), int(hi))
        fiscal_year = int(args[2])

    reports = available_reports(repo)
    pairs = discover_pairs(reports, chamber, subcommittee, fiscal_year)
    if not pairs:
        print("no comparable pairs found for that filter", file=sys.stderr)
        return 1

    from budget_differ.chain import build_chain
    from budget_differ.render import render_chain
    from budget_differ.render.html import NavItem, render_nav

    out_root = Path("out")

    # Enumerate groups and their chain (longitudinal) page dirs up front, from the catalog alone, so every page can carry the full sidebar.
    groups: dict[tuple[str, str], list[int]] = {}
    labels: dict[tuple[str, str], str] = {}
    for p in pairs:
        key = (p.new.chamber, p.new.slug())
        fys = groups.setdefault(key, [])
        for fy in (p.old.fiscal_year, p.new.fiscal_year):
            if fy and fy not in fys:
                fys.append(fy)
        labels[key] = p.new.subcommittee or p.new.slug()
    chain_dir = {
        key: f"{key[0]}-{key[1]}-chain-fy{min(fys)}-fy{max(fys)}"
        for key, fys in groups.items()
    }
    nav_items = [
        NavItem(chamber=key[0], label=labels[key], dir=chain_dir[key])
        for key in sorted(groups, key=lambda k: (k[0], labels[k].lower()))
    ]

    # Groups are independent — fan out across cores. Output is deterministic (no timestamps), so unchanged pages stay byte-identical and Netlify's content-addressed deploy uploads only what actually changed.
    jobs = [
        (
            str(repo),
            key[0],
            key[1],
            min(fys),
            max(fys),
            chain_dir[key],
            render_nav(nav_items, chain_dir[key], "../"),
            str(out_root),
        )
        for key, fys in groups.items()
    ]
    index_rows = []
    timelines = 0
    workers = min(len(jobs), os.cpu_count() or 4)
    with ProcessPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(_build_group, job): job for job in jobs}
        for fut in as_completed(futures):
            name, rows, skipped = fut.result()
            if skipped:
                print(f"{name}: skipped — {skipped}", flush=True)
                continue
            print(f"{name}: {len(rows)} pair(s) + timeline", flush=True)
            index_rows.extend(rows)
            timelines += 1
    index_rows.sort(key=lambda r: (r[0].new.chamber, r[0].new.slug(), r[0].new.fiscal_year or 0))
    from budget_differ.render.assets import CSS

    (out_root / "style.css").write_text(CSS)
    render_top_index(index_rows, out_root, render_nav(nav_items, ".", ""))
    print(f"built {len(index_rows)} pair(s) + {timelines} timeline(s) → {out_root / 'index.html'}")
    return 0


def _build_group(job: tuple) -> tuple[str, list, str | None]:
    """Worker: build one chamber/subcommittee group — thread pages (one per account/provision, with blame), all pair pages, and its timeline."""
    from budget_differ.chain import build_chain
    from budget_differ.render import render_chain, render_pair
    from budget_differ.render.threads import render_thread_pages, threads_dir_name

    repo_s, chamber, slug, lo, hi, chain_dir_name, nav_html, out_root_s = job
    repo = Path(repo_s)
    out_root = Path(out_root_s)
    try:
        chain = build_chain(repo, chamber, slug, lo, hi)
    except ValueError as exc:
        return (f"{chamber}/{slug}", [], str(exc))
    threads_dir = threads_dir_name(chain, slug)
    fnames = render_thread_pages(chain, out_root / threads_dir, nav_html)
    thread_hrefs, section_hrefs = _thread_links(chain, threads_dir, fnames)
    rows = []
    for _, _, pair, diff in chain.transitions:
        render_pair(pair, diff, out_root / pair.slug(), nav_html, section_hrefs)
        rows.append((pair, diff.counts(), f"{pair.slug()}/index.html"))
    render_chain(chain, out_root / chain_dir_name, nav_html, thread_hrefs)
    return (f"{chamber}/{slug}", rows, None)


def _thread_links(
    chain, threads_dir: str, fnames: dict[tuple[str, ...], str]
) -> tuple[dict[tuple[str, ...], str], dict[int, str]]:
    """Thread hrefs keyed by row key (chain page) and by id(Section) (pair pages hold sections, not rows)."""
    thread_hrefs = {key: f"../{threads_dir}/{fname}" for key, fname in fnames.items()}
    section_hrefs = {
        sid: thread_hrefs[key]
        for sid, key in chain.section_row_keys().items()
        if key in thread_hrefs
    }
    return thread_hrefs, section_hrefs


# The acceptance demonstration: two House subcommittees across three successive fiscal years — six reports, four year-over-year comparisons.
DEMO_GROUPS = [
    ("house", "energy-water", 2025, 2027),
    ("house", "legislative-branch", 2025, 2027),
]


def build_demo(repo: Path, out_root: Path) -> int:
    """Build the demonstration site plus a manifest of source reports with SHA-256, so a reviewer can confirm the inputs."""
    import hashlib

    from budget_differ.chain import build_chain
    from budget_differ.render import render_chain, render_pair
    from budget_differ.render.assets import CSS
    from budget_differ.render.html import NavItem, render_nav
    from budget_differ.render.threads import render_thread_pages, threads_dir_name

    chains = [(g, build_chain(repo, g[0], g[1], g[2], g[3])) for g in DEMO_GROUPS]
    nav_items = [
        NavItem(chamber=ch, label=chain.subcommittee, dir=f"{ch}-{slug}-chain-fy{chain.fys[0]}-fy{chain.fys[-1]}")
        for (ch, slug, _, _), chain in chains
    ]
    index_rows = []
    manifest = {"comparisons": [], "reports": {}}
    for ((chamber, slug, _, _), chain), item in zip(chains, nav_items):
        nav_html = render_nav(nav_items, item.dir, "../")
        threads_dir = threads_dir_name(chain, slug)
        fnames = render_thread_pages(chain, out_root / threads_dir, nav_html)
        thread_hrefs, section_hrefs = _thread_links(chain, threads_dir, fnames)
        for _, _, pair, diff in chain.transitions:
            render_pair(pair, diff, out_root / pair.slug(), nav_html, section_hrefs)
            index_rows.append((pair, diff.counts(), f"{pair.slug()}/index.html"))
            manifest["comparisons"].append(
                {
                    "page": f"{pair.slug()}/index.html",
                    "old": pair.old.package_id,
                    "new": pair.new.package_id,
                    "policy_flags": sum(1 for sd in diff.sections for f in sd.flags if f.tier >= 2),
                    "section_counts": diff.counts(),
                }
            )
        render_chain(chain, out_root / item.dir, nav_html, thread_hrefs)
        for fy in chain.fys:
            e = chain.entries[fy]
            manifest["reports"][e.package_id] = {
                "chamber": e.chamber,
                "subcommittee": e.subcommittee,
                "fiscal_year": fy,
                "title": e.title,
                "html_url": e.html_url,
                "pdf_url": e.pdf_url,
                "sha256": hashlib.sha256(raw_path(repo, e).read_bytes()).hexdigest(),
            }
    (out_root / "style.css").write_text(CSS)
    render_top_index(index_rows, out_root, render_nav(nav_items, ".", ""))
    (out_root / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"built demo: {len(index_rows)} comparison(s) across {len(manifest['reports'])} reports → {out_root / 'index.html'}")
    return 0


def _build_chain(repo: Path, chamber: str, subcommittee: str, lo: int, hi: int) -> int:
    from budget_differ.chain import build_chain
    from budget_differ.render import render_chain
    from budget_differ.render.threads import render_thread_pages, threads_dir_name

    chain = build_chain(repo, chamber, subcommittee, lo, hi)
    out_root = Path("out")
    threads_dir = threads_dir_name(chain, subcommittee.lower())
    fnames = render_thread_pages(chain, out_root / threads_dir)
    thread_hrefs, section_hrefs = _thread_links(chain, threads_dir, fnames)
    # Pairwise pages from the same computed diffs, cross-linked to thread histories.
    for _, _, pair, diff in chain.transitions:
        render_pair(pair, diff, out_root / pair.slug(), section_hrefs=section_hrefs)
    from budget_differ.render.assets import CSS

    (out_root / "style.css").write_text(CSS)
    slug = f"{chamber}-{subcommittee.lower()}-chain-fy{chain.fys[0]}-fy{chain.fys[-1]}"
    out_path = render_chain(chain, out_root / slug, thread_hrefs=thread_hrefs)
    print(f"built chain across FY{chain.fys} + {len(fnames)} thread page(s) → {out_path}")
    return 0


def _dump_sections(repo: Path, package_id: str) -> int:
    entry = next((e for e in load_catalog(repo) if e.package_id == package_id), None)
    if entry is None:
        print(f"{package_id} not in catalog", file=sys.stderr)
        return 1
    if not raw_path(repo, entry).exists():
        print(f"raw file missing: {raw_path(repo, entry)}", file=sys.stderr)
        return 1
    doc = load_document(repo, entry)
    out = [
        {
            "heading": s.heading,
            "level": s.level,
            "path": list(s.path),
            "paragraphs": [asdict(p) for p in s.paragraphs],
            "table_spans": s.table_spans,
        }
        for s in doc.sections
    ]
    json.dump(out, sys.stdout, indent=2)
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
