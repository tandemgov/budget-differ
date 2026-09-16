"""Policy-signal rules: flag small edits whose wording changes what the report asks for ("not", "may" → "shall", "90" → "180 days").

Rationale, rule families, and known failure modes: docs/methodology.md.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Flags at or above this tier promote a paired paragraph to SUBSTANTIVE; lower tiers annotate without promoting.
REVIEW = 2
NOTE = 1


@dataclass(frozen=True)
class PolicyFlag:
    category: str  # e.g. "negation", "discretion", "deadline"
    reason: str  # one line: why this warrants review
    before: tuple[str, str, str]  # (leading context, changed words, trailing context) in the prior year
    after: tuple[str, str, str]  # same, in the proposed year
    tier: int = REVIEW

    @property
    def label(self) -> str:
        return CATEGORY_LABELS.get(self.category, self.category)


CATEGORY_LABELS = {
    "negation": "negation",
    "discretion": "discretion / force",
    "prohibition": "prohibition",
    "eligibility": "eligibility / scope",
    "condition": "condition",
    "reporting": "reporting requirement",
    "provision": "provision effect",
    "deadline": "deadline",
    "limit": "floor / ceiling",
    "share": "percentage / share",
    "quantity": "program quantity",
    "funding": "dollar amount",
    "wording": "wording change",
}

# Whether a changed narrative dollar figure alone promotes a paragraph is a client decision (docs/substantive-definition.md).
FUNDING_TIER = NOTE

# Ranking weight per category: how strongly a flag lifts its section in the ranked list.
CATEGORY_WEIGHT = {
    "negation": 60.0,
    "prohibition": 60.0,
    "discretion": 50.0,
    "eligibility": 40.0,
    "condition": 40.0,
    "deadline": 40.0,
    "limit": 40.0,
    "share": 40.0,
    "quantity": 30.0,
    "reporting": 30.0,
    "provision": 40.0,
    "funding": 8.0,
    "wording": 6.0,
}

# Word-level context kept on each side of a changed run for display.
SNIPPET_CONTEXT = 8
# Longer changed runs are elided in the middle for display.
SNIPPET_MAX_WORDS = 30
# Equal-token gaps at most this long merge adjacent edits into one hunk, so "may not" split across two opcodes reads as one change.
HUNK_GAP = 3
# Tokens of surrounding context searched for a number's governing phrase ("not less than", "within").
NUMBER_CONTEXT = 5

# Directive force, strongest first. A change in which tier appears is a change in discretion.
_FORCE_TIERS: list[tuple[str, re.Pattern[str]]] = [
    ("mandatory", re.compile(r"\b(shall|must|requires?|required|directs?|directed|instructs?|instructed|mandates)\b")),
    ("expectation", re.compile(r"\b(expects?|expected|should|will)\b")),
    ("hortatory", re.compile(r"\b(urges?|urged|encourages?|encouraged|recommends?(?!\s+(?:\S+\s+){0,3}\$)|requests?|requested|consider)\b")),
    ("permissive", re.compile(r"\b(may|can|allows?|allowed|permits?|permitted|authorizes?|authorized|discretion)\b")),
]

_FAMILIES: dict[str, tuple[re.Pattern[str], str]] = {
    "negation": (
        re.compile(r"\b(not|no|never|none|neither|nor|cannot|without)\b"),
        "negation added or removed — can reverse the meaning of the sentence",
    ),
    "prohibition": (
        re.compile(
            r"\b(prohibit\w*|none of the funds|no funds|may not|shall not|must not|restrict\w*|"
            r"preclud\w*|ban(?:s|ned)?|forbid\w*|barred)\b"
        ),
        "prohibition or restriction language changed",
    ),
    "eligibility": (
        re.compile(
            r"\b(eligib\w*|ineligib\w*|qualif\w*|only|exclusively|solely|limited to|"
            r"priority|prioritiz\w*|preference|except|exclud\w*|exempt\w*)\b"
        ),
        "eligibility, priority, or scope limitation changed",
    ),
    "condition": (
        re.compile(
            r"\b(unless|until|provided(?:, however,)? that|subject to|contingent|conditions?|conditioned|"
            r"only if|if|prior to|notwithstanding|approv\w*|in consultation with|in coordination with)\b"
        ),
        "condition or prerequisite changed",
    ),
    "reporting": (
        re.compile(r"\b(reports?|briefings?|brief|notif\w*|certif\w*|submit\w*|testify|testimony)\b"),
        "reporting, briefing, or notification requirement changed",
    ),
    "provision": (
        re.compile(r"\b(modif\w*|amend\w*|new provision|repeal\w*|rescind\w*|rescission\w*|extend\w*|terminat\w*|expir\w*)\b"),
        "description of what a provision does changed (modifies, extends, rescinds, repeals, terminates)",
    ),
}

_DEADLINE_PHRASE = re.compile(r"\b(not later than|no later than|within|deadline)\b")
_LIMIT_PHRASE = re.compile(
    r"\b(not less than|not more than|not to exceed|no more than|no less than|no fewer than|not fewer than|"
    r"up to|at least|a minimum of|a maximum of|minimum|maximum|cap|ceiling|limited to|limits? to|limit)\b"
)
_TIME_UNIT = re.compile(r"^(days?|weeks?|months?|years?|calendar|business)$")
_PERCENT = re.compile(r"^(percent|per|%)")
_CITATION_BEFORE = re.compile(
    r"\b(section|sections|sec|secs|title|division|public law|law|paragraph|subsection|clause|u\.?s\.?c|stat|number|no|h\.?r|s|report|rept|congress)\s*$"
)
_MONTH = re.compile(r"^(january|february|march|april|may|june|july|august|september|october|november|december)$")
_NUMBER_WORDS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9,
    "ten": 10, "eleven": 11, "twelve": 12, "fifteen": 15, "twenty": 20, "thirty": 30, "forty": 40,
    "forty-five": 45, "fifty": 50, "sixty": 60, "ninety": 90, "hundred": 100,
}

# Words whose insertion or removal alone does not change meaning.
_STOPWORDS = frozenset(
    "a an the of and to in on for its their his her this that these those such also date as with by at "
    "is are be been being which who whom whose it also further additionally therefore however".split()
)


def _norm(tok: str) -> str:
    return tok.lower().strip(".,;:()[]\"'“”‘’")


def _is_year(tok: str) -> bool:
    return re.fullmatch(r"(19|20)\d{2}", _norm(tok)) is not None


def _number_value(tok: str) -> float | None:
    t = _norm(tok).replace("$", "").replace(",", "").rstrip("%")
    if t in _NUMBER_WORDS:
        return float(_NUMBER_WORDS[t])
    try:
        return float(t)
    except ValueError:
        return None


def _is_numeric(tok: str) -> bool:
    return _number_value(tok) is not None


def _join(tokens: list[str]) -> str:
    return " ".join(tokens)


class _Scoped:
    """A negation pattern that ignores negators belonging to limit, deadline, or prohibition phrases, which have their own families."""

    _mask = re.compile(
        r"\b(not less than|not more than|not to exceed|no more than|no less than|no fewer than|not fewer than|"
        r"not later than|no later than|none of the funds|no funds|may not|shall not|must not)\b"
    )

    def __init__(self, pattern: re.Pattern[str]) -> None:
        self.pattern = pattern

    def findall(self, text: str) -> list[str]:
        return self.pattern.findall(self._mask.sub(" ", text))


def _neg_scope(pattern: re.Pattern[str]) -> _Scoped:
    return _Scoped(pattern)


def _count(pattern: re.Pattern[str], text: str) -> int:
    return len(pattern.findall(text.lower()))


@dataclass
class _Hunk:
    i1: int
    i2: int
    j1: int
    j2: int
    parts: list[tuple[int, int, int, int]]  # the individual edits merged into this hunk


def _hunks(old: list[str], new: list[str], opcodes: list[tuple[str, list[str], list[str]]]) -> list[_Hunk]:
    """Rebuild index ranges from the stored opcodes and merge edits separated by short equal runs."""
    out: list[_Hunk] = []
    i = j = 0
    gap_after_last: int | None = None
    for tag, o, n in opcodes:
        if tag == "equal":
            i += len(o)
            j += len(n)
            if out:
                gap_after_last = len(o)
            continue
        part = (i, i + len(o), j, j + len(n))
        if out and gap_after_last is not None and gap_after_last <= HUNK_GAP:
            out[-1].i2 = i + len(o)
            out[-1].j2 = j + len(n)
            out[-1].parts.append(part)
        else:
            out.append(_Hunk(i, i + len(o), j, j + len(n), [part]))
        i += len(o)
        j += len(n)
        gap_after_last = 0
    return out


def _side(tokens: list[str], a: int, b: int) -> tuple[str, str, str]:
    lo = max(0, a - SNIPPET_CONTEXT)
    hi = min(len(tokens), b + SNIPPET_CONTEXT)
    pre = ("… " if lo > 0 else "") + _join(tokens[lo:a])
    post = _join(tokens[b:hi]) + (" …" if hi < len(tokens) else "")
    mid = tokens[a:b]
    if len(mid) > SNIPPET_MAX_WORDS:
        head = SNIPPET_MAX_WORDS * 2 // 3
        mid = mid[:head] + ["…"] + mid[-(SNIPPET_MAX_WORDS - head) :]
    return (pre, _join(mid), post)


def _focus(old: list[str], new: list[str], h: _Hunk, pattern) -> tuple[int, int, int, int]:
    """The single edit inside a hunk that carries a family's change, so a flag on a long rewrite points at the words that tripped it."""
    for i1, i2, j1, j2 in h.parts:
        if _count(pattern, _window(old, i1, i2)) != _count(pattern, _window(new, j1, j2)):
            return (i1, i2, j1, j2)
    return (h.i1, h.i2, h.j1, h.j2)


