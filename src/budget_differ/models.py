"""Core data model: segmented documents and diff results."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum

from budget_differ.policy import PolicyFlag


class ChangeClass(IntEnum):
    """Ordered by severity so max() over paragraphs yields the section class."""

    UNCHANGED = 0
    NUMBERS_ONLY = 1
    MINOR = 2
    SUBSTANTIVE = 3
    ADDED = 4
    REMOVED = 5

    @property
    def label(self) -> str:
        return {
            ChangeClass.UNCHANGED: "unchanged",
            ChangeClass.NUMBERS_ONLY: "numbers only",
            ChangeClass.MINOR: "minor",
            ChangeClass.SUBSTANTIVE: "substantive",
            ChangeClass.ADDED: "new",
            ChangeClass.REMOVED: "dropped",
        }[self]


@dataclass
class Paragraph:
    text: str
    kind: str = "narrative"  # narrative | directive | gp_section
    topic: str | None = None  # "Bayonne, NJ" from a "Topic.--" lead-in, or "Section 108"


@dataclass
class Section:
    heading: str
    level: int  # 0=title, 1=agency/department, 2=account, 3=topical sub-head
    path: tuple[str, ...]  # normalized ancestor headings + self — the alignment key
    paragraphs: list[Paragraph] = field(default_factory=list)
    table_spans: int = 0  # count of table regions dropped inside this section
    order: int = 0


@dataclass
class Document:
    package_id: str
    chamber: str
    subcommittee: str
    fiscal_year: int
    sections: list[Section] = field(default_factory=list)


@dataclass
class ParagraphDiff:
    old: Paragraph | None
    new: Paragraph | None
    change: ChangeClass
    # Word-level opcodes for rendering: list of (tag, old_tokens, new_tokens)
    opcodes: list[tuple[str, list[str], list[str]]] = field(default_factory=list)
    changed_words: int = 0
    # Policy signals on a paired edit (see policy.py); a review-tier flag promotes `change` to SUBSTANTIVE.
    flags: list[PolicyFlag] = field(default_factory=list)
    # Size-only class before any policy promotion, kept so evaluation can separate the two signals.
    literal_change: ChangeClass | None = None
    # Policy families present in a whole new or dropped paragraph ("deadline", "prohibition").
    tags: list[str] = field(default_factory=list)


@dataclass
class RelatedSection:
    """A likely counterpart of a dropped/new section that fell below the alignment threshold — a rename or reorganization the reader should see, not assert."""

    heading: str
    path: tuple[str, ...]
    overlap: float  # token_set_ratio, 0-100
    sd: SectionDiff | None = None  # the counterpart's diff, for its page anchor


@dataclass
class SectionDiff:
    old: Section | None
    new: Section | None
    change: ChangeClass
    paragraph_diffs: list[ParagraphDiff] = field(default_factory=list)
    changed_words: int = 0
    score: float = 0.0
    related: RelatedSection | None = None
    renamed_from: str | None = None  # prior-year heading when a rename was promoted to a match
    anchor: str = ""  # page-unique id, assigned once per PairDiff so every link agrees

    @property
    def flags(self) -> list[PolicyFlag]:
        return [f for pd in self.paragraph_diffs for f in pd.flags]

    @property
    def display_path(self) -> tuple[str, ...]:
        sec = self.new or self.old
        assert sec is not None
        return sec.path


@dataclass
class ParagraphMove:
    """A paragraph that relocated to a different section between years — most often a directive carried into a renamed/reorganized account. Rendered as a move, not as a deletion plus an addition."""

    old_section_heading: str
    old_section_path: tuple[str, ...]
    new_section_heading: str
    new_section_path: tuple[str, ...]
    diff: ParagraphDiff  # UNCHANGED for verbatim moves; word-level diff when also edited
    # Owning diffs: links resolve through their anchors, since a path alone cannot name the second of two duplicate sections or a renamed one.
    old_sd: SectionDiff | None = None
    new_sd: SectionDiff | None = None


@dataclass
class PairDiff:
    new_doc: Document
    old_doc: Document
    sections: list[SectionDiff] = field(default_factory=list)
    moves: list[ParagraphMove] = field(default_factory=list)

    def counts(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for sd in self.sections:
            out[sd.change.label] = out.get(sd.change.label, 0) + 1
        return out
