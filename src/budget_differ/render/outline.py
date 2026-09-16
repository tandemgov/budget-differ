"""Document order and the floating outline shared by the ranked and full-document pair pages."""

from __future__ import annotations

import html
from dataclasses import dataclass, field

from budget_differ.anchors import section_anchor
from budget_differ.models import PairDiff, ParagraphDiff, SectionDiff

_ROMAN = {"i", "ii", "iii", "iv", "v", "vi", "vii", "viii", "ix", "x"}
_SMALL_WORDS = {"a", "an", "and", "as", "at", "by", "for", "in", "of", "on", "or", "the", "to", "under", "with"}


def document_order(diff: PairDiff) -> list[SectionDiff]:
    """Sections as the newer report prints them, each dropped section placed right after the section that preceded it in the older report."""
    by_new = {id(sd.new): sd for sd in diff.sections if sd.new is not None}
    by_old = {id(sd.old): sd for sd in diff.sections if sd.old is not None}
    dropped_after: dict[int | None, list[SectionDiff]] = {}
    last: int | None = None
    for sec in diff.old_doc.sections:
        sd = by_old.get(id(sec))
        if sd is None:
            continue
        if sd.new is None:
            dropped_after.setdefault(last, []).append(sd)
        else:
            last = id(sd)
    out = list(dropped_after.get(None, []))
    for sec in diff.new_doc.sections:
        sd = by_new.get(id(sec))
        if sd is None:
            continue
        out.append(sd)
        out.extend(dropped_after.get(id(sd), []))
    # Anything the documents' section lists do not reach still gets a place.
    placed = {id(sd) for sd in out}
    out.extend(sd for sd in diff.sections if id(sd) not in placed)
    return out


def paragraph_order(sd: SectionDiff) -> list[ParagraphDiff]:
    """A matched section's paragraph diffs in the newer report's order, each removed paragraph right after the paragraph that preceded it."""
    assert sd.new is not None
    index = {id(p): i for i, p in enumerate(sd.new.paragraphs)}
    at: dict[int, ParagraphDiff] = {}
    removed_after: dict[int, list[ParagraphDiff]] = {}
    last = -1
    for pd in sd.paragraph_diffs:
        if pd.new is not None and id(pd.new) in index:
            last = index[id(pd.new)]
            at[last] = pd
        else:
            removed_after.setdefault(last, []).append(pd)
    out = list(removed_after.get(-1, []))
    for i in range(len(sd.new.paragraphs)):
        if i in at:
            out.append(at[i])
        out.extend(removed_after.get(i, []))
    return out


@dataclass
class OutlineNode:
    key: str  # normalized path component
    depth: int
    sd: SectionDiff | None = None
    children: list[OutlineNode] = field(default_factory=list)

    def first_sd(self) -> SectionDiff | None:
        if self.sd is not None:
            return self.sd
        for child in self.children:
            found = child.first_sd()
            if found is not None:
                return found
        return None


def build_outline(ordered: list[SectionDiff]) -> list[OutlineNode]:
    """Nest sections by path, reusing a parent only while it is the latest sibling so interrupted headings keep document order."""
    root = OutlineNode(key="", depth=-1)
    for sd in ordered:
        path = sd.display_path
        parent = root
        for depth, comp in enumerate(path):
            leaf = depth == len(path) - 1
            last = parent.children[-1] if parent.children else None
            if last is not None and last.key == comp and not (leaf and last.sd is not None):
                node = last
            else:
                node = OutlineNode(key=comp, depth=depth)
                parent.children.append(node)
            parent = node
        parent.sd = sd
    return root.children


def display_heading(text: str) -> str:
    """Title-case an all-caps heading for the outline and breadcrumbs; mixed-case headings are left as printed."""
    if any(c.islower() for c in text):
        return text
    words = text.lower().split()
    out = []
    for i, w in enumerate(words):
        if i and w in _SMALL_WORDS:
            out.append(w)
        elif w in _ROMAN:
            out.append(w.upper())
        else:
            out.append(w[:1].upper() + w[1:])
    return " ".join(out)


def _node_label(node: OutlineNode) -> str:
    if node.sd is not None:
        sec = node.sd.new or node.sd.old
        assert sec is not None
        return display_heading(sec.heading)
    return display_heading(node.key)


def render_outline(diff: PairDiff) -> str:
    """Collapsible outline of the report, each entry marked by its change class and linked to the section's anchor on the current page."""
    nodes = build_outline(document_order(diff))
    out = [
        '<div class="outline">',
        '<input type="checkbox" id="oltoggle" class="oltoggle-box">',
        '<label for="oltoggle" class="olhead">Outline</label>',
        '<div class="olbody"><div class="olactions">'
        '<button type="button" data-ol="expand">expand all</button>'
        '<button type="button" data-ol="collapse">collapse</button></div>',
    ]
    out.append(_render_nodes(nodes))
    out.append("</div></div>")
    return "".join(out)


def _render_nodes(nodes: list[OutlineNode]) -> str:
    items: list[str] = []
    for node in nodes:
        target = node.first_sd()
        anchor = (target.anchor or section_anchor(target.display_path)) if target else ""
        label = html.escape(_node_label(node), quote=True)
        change = node.sd.change.label.replace(" ", "-") if node.sd is not None else "none"
        cls = ["oli"]
        if node.children:
            cls.append("has-kids")
            if node.depth == 0:
                cls.append("open")
        caret = '<button type="button" class="olcaret" aria-label="toggle"></button>' if node.children else ""
        link_cls = "oll own" if node.sd is not None else "oll"
        items.append(
            f'<li class="{" ".join(cls)}" data-oc="{change}">{caret}'
            f'<a class="{link_cls}" href="#{anchor}" title="{label}">{label}</a>'
            + (_render_nodes(node.children) if node.children else "")
            + "</li>"
        )
    return f'<ul class="ol">{"".join(items)}</ul>'
