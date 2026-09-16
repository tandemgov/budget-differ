"""Thread sections across multiple years of the same subcommittee report."""

from __future__ import annotations

import re

from dataclasses import dataclass, field
from pathlib import Path

from rapidfuzz import fuzz

from budget_differ.align import section_similarity, section_similarity_strict
from budget_differ.compare import compare_documents, load_document
from budget_differ.corpus import CatalogEntry, Pair, available_reports
from budget_differ.models import ChangeClass, Document, PairDiff, Section, SectionDiff

# Stitching a dead thread to a later-born one: content-overlap floors, lower when the normalized heading and title already agree.
STITCH_SAME_HEADING = 45.0
# Content alone must clear the same bar the pairwise aligner uses for a content-only rescue; stitching has no shared-parent constraint to lean on.
STITCH_CONTENT_ONLY = 80.0
# Content-only guards: token_set_ratio saturates when a short text's tokens all appear in a long one (a one-liner vs. a paragraph quoting it).
STITCH_MIN_BODY = 40
STITCH_MIN_LENGTH_RATIO = 0.4
# Short texts are templated, so overlap runs high between unrelated provisions; below this length the order-sensitive score must also pass.
STITCH_SHORT_BODY = 300
STITCH_SHORT_STRICT = 85.0


@dataclass
class ChainCell:
    slug: str  # pair page directory the chip links into
    sd: SectionDiff
    label: str  # display label; usually sd.change.label, else "reorganized"/"returned"


@dataclass
class Thread:
    """One section followed across the chain: fy → its Section in that year, and fy_new → the cell for the transition that landed there."""

    sections: dict[int, Section] = field(default_factory=dict)
    cells: dict[int, ChainCell] = field(default_factory=dict)
    score: float = 0.0

    def latest_section(self) -> Section:
        return self.sections[max(self.sections)]

    def earliest_section(self) -> Section:
        return self.sections[min(self.sections)]


@dataclass
class RowCell:
    label: str
    slug: str
    sd: SectionDiff  # anchor target on the pair page
    renamed: bool = False


@dataclass
class ChainRow:
    """One account (or general provision) followed across the chain. Topical sub-heads (PROGRAM DESCRIPTION, COMMITTEE RECOMMENDATION, ...) aggregate into their account's row: a sub-head appearing or vanishing while the account persists is a substantive change to the account, not an account drop."""

    heading: str
    crumb: tuple[str, ...]
    formerly: str | None
    key: tuple[str, ...] = ()
    cells: dict[int, RowCell] = field(default_factory=dict)
    members: list[Thread] = field(default_factory=list)
    score: float = 0.0


@dataclass
class Chain:
    chamber: str
    subcommittee: str
    fys: list[int]
    entries: dict[int, CatalogEntry]
    transitions: list[tuple[int, int, Pair, PairDiff]]
    threads: list[Thread]
    rows: list[ChainRow] = field(default_factory=list)

    def section_row_keys(self) -> dict[int, tuple[str, ...]]:
        """id(Section) → owning row key. Not derivable from a path: general provisions carry a birth-year suffix and sub-heads roll up into their account."""
        out: dict[int, tuple[str, ...]] = {}
        for row in self.rows:
            for t in row.members:
                for sec in t.sections.values():
                    out[id(sec)] = row.key
        return out


def build_chain(
    repo: Path, chamber: str, subcommittee: str, fy_from: int, fy_to: int
) -> Chain:
    group = [
        e
        for e in available_reports(repo)
        if e.chamber == chamber
        and e.slug() == subcommittee.lower()
        and fy_from <= (e.fiscal_year or 0) <= fy_to
    ]
    entries: dict[int, CatalogEntry] = {}
    for e in sorted(group, key=lambda e: e.package_id):
        assert e.fiscal_year is not None
        entries[e.fiscal_year] = e
    fys = sorted(entries)
    if len(fys) < 2:
        raise ValueError(
            f"need at least 2 fiscal years on disk for {chamber}/{subcommittee} "
            f"in FY{fy_from}-FY{fy_to}; found {fys or 'none'}"
        )

    docs: dict[int, Document] = {fy: load_document(repo, entries[fy]) for fy in fys}
    # Drop text-free GPO stubs ("TEXT NOT AVAILABLE REFER TO PDF") — diffing against one reports the whole bill as changed. The chain just skips that year.
    for fy in list(fys):
        if len(docs[fy].sections) < 15:
            print(f"  note: skipping FY{fy} ({entries[fy].package_id}) — no usable text")
            fys.remove(fy)
            del docs[fy], entries[fy]
    if len(fys) < 2:
        raise ValueError(
            f"fewer than 2 usable fiscal years for {chamber}/{subcommittee}"
        )
    return chain_from_docs(chamber, subcommittee, fys, docs, entries)


