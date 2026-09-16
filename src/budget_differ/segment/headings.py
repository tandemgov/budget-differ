"""Group heading lines into headings and assign hierarchy levels."""

from __future__ import annotations

import re
from dataclasses import dataclass

# Case-insensitive: body headings print "TITLE V--..." but TOC entries print "Title V--..." and both must classify as titles.
_TITLE = re.compile(r"^TITLE\s+[IVXLC]+\b", re.IGNORECASE)
_GENERAL_PROVISIONS = re.compile(r"GENERAL PROVISION")
# Parenthetical subtitles printed under an account heading — annotations, not children.
_ANNOTATION = re.compile(r"^\(|^INCLUDING\s|^LEGISLATIVE PROPOSAL", re.IGNORECASE)

# Recurring topical sub-heads that appear under many accounts; never treat as accounts.
# Grounded in a corpus frequency count (headings repeating >=3x within single reports):
# genuinely repeating *accounts* (SALARIES AND EXPENSES, CONSTRUCTION, OIG) stay out.
TOPICAL = {
    "INTRODUCTION",
    "COMMITTEE RECOMMENDATION",
    "COMMITTEE RECOMMENDATIONS",
    "COMMITTEE DIRECTIVES",
    "COMMITTEE PROVISIONS",
    "ITEMS OF INTEREST",
    "NEW STARTS",
    "ADDITIONAL FUNDING",
    "OVERVIEW OF RECOMMENDATION",
    "REPROGRAMMING",
    "CONGRESSIONALLY DIRECTED SPENDING",
    "MISSION",
    "BUDGET HIGHLIGHTS",
    "PROGRAM DESCRIPTION",
    "ADMINISTRATIVE PROVISION",
    "ADMINISTRATIVE PROVISIONS",
    "LIMITATION ON OBLIGATIONS",
    "LIQUIDATION OF CONTRACT AUTHORIZATION",
    "NET APPROPRIATION",
    "GROSS APPROPRIATION",
    "FUNDING INCREASES",
    "FUNDING HIGHLIGHTS",
    "EXPLANATION OF PROJECT LEVEL ADJUSTMENTS",
    "TRANSFER OF FUNDS",
    # Senate Defense prints both under every appropriation account.
    "COMMITTEE RECOMMENDED PROGRAM",
    "COMMITTEE RECOMMENDED ADJUSTMENTS",
}


@dataclass
class Heading:
    text: str  # merged, whitespace-collapsed
    level: int
    line_start: int
    line_end: int
    is_general_provisions: bool = False
    # A parenthetical subtitle ("(INCLUDING TRANSFER OF FUNDS)") belongs to the heading above it and never opens a section.
    is_annotation: bool = False


_TRAILING_ACRONYM = re.compile(r"\s*\([A-Z][A-Za-z0-9&-]{1,5}\)\s*$")


def normalize_heading(text: str) -> str:
    """Alignment-path normalization: insensitive to case, punctuation, years, and a trailing acronym ("(VHA)")."""
    t = _TRAILING_ACRONYM.sub("", text).upper()
    t = re.sub(r"\b(19|20)\d{2}\b", "FY", t)
    t = re.sub(r"[^A-Z0-9 ]+", " ", t)
    return re.sub(r"\s+", " ", t).strip()


_DEPARTMENT = re.compile(r"^DEPARTMENT OF\b", re.IGNORECASE)

# Agencies absent from the USASpending managing_agency universe: off-budget entities that still get report language, and historical names of since-renamed agencies (USASpending only records the current name — Broadcasting Board of Governors became the U.S. Agency for Global Media in 2018, but FY2016-2019 reports print the old name as the agency heading).
AGENCY_SUPPLEMENT = frozenset(
    {
        "UNITED STATES POSTAL SERVICE",
        "U S POSTAL SERVICE",
        "BROADCASTING BOARD OF GOVERNORS",
        # Standard agency-tier budget grouping in State/Foreign Ops bills (Treasury 11-x accounts: IDA, ESF, Transition Initiatives, ...); without it the preceding department keeps the agency slot across the title boundary.
        "FUNDS APPROPRIATED TO THE PRESIDENT",
        # Reports drop the "United States" prefix the lexicon carries.
        "TRADE AND DEVELOPMENT AGENCY",
    }
)

# Legislative agencies absent from USASpending (all but GAO); unpinned, each nests under the agency before it.
# Added only for Legislative Branch reports: others print SENATE and HOUSE OF REPRESENTATIVES over procedure sections.
LEGISLATIVE_AGENCIES = frozenset(
    {
        "SENATE",
        "HOUSE OF REPRESENTATIVES",
        "JOINT ITEMS",
        "UNITED STATES CAPITOL POLICE",
        "CAPITOL POLICE",
        "OFFICE OF COMPLIANCE",
        "OFFICE OF CONGRESSIONAL WORKPLACE RIGHTS",
        "CONGRESSIONAL BUDGET OFFICE",
        "ARCHITECT OF THE CAPITOL",
        "LIBRARY OF CONGRESS",
        "GOVERNMENT PRINTING OFFICE",
        "GOVERNMENT PUBLISHING OFFICE",
        "GOVERNMENT ACCOUNTABILITY OFFICE",
        "OPEN WORLD LEADERSHIP CENTER",
        "OPEN WORLD LEADERSHIP CENTER TRUST FUND",
        "CONGRESSIONAL OFFICE FOR INTERNATIONAL LEADERSHIP",
        "CONGRESSIONAL OFFICE FOR INTERNATIONAL LEADERSHIP FUND",
        "JOHN C STENNIS CENTER FOR PUBLIC SERVICE TRAINING AND DEVELOPMENT",
    }
)

