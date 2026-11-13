"""Check `budget-differ ingest` against GovInfo: convert a document's GovInfo PDF and compare the result with GovInfo's own .htm of the same document.

Three measures:

- prose (catalog reports only): the share of the words the pipeline actually diffs (paragraph text after segmentation, tables and front and back matter dropped) that the converted render reproduces, in order. This is the number that matters for comparisons.
- words: the share of GovInfo's words that the converted text reproduces, in order (difflib over word sequences; dot leaders ignored). This is the conversion's fidelity, independent of segmentation.
- sections (catalog reports only): both renders segmented and diffed. GovInfo's .htm has its own quirks (table titles read as headings, dash lists split per line), so this measures how differently the two renders segment, not which is right; prerelease comparisons convert both years for that reason (see chain.build_chain).

    uv run python scripts/ingest_check.py CRPT-119srpt38 CRPT-118srpt192     # catalog reports
    uv run python scripts/ingest_check.py --pair BILL.htm BILL.pdf            # any GovInfo .htm/.pdf pair, e.g. a reported bill
    add --show N to print the first N word-level differences
"""

from __future__ import annotations

import difflib
import re
import sys
from dataclasses import replace
from pathlib import Path

from budget_differ.compare import compare_documents, load_document
from budget_differ.config import approps_repo
from budget_differ.corpus import load_catalog, pdf_path, raw_path
from budget_differ.ingest import pdf_to_gpo_text
from budget_differ.segment.preprocess import extract_pre_text


def _words(text: str) -> list[str]:
    text = re.sub(r"-\s*\n\s*", "-", text).lower().replace("--", " ")
    return [w.rstrip(".") for w in re.findall(r"[a-z0-9$][\w$,.'%-]*", text) if w.rstrip(".")]


def word_agreement(htm: Path, pdf: Path, show: int = 0) -> float:
    gov = _words(extract_pre_text(htm.read_text(errors="replace")))
    conv = _words(pdf_to_gpo_text(pdf))
    sm = difflib.SequenceMatcher(None, gov, conv, autojunk=False)
    share = sum(b.size for b in sm.get_matching_blocks()) / max(1, len(gov))
    print(f"{pdf.stem}: words {share:.2%} of {len(gov)} GovInfo words reproduced in order ({len(conv)} converted)")
    shown = 0
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag != "equal" and shown < show:
            print(f"    {tag}: {' '.join(gov[i1:i2])[:70]!r} -> {' '.join(conv[j1:j2])[:70]!r}")
            shown += 1
    return share


def section_agreement(package_id: str) -> None:
    repo = approps_repo()
    entry = next(e for e in load_catalog(repo) if e.package_id == package_id)
    gov = load_document(repo, entry)
    conv = load_document(repo, replace(entry, from_pdf=True))
    g = [w for s in gov.sections for p in s.paragraphs for w in _words(p.text)]
    c = [w for s in conv.sections for p in s.paragraphs for w in _words(p.text)]
    sm = difflib.SequenceMatcher(None, g, c, autojunk=False)
    share = sum(b.size for b in sm.get_matching_blocks()) / max(1, len(g))
    print(f"{package_id}: prose {share:.2%} of {len(g)} diffed GovInfo words reproduced in order ({len(c)} converted)")
    counts = compare_documents(gov, conv).counts()
    total = sum(counts.values())
    print(f"{package_id}: sections {counts.get('unchanged', 0)}/{total} unchanged between renders; "
          f"{len(gov.sections)} GovInfo vs {len(conv.sections)} converted sections; {counts}")


def main(argv: list[str]) -> int:
    show = 0
    if "--show" in argv:
        i = argv.index("--show")
        show = int(argv[i + 1])
        del argv[i : i + 2]
    if argv[:1] == ["--pair"]:
        word_agreement(Path(argv[1]), Path(argv[2]), show)
        return 0
    repo = approps_repo()
    by_id = {e.package_id: e for e in load_catalog(repo)}
    for package_id in argv or ["CRPT-119srpt38"]:
        entry = by_id[package_id]
        if not pdf_path(repo, entry).exists():
            print(f"{package_id}: no PDF at {pdf_path(repo, entry)}", file=sys.stderr)
            return 1
        word_agreement(raw_path(repo, entry), pdf_path(repo, entry), show)
        section_agreement(package_id)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