def chain_from_docs(
    chamber: str,
    subcommittee: str,
    fys: list[int],
    docs: dict[int, Document],
    entries: dict[int, CatalogEntry],
) -> Chain:
    """Thread already-loaded documents (ascending fiscal years) into a chain."""
    transitions: list[tuple[int, int, Pair, PairDiff]] = []
    for a, b in zip(fys, fys[1:]):
        pair = Pair(new=entries[b], old=entries[a])
        transitions.append((a, b, pair, compare_documents(docs[a], docs[b])))

    threads = _thread(fys, docs, transitions)
    _stitch(threads, fys)
    threads.sort(key=lambda t: -t.score)
    rows = _aggregate_rows(threads)
    return Chain(
        chamber=chamber,
        subcommittee=entries[fys[-1]].subcommittee or subcommittee,
        fys=fys,
        entries=entries,
        transitions=transitions,
        threads=threads,
        rows=rows,
    )


def _account_key(sec: Section) -> tuple[str, ...]:
    if sec.path[-1].startswith("SEC "):
        return sec.path  # general provisions stay their own row
    if sec.level >= 4 and len(sec.path) > 1:
        return sec.path[:-1]  # topical/annotation sub-head → its account
    return sec.path


_RANK = {"unchanged": 0, "numbers only": 1, "minor": 2, "substantive": 3}
_ORDER = ["unchanged", "numbers only", "minor", "substantive"]


def _aggregate_rows(threads: list[Thread]) -> list[ChainRow]:
    groups: dict[tuple[str, ...], list[Thread]] = {}
    seen_gp: dict[tuple, int] = {}
    for t in threads:
        key = _account_key(t.latest_section())
        if key[-1].startswith("SEC "):
            # A number is a slot, not an identity: distinct provisions that held "SEC 634" in different eras must not share a row. Key GP rows by the thread's birth year (plus an occurrence counter for same-year duplicates) — deterministic, so page filenames stay stable.
            birth = min(t.sections) if t.sections else 0
            n = seen_gp.get((key, birth), 0)
            seen_gp[(key, birth)] = n + 1
            key = (*key, f"B{birth}" + (f".{n}" if n else ""))
        groups.setdefault(key, []).append(t)

    rows: list[ChainRow] = []
    for key, members in groups.items():
        # GP rows carry a birth-year suffix for identity; display uses the bare key.
        display_key = key[:-1] if re.fullmatch(r"B\d+(\.\d+)?", key[-1]) else key
        # The account's own thread (section path == display key) names the row.
        main = next((t for t in members if t.latest_section().path == display_key), None)
        heading_sec = (main or members[0]).latest_section()
        heading = heading_sec.heading if main else display_key[-1].title()
        formerly = None
        if main is not None:
            earliest = main.earliest_section()
            if earliest.path[-1] != main.latest_section().path[-1]:
                formerly = f"{earliest.heading} (FY{min(main.sections)})"

        row = ChainRow(
            heading=heading, crumb=display_key[:-1], formerly=formerly, key=key, members=members
        )
        fys_with_cells = {fy for t in members for fy in t.cells}
        for fy in fys_with_cells:
            cells = [t.cells[fy] for t in members if fy in t.cells]
            labels = {c.label for c in cells}
            if labels <= {"dropped", "reorganized"}:
                label = "reorganized" if "reorganized" in labels else "dropped"
            elif labels <= {"new", "returned"}:
                label = "returned" if "returned" in labels else "new"
            else:
                # Mixed: the account persists; child add/drops rank as substantive.
                label = _ORDER[max(_RANK.get(c.label, 3) for c in cells)]
            anchor = next((c for c in cells if (c.sd.new or c.sd.old).path == display_key), cells[0])
            renamed = any(c.sd.renamed_from is not None for c in cells)
            row.cells[fy] = RowCell(label=label, slug=anchor.slug, sd=anchor.sd, renamed=renamed)
        row.score = sum(t.score for t in members)
        rows.append(row)
    rows.sort(key=lambda r: -r.score)
    return rows


