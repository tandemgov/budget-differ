"""Read the approps repo's catalog and discover comparable report pairs."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from budget_differ.config import catalog_path, raw_dir


def _norm(name: str) -> str:
    t = re.sub(r"[^A-Z0-9 ]+", " ", name.upper())
    return re.sub(r"\s+", " ", t).strip()


@lru_cache(maxsize=4)
def _lexicons(repo: Path) -> tuple[frozenset[str], frozenset[str]]:
    path = repo / "data" / "reference" / "federal_accounts.json"
    if not path.exists():
        return frozenset(), frozenset()
    data = json.loads(path.read_text())
    accounts = next((v for k, v in data.items() if k != "metadata"), [])
    agencies = {_norm(a["managing_agency"]) for a in accounts if a.get("managing_agency")}
    # A bureau name pins the bureau tier only when it identifies ONE agency.
    # Generic names ("Office of Inspector General" exists under dozens of agencies) are usually sibling accounts in report structure, and pinning them creates false parents over the accounts that follow.
    bureau_agencies: dict[str, set[str]] = {}
    for a in accounts:
        if a.get("bureau_name") and a.get("managing_agency"):
            bureau_agencies.setdefault(_norm(a["bureau_name"]), set()).add(
                _norm(a["managing_agency"])
            )
    bureaus = {b for b, ags in bureau_agencies.items() if len(ags) == 1}
    return frozenset(agencies), frozenset(bureaus - agencies)


def load_agency_lexicon(repo: Path) -> frozenset[str]:
    """Normalized federal agency names (USASpending managing_agency) — pin headings to the agency tier regardless of case styling."""
    return _lexicons(repo)[0]


def load_bureau_lexicon(repo: Path) -> frozenset[str]:
    """Normalized bureau names (IRS, TIGTA, ...) — pin headings to the bureau tier."""
    return _lexicons(repo)[1]


@dataclass(frozen=True)
class CatalogEntry:
    package_id: str
    congress: int
    chamber: str
    subcommittee: str | None
    fiscal_year: int | None
    stage: str
    title: str
    html_url: str
    pdf_url: str = ""

    def slug(self) -> str:
        assert self.subcommittee is not None
        return self.subcommittee.lower()


def load_catalog(repo: Path) -> list[CatalogEntry]:
    data = json.loads(catalog_path(repo).read_text())
    entries = []
    for row in data:
        entries.append(
            CatalogEntry(
                package_id=row["package_id"],
                congress=int(row["congress"]),
                chamber=row["chamber"],
                subcommittee=row.get("subcommittee"),
                fiscal_year=row.get("fiscal_year"),
                stage=row.get("stage", "committee"),
                title=row.get("title", ""),
                html_url=row.get("html_url", ""),
                pdf_url=row.get("pdf_url", ""),
            )
        )
    return entries


def raw_path(repo: Path, entry: CatalogEntry) -> Path:
    return raw_dir(repo) / str(entry.congress) / entry.chamber / f"{entry.package_id}.htm"


def pdf_path(repo: Path, entry: CatalogEntry) -> Path:
    return raw_path(repo, entry).with_suffix(".pdf")


def available_reports(repo: Path) -> list[CatalogEntry]:
    """Committee-stage reports with a known subcommittee and a raw HTML file on disk.

    Titles starting with "MAKING ..." are bill-action phrasing (continuing-resolution / omnibus conference reports, e.g. CRPT-116hrpt9) — not subcommittee bill reports, and diffing one against a subcommittee report mismatches every section.
    """
    return [
        e
        for e in load_catalog(repo)
        if e.stage == "committee"
        and e.subcommittee
        and e.fiscal_year
        and not e.title.upper().startswith("MAKING")
        and raw_path(repo, e).exists()
    ]


@dataclass(frozen=True)
class Pair:
    new: CatalogEntry
    old: CatalogEntry

    def slug(self) -> str:
        return (
            f"{self.new.chamber}-{self.new.slug()}"
            f"-fy{self.old.fiscal_year}-fy{self.new.fiscal_year}"
        )


def discover_pairs(
    reports: list[CatalogEntry],
    chamber: str | None = None,
    subcommittee: str | None = None,
    fiscal_year: int | None = None,
) -> list[Pair]:
    """For each report, pair it against the same chamber+subcommittee report from the latest earlier fiscal year on disk. Senate gap years fall back further than FY-1."""
    groups: dict[tuple[str, str], list[CatalogEntry]] = {}
    for e in reports:
        if chamber and e.chamber != chamber:
            continue
        if subcommittee and e.slug() != subcommittee.lower():
            continue
        groups.setdefault((e.chamber, e.slug()), []).append(e)

    pairs: list[Pair] = []
    for group in groups.values():
        # One report per FY: if duplicates exist, keep the highest report number.
        by_fy: dict[int, CatalogEntry] = {}
        for e in sorted(group, key=lambda e: e.package_id):
            assert e.fiscal_year is not None
            by_fy[e.fiscal_year] = e
        fys = sorted(by_fy)
        for i, fy in enumerate(fys):
            if fiscal_year and fy != fiscal_year:
                continue
            if i == 0:
                continue
            pairs.append(Pair(new=by_fy[fy], old=by_fy[fys[i - 1]]))
    return sorted(pairs, key=lambda p: (p.new.chamber, p.new.slug(), p.new.fiscal_year or 0))