def _window(tokens: list[str], a: int, b: int, pad: int = HUNK_GAP + 1) -> str:
    return _join(tokens[max(0, a - pad) : b + pad]).lower()


def flag_edit(
    old_text: str, new_text: str, opcodes: list[tuple[str, list[str], list[str]]], year_delta: int = 1
) -> list[PolicyFlag]:
    """Flags for one paired paragraph, given its word-level opcodes (as stored on ParagraphDiff); year_delta is the fiscal-year gap between the reports."""
    old = old_text.split()
    new = new_text.split()
    hunks = _hunks(old, new, opcodes)
    if not hunks:
        return []
    flags: list[PolicyFlag] = []
    seen: set[tuple[str, int]] = set()
    flagged_hunks: set[int] = set()

    def add(category: str, reason: str, h: _Hunk, tier: int = REVIEW, pattern=None, span=None) -> None:
        key = (category, h.i1)
        if key in seen:
            return
        seen.add(key)
        flagged_hunks.add(h.i1)
        if span is None:
            span = _focus(old, new, h, pattern) if pattern is not None else (h.i1, h.i2, h.j1, h.j2)
        i1, i2, j1, j2 = span
        flags.append(PolicyFlag(category, reason, _side(old, i1, i2), _side(new, j1, j2), tier))

    old_l, new_l = old_text.lower(), new_text.lower()
    families = {c: (_neg_scope(pattern) if c == "negation" else pattern, reason) for c, (pattern, reason) in _FAMILIES.items()}

    # Discretion: the set of force tiers present changed at paragraph level; point at the hunk that carries it.
    old_force = [_count(p, old_l) for _, p in _FORCE_TIERS]
    new_force = [_count(p, new_l) for _, p in _FORCE_TIERS]
    if old_force != new_force:
        for h in hunks:
            for part in h.parts:
                ow, nw = _window(old, part[0], part[1]), _window(new, part[2], part[3])
                before = [name for name, p in _FORCE_TIERS if _count(p, ow) > _count(p, nw)]
                after = [name for name, p in _FORCE_TIERS if _count(p, nw) > _count(p, ow)]
                if before or after:
                    add("discretion", _force_reason(before, after), h, span=part)
                    break

    prohibition_hunks: set[int] = set()
    for category, (pattern, reason) in families.items():
        if _count(pattern, old_l) == _count(pattern, new_l):
            continue
        for h in hunks:
            if category == "negation" and h.i1 in prohibition_hunks:
                continue
            if _count(pattern, _window(old, h.i1, h.i2)) != _count(pattern, _window(new, h.j1, h.j2)):
                add(category, reason, h, pattern=pattern)
                if category == "prohibition":
                    prohibition_hunks.add(h.i1)

    for h in hunks:
        for category, reason, tier in _numeric_flags(old, new, h, year_delta):
            add(category, reason, h, tier)
        if h.i1 not in flagged_hunks:
            if not _editorial(old[h.i1 : h.i2], new[h.j1 : h.j2], force_same=old_force == new_force):
                add("wording", "content words substituted — not explained as an editorial or numeric change", h, NOTE)
    return flags


