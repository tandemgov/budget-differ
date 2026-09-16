"""The checked-in demonstration site must be internally navigable: every relative link and fragment resolves."""

import html
import json
import re
from pathlib import Path
from urllib.parse import unquote, urlsplit

import pytest

DEMO = Path(__file__).resolve().parents[1] / "demo"

pytestmark = pytest.mark.skipif(not (DEMO / "index.html").exists(), reason="demo/ not built")


def test_every_internal_link_resolves():
    pages = list(DEMO.rglob("*.html"))
    ids = {p.resolve(): set(re.findall(r'id="([^"]+)"', p.read_text())) for p in pages}
    broken = []
    for page in pages:
        for href in re.findall(r'href="([^"]+)"', page.read_text()):
            href = html.unescape(href)
            if href.startswith(("http:", "https:", "mailto:")):
                continue
            parts = urlsplit(href)
            target = (page.parent / unquote(parts.path)).resolve() if parts.path else page.resolve()
            if parts.path.endswith(".css"):
                ok = target.exists()
            else:
                ok = target in ids and (not parts.fragment or parts.fragment in ids[target])
            if not ok:
                broken.append((str(page.relative_to(DEMO)), href))
    assert not broken, broken[:10]


def test_manifest_covers_two_subcommittees_three_years():
    manifest = json.loads((DEMO / "manifest.json").read_text())
    assert len(manifest["comparisons"]) == 4
    assert len(manifest["reports"]) == 6
    assert {r["subcommittee"] for r in manifest["reports"].values()} == {"Energy-Water", "Legislative-Branch"}
    for c in manifest["comparisons"]:
        assert (DEMO / c["page"]).exists()