def _thread(
    fys: list[int],
    docs: dict[int, Document],
    transitions: list[tuple[int, int, Pair, PairDiff]],
) -> list[Thread]:
    threads: list[Thread] = []
    by_section: dict[int, Thread] = {}

    for sec in docs[fys[0]].sections:
        t = Thread(sections={fys[0]: sec})
        threads.append(t)
        by_section[id(sec)] = t

    for a, b, pair, diff in transitions:
        slug = pair.slug()
        for sd in diff.sections:
            if sd.old is not None:
                t = by_section.get(id(sd.old))
                if t is None:  # defensive: old doc section not seeded (shouldn't happen)
                    t = Thread(sections={a: sd.old})
                    threads.append(t)
                    by_section[id(sd.old)] = t
            else:
                t = Thread()
                threads.append(t)
            if sd.new is not None:
                t.sections[b] = sd.new
                by_section[id(sd.new)] = t
            t.cells[b] = ChainCell(slug=slug, sd=sd, label=sd.change.label)
            t.score += sd.score
    return threads


def _body(sec: Section) -> str:
    return " ".join(p.text for p in sec.paragraphs)[:2000]


def _stitch(threads: list[Thread], fys: list[int]) -> None:
    """Merge a thread that died into one born at or after its death when they are plainly the same section: a same-transition drop+new pair the aligner couldn't marry ("reorganized"), or a section skipping a year and coming back ("returned")."""
    first_fy, last_fy = fys[0], fys[-1]
    while True:
        dead = [
            t
            for t in threads
            if t.cells
            and max(t.sections) < last_fy
            and t.cells[max(t.cells)].sd.change == ChangeClass.REMOVED
        ]
        born = [t for t in threads if t.sections and min(t.sections) > first_fy]
        candidates: list[tuple[float, Thread, Thread]] = []
        for dt in dead:
            death_fy = max(dt.cells)
            dsec = dt.latest_section()
            for bt in born:
                if bt is dt:
                    continue
                birth_fy = min(bt.sections)
                if birth_fy < death_fy:
                    continue  # overlapping lifetimes — not the same section
                bsec = bt.earliest_section()
                # A general provision's number is not its identity — renumbering means two unrelated provisions can share "SEC 634" years apart, so SEC threads never get the same-heading discount, and their similarity compares scaffold-stripped predicate tails.
                same_heading = (
                    dsec.path[-1] == bsec.path[-1]
                    and dsec.path[0] == bsec.path[0]
                    and not dsec.path[-1].startswith("SEC ")
                )
                score = section_similarity(dsec, bsec)
                if same_heading:
                    if score >= STITCH_SAME_HEADING:
                        candidates.append((score + 10, dt, bt))
                elif score >= STITCH_CONTENT_ONLY and _comparable(dsec, bsec):
                    candidates.append((score, dt, bt))
        merged = False
        used: set[int] = set()
        for _, dt, bt in sorted(candidates, key=lambda c: -c[0]):
            if id(dt) in used or id(bt) in used:
                continue
            used.add(id(dt))
            used.add(id(bt))
            _merge(dt, bt, threads)
            merged = True
        if not merged:
            break


def _comparable(a: Section, b: Section) -> bool:
    """Whether an overlap score means anything here: both long enough to carry identity and close enough in length that neither is quoted inside the other."""
    la, lb = len(_body(a)), len(_body(b))
    lo, hi = min(la, lb), max(la, lb)
    if lo < STITCH_MIN_BODY or lo / hi < STITCH_MIN_LENGTH_RATIO:
        return False
    if lo < STITCH_SHORT_BODY and section_similarity_strict(a, b) < STITCH_SHORT_STRICT:
        return False
    return True


def _merge(dead: Thread, borne: Thread, threads: list[Thread]) -> None:
    death_fy = max(dead.cells)
    birth_fy = min(borne.cells)
    birth_cell = borne.cells[birth_fy]
    if birth_fy == death_fy:
        # Same transition: one "reorganized" cell (linking to the new side) replaces the dropped and new cells.
        dead.cells[death_fy] = ChainCell(birth_cell.slug, birth_cell.sd, "reorganized")
    else:
        borne.cells[birth_fy] = ChainCell(birth_cell.slug, birth_cell.sd, "returned")
    dead.sections.update(borne.sections)
    for fy, cell in borne.cells.items():
        if fy not in dead.cells:
            dead.cells[fy] = cell
    dead.score += borne.score
    threads.remove(borne)
