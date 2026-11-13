"""The in-browser comparison page: committed files match the source, its CSP covers the result pages' scripts, links stay http(s)."""

from __future__ import annotations

import base64
import hashlib
import re
import zipfile
from pathlib import Path

import pytest

from budget_differ.compare_page import SRC, WEB, _SAMPLE_NEW, _SAMPLE_OLD
from budget_differ.corpus import CatalogEntry
from budget_differ.render.html import _pdf_url, _source_links

PAGE = Path(__file__).resolve().parents[1] / "demo" / "compare"
pytestmark = pytest.mark.skipif(not (PAGE / "index.html").exists(), reason="demo/compare not built")


def _csp() -> str:
    m = re.search(r'http-equiv="Content-Security-Policy" content="([^"]+)"', (PAGE / "index.html").read_text())
    assert m, "index.html has no Content-Security-Policy"
    return m.group(1)


def test_csp_allows_only_this_site_and_hashed_inline_scripts():
    csp = _csp()
    script_src = next(d for d in csp.split("; ") if d.startswith("script-src "))
    assert "'unsafe-inline'" not in script_src and "'unsafe-eval'" not in script_src
    assert "http" not in csp
    assert "default-src 'none'" in csp


def test_csp_covers_every_inline_script_in_result_pages():
    """Fails when the renderer's scripts change without `budget-differ demo` being rerun: the page would block them."""
    import sys

    sys.path.insert(0, str(WEB))
    try:
        import web  # type: ignore[import-not-found]
    finally:
        sys.path.pop(0)
    pages = web.compare_texts(_SAMPLE_OLD, _SAMPLE_NEW, str(WEB / "lexicon.json"))["pages"]
    csp = _csp()
    for html in pages.values():
        for script in re.findall(r"<script>(.*?)</script>", html, re.DOTALL):
            digest = base64.b64encode(hashlib.sha256(script.encode()).digest()).decode()
            assert f"'sha256-{digest}'" in csp


def test_committed_app_zip_matches_source():
    with zipfile.ZipFile(PAGE / "app.zip") as zf:
        names = set(zf.namelist())
        for path in SRC.rglob("*.py"):
            name = f"budget_differ/{path.relative_to(SRC).as_posix()}"
            assert name in names, f"{name} missing from app.zip; rerun `uv run budget-differ demo`"
            assert zf.read(name) == path.read_bytes(), f"{name} is stale in app.zip; rerun `uv run budget-differ demo`"
        assert zf.read("web.py") == (WEB / "web.py").read_bytes()


def test_committed_page_files_match_source():
    for name in ("compare.js", "compare.css", "worker.js", "lexicon.json"):
        assert (PAGE / name).read_bytes() == (WEB / name).read_bytes(), f"{name} is stale; rerun `uv run budget-differ demo`"


def _entry(**kw) -> CatalogEntry:
    return CatalogEntry(**{"package_id": "X", "congress": 119, "chamber": "senate", "subcommittee": "Legislative-Branch",
                           "fiscal_year": 2027, "stage": "committee", "title": "", "html_url": "", **kw})


@pytest.mark.parametrize("url", ["javascript:alert(1)", "data:text/html,<b>x</b>", "JaVaScRiPt:alert(1)", "/etc/passwd"])
def test_only_http_links_are_rendered(url):
    entry = _entry(pdf_url=url, html_url=url)
    assert _pdf_url(entry) == ""
    assert url not in _source_links(entry)


def test_local_document_without_url_has_no_pdf_link():
    entry = _entry(local_path="x.htm", source="dropped in")
    assert _pdf_url(entry) == ""
    assert "href" not in _source_links(entry)
    assert _pdf_url(_entry()).startswith("https://www.govinfo.gov/")