def _force_reason(before: list[str], after: list[str]) -> str:
    rank = {name: i for i, (name, _) in enumerate(_FORCE_TIERS)}
    if before and after:
        stronger = min(rank[a] for a in after) < min(rank[b] for b in before)
        direction = "strengthened" if stronger else "weakened"
        return f"direction {direction}: {'/'.join(before)} → {'/'.join(after)} language"
    if after:
        return f"{'/'.join(after)} language added — changes what the agency is told to do"
    return f"{'/'.join(before)} language removed — changes what the agency is told to do"


def _numeric_flags(old: list[str], new: list[str], h: _Hunk, year_delta: int = 1) -> list[tuple[str, str, int]]:
    o_nums = [(k, t) for k, t in enumerate(old[h.i1 : h.i2], h.i1) if _is_numeric(t)]
    n_nums = [(k, t) for k, t in enumerate(new[h.j1 : h.j2], h.j1) if _is_numeric(t)]
    if not o_nums and not n_nums:
        # A limit phrase can change with the figure untouched ("up to $20,000,000" → "$20,000,000").
        ow, nw = _window(old, h.i1, h.i2, 1), _window(new, h.j1, h.j2, 1)
        if _count(_LIMIT_PHRASE, ow) != _count(_LIMIT_PHRASE, nw):
            return [("limit", "floor/ceiling wording changed around a figure", REVIEW)]
        if _count(_DEADLINE_PHRASE, ow) != _count(_DEADLINE_PHRASE, nw) and _near_time(new, h.j1, h.j2):
            return [("deadline", "deadline wording changed", REVIEW)]
        return []

    out: list[tuple[str, str, int]] = []
    sides = [(old, k, t) for k, t in o_nums] + [(new, k, t) for k, t in n_nums]
    kinds = {_number_kind(tokens, k, t) for tokens, k, t in sides}
    ow, nw = _window(old, h.i1, h.i2, NUMBER_CONTEXT), _window(new, h.j1, h.j2, NUMBER_CONTEXT)
    limit_changed = _count(_LIMIT_PHRASE, ow) != _count(_LIMIT_PHRASE, nw)
    change = _change_text(o_nums, n_nums)

    if "deadline" in kinds:
        out.append(("deadline", f"deadline or time period changed{change}", REVIEW))
    if "share" in kinds:
        out.append(("share", f"percentage or cost share changed{change}", REVIEW))
    if "limit" in kinds or limit_changed:
        out.append(("limit", f"floor or ceiling changed{change}", REVIEW))
    elif "dollars" in kinds:
        out.append(("funding", f"dollar amount changed{change}", FUNDING_TIER))
    if "quantity" in kinds:
        out.append(("quantity", f"count or program limit changed{change}", REVIEW))
    old_years = [_number_value(t) for k, t in o_nums if _number_kind(old, k, t) in ("year", "date")]
    new_years = [_number_value(t) for k, t in n_nums if _number_kind(new, k, t) in ("year", "date")]
    shifted = [(a, b) for a, b in zip(old_years, new_years) if a is not None and b is not None and 1900 < a < 2100 and b - a not in (0, year_delta)]
    if shifted:
        a, b = shifted[0]
        out.append(("deadline", f"date moved by other than the {year_delta}-year report gap: {a:.0f} → {b:.0f}", REVIEW))
    return out