# Legislative branch sub-agencies that head their own "Salaries and Expenses" accounts; the lexicon's bureau list lacks them for the same reason.
LEGISLATIVE_BUREAUS = frozenset(
    {
        "COPYRIGHT OFFICE",
        "CONGRESSIONAL RESEARCH SERVICE",
        "NATIONAL LIBRARY SERVICE FOR THE BLIND AND PRINT DISABLED",
        "NATIONAL LIBRARY SERVICE FOR THE BLIND AND PHYSICALLY HANDICAPPED",
        "BOOKS FOR THE BLIND AND PHYSICALLY HANDICAPPED",
        "PUBLIC INFORMATION PROGRAMS OF THE SUPERINTENDENT OF DOCUMENTS",
    }
)


def _kind(text: str, agencies: frozenset[str], bureaus: frozenset[str]) -> str:
    upper = text.upper()
    if _TITLE.match(text):
        return "title"
    if _GENERAL_PROVISIONS.search(upper):
        return "gp"
    if _ANNOTATION.match(text):
        return "annotation"
    # Agency/bureau checks precede the case test: Senate reports print these headings in Title Case ("General Services Administration", "Internal Revenue Service"), which would otherwise read as topical sub-heads. Bureau membership outranks the DEPARTMENT OF pattern: "Department of Defense Education Activity" is a bureau.
    norm = normalize_heading(text)
    if norm in agencies or norm in AGENCY_SUPPLEMENT:
        return "agency"
    if norm in bureaus:
        return "bureau"
    # A known agency name plus trailing words is a sub-entity ("DEPARTMENT OF DEFENSE EDUCATION ACTIVITY").
    # Legislative accounts reuse agency names ("Capitol Police Buildings, Grounds, and Security" is an AOC account), so they are exempt.
    if any(norm.startswith(a + " ") for a in agencies if a not in LEGISLATIVE_AGENCIES):
        return "bureau"
    if _DEPARTMENT.match(text):
        return "agency"
    if upper in TOPICAL or _upper_share(text) < 0.9:
        return "topical"
    return "structural"


def assign_levels(
    headings: list[Heading],
    agencies: frozenset[str] = frozenset(),
    bureaus: frozenset[str] = frozenset(),
    money_after: frozenset[int] | set[int] = frozenset(),
) -> None:
    """Assign levels in place. Tiers: 0 = TITLE N--, 1 = agency (departments and lexicon-matched federal agencies — pinned so a following bureau chain cannot evict them), 2 = adjacency-promoted parent (bureau/activity stacked directly above another structural heading), 3 = account (structural default; GENERAL PROVISIONS), 4 = topical sub-heads and parenthetical annotations. Promotion to level 2 requires the adjacent next heading to be structural — a following PROGRAM DESCRIPTION or "(INCLUDING TRANSFER OF FUNDS)" is a sub-head of this section, not a child."""
    kinds = [_kind(h.text, agencies, bureaus) for h in headings]
    occurrences: dict[str, int] = {}
    for h in headings:
        n = normalize_heading(h.text)
        occurrences[n] = occurrences.get(n, 0) + 1
    for idx, h in enumerate(headings):
        kind = kinds[idx]
        if kind == "title":
            h.level = 0
        elif kind == "agency":
            h.level = 1
        elif kind == "bureau":
            h.level = 2
        elif kind == "gp":
            h.level = 3
            h.is_general_provisions = True
        elif kind in ("annotation", "topical"):
            h.is_annotation = kind == "annotation"
            # Case alone can't demote a structural heading: a Title Case heading that opens a money block, or that appears exactly once in the report ("District of Columbia Funds"), is an account — real topical sub-heads (PROGRAM DESCRIPTION) recur dozens of times.
            if (
                kind == "topical"
                and h.text.upper() not in TOPICAL
                and (idx in money_after or occurrences[normalize_heading(h.text)] == 1)
            ):
                h.level = 3
                nxt = headings[idx + 1] if idx + 1 < len(headings) else None
                # Stacked directly over a recurring account ("Supreme Court of the United States" over SALARIES AND EXPENSES), it is that account's owner.
                if (
                    nxt is not None
                    and nxt.line_start - h.line_end <= 3
                    and kinds[idx + 1] == "structural"
                    and occurrences[normalize_heading(nxt.text)] > 1
                    and normalize_heading(nxt.text) != normalize_heading(h.text)
                ):
                    h.level = 2
            else:
                h.level = 4
        else:
            nxt = headings[idx + 1] if idx + 1 < len(headings) else None
            if (
                nxt is not None
                and nxt.line_start - h.line_end <= 3
                and kinds[idx + 1] == "structural"
                # A caption printed twice in a row is one heading, not a parent over itself.
                and normalize_heading(nxt.text) != normalize_heading(h.text)
            ):
                h.level = 2
            else:
                h.level = 3


def _upper_share(s: str) -> float:
    letters = [c for c in s if c.isalpha()]
    if not letters:
        return 0.0
    return sum(1 for c in letters if c.isupper()) / len(letters)