def _change_text(o_nums: list[tuple[int, str]], n_nums: list[tuple[int, str]]) -> str:
    if len(o_nums) == 1 and len(n_nums) == 1:
        return f": {_norm(o_nums[0][1])} → {_norm(n_nums[0][1])}"
    return ""


def _near_time(tokens: list[str], a: int, b: int) -> bool:
    return any(_TIME_UNIT.match(_norm(t)) for t in tokens[a : b + NUMBER_CONTEXT])


def _number_kind(tokens: list[str], k: int, tok: str) -> str:
    """deadline | share | limit | dollars | quantity | year | citation | date | other."""
    raw = _norm(tok)
    nxt = [_norm(t) for t in tokens[k + 1 : k + 3]]
    prev = _join([_norm(t) for t in tokens[max(0, k - NUMBER_CONTEXT) : k]])
    prev1 = _norm(tokens[k - 1]) if k > 0 else ""
    if _is_year(tok) and "$" not in tok:
        return "year"
    if _CITATION_BEFORE.search(prev) and not prev.endswith(("than", "to", "of")):
        return "citation"
    if _MONTH.match(prev1):
        return "date"
    if nxt and _TIME_UNIT.match(nxt[0]):
        return "deadline"
    if tok.endswith("%") or (nxt and _PERCENT.match(nxt[0])):
        return "share"
    if _LIMIT_PHRASE.search(prev):
        return "limit"
    if "$" in tok:
        return "dollars"
    if re.search(r"-", raw) or "." in raw and not raw.replace(".", "").isdigit():
        return "other"
    if nxt and re.fullmatch(r"[a-z][a-z-]+", nxt[0]) and nxt[0] not in _STOPWORDS:
        return "quantity"
    return "other"


_ACRONYM = re.compile(r"^\(?[A-Z][A-Za-z&-]*[A-Z](?:'s|’s)?\)?[.,;:]?$")


def _editorial(o: list[str], n: list[str], force_same: bool = False) -> bool:
    """True when a hunk's change reads as editorial: case, punctuation, hyphenation, plurals, stopwords, years, or acronym expansion."""
    squash = lambda toks: re.sub(r"[^a-z0-9]", "", " ".join(toks).lower())  # noqa: E731
    if squash(o) == squash(n):
        return True
    content = lambda toks: [  # noqa: E731
        _norm(t).rstrip("s") for t in toks if _norm(t) and _norm(t) not in _STOPWORDS and not _is_numeric(t)
    ]
    co, cn = content(o), content(n)
    if co == cn:
        return True
    if force_same:
        # Voice changes that keep the same force: "the Committee directs the Corps to" ↔ "the Corps is directed to".
        voice = lambda toks: [t for t in toks if t != "committee" and not any(p.search(t) for _, p in _FORCE_TIERS)]  # noqa: E731
        co, cn = voice(co), voice(cn)
        if co == cn:
            return True
    if not co and not cn:
        return True
    # Acronym swap: one side is a lone acronym (optionally parenthesized), the other a spelled-out name or nothing.
    for a, b in ((o, n), (n, o)):
        acr = [t for t in a if _norm(t) not in _STOPWORDS]
        if len(acr) == 1 and _ACRONYM.match(acr[0]):
            if not b or sum(1 for t in b if t[:1].isupper()) >= 1:
                return True
    return False


def describe_paragraph(text: str) -> list[str]:
    """Policy families present in a whole new or dropped paragraph, for tagging it."""
    low = text.lower()
    tags: list[str] = []
    if _count(_FAMILIES["prohibition"][0], low):
        tags.append("prohibition")
    if _count(_FORCE_TIERS[0][1], low):
        tags.append("mandatory direction")
    if _count(_FAMILIES["reporting"][0], low):
        tags.append("reporting requirement")
    tokens = text.split()
    if any(_is_numeric(t) and _number_kind(tokens, k, t) == "deadline" for k, t in enumerate(tokens)):
        tags.append("deadline")
    if _LIMIT_PHRASE.search(low) and "$" in text:
        tags.append("floor / ceiling")
    if _count(_FAMILIES["eligibility"][0], low) and re.search(r"\beligib|\bonly\b|limited to", low):
        tags.append("eligibility / scope")
    return tags


def max_tier(flags: list[PolicyFlag]) -> int:
    return max((f.tier for f in flags), default=0)
