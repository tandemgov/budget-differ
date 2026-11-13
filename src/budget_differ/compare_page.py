"""Assemble the in-browser comparison page (demo/compare/) from web/compare/.

Two parts:

- The page itself, rebuilt by `budget-differ demo` and committed: index.html (with its Content-Security-Policy), compare.js, compare.css, worker.js, lexicon.json, and app.zip (budget_differ's source plus web.py, built deterministically so rebuilds leave git clean).
- The runtime, fetched by `build(..., runtime=True)` and not committed (demo/compare/runtime/ is gitignored): Pyodide, the PyMuPDF WebAssembly wheel, and rapidfuzz's pure-Python modules, each pinned by SHA-256 and served from the site itself, so the page loads no third-party code.

The CSP allows only this site's own scripts, plus the inline scripts of the rendered result pages by hash; the hashes are computed here by rendering a sample comparison with the same code the page runs.
"""

from __future__ import annotations

import base64
import hashlib
import io
import re
import shutil
import sys
import tarfile
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WEB = ROOT / "web" / "compare"
SRC = ROOT / "src" / "budget_differ"

# (url, sha256, filename in runtime/)
PYODIDE = (
    "https://registry.npmjs.org/pyodide/-/pyodide-0.29.5.tgz",
    "6749b10ee515a1458ecea36d860c8ce2a48366e85b3f92d749ad1840e4aff181",
)
PYODIDE_FILES = ("pyodide.js", "pyodide.asm.js", "pyodide.asm.wasm", "python_stdlib.zip", "pyodide-lock.json")
PYMUPDF = (
    "https://files.pythonhosted.org/packages/58/8c/d897dcd32a25b58186c968b15ce4324ca029e9d96460de12325314e390be/"
    "pymupdf-1.28.2-cp313-abi3-pyemscripten_2025_0_wasm32.whl",
    "2e1b574c0fd2cb238021033fd3c0f9c4388816638df064e4bfb56d9d81736dc8",
)
RAPIDFUZZ = (
    "https://files.pythonhosted.org/packages/18/97/226c43b7b5d957bc3840ed52ea99eed261f99834c4619be7a4742cbaeafa/"
    "rapidfuzz-3.14.6.tar.gz",
    "e13a8160d017b499ec7a2fa9d0ce1ae2e7377080815785819f966fb235d4eb60",
)

_SAMPLE_OLD = """
                                TITLE I

                                 SENATE

                           Expense Allowances

    The Committee recommends $195,000 for expense allowances.
    Reporting.--The Committee directs the agency to report within 30 days.
"""
_SAMPLE_NEW = _SAMPLE_OLD.replace("30 days", "60 days").replace("$195,000", "$205,000")


def _zip(entries: list[tuple[str, bytes]], dest: Path) -> None:
    """A zip whose bytes depend only on its contents: sorted names, fixed timestamps and permissions, no compression (deflate output varies with the zlib build; Pages compresses in transit)."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_STORED) as zf:
        for name, data in sorted(entries):
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.external_attr = 0o644 << 16
            info.compress_type = zipfile.ZIP_STORED
            zf.writestr(info, data)
    dest.write_bytes(buf.getvalue())


def _inline_script_hashes() -> list[str]:
    """CSP hashes of every inline script in the result pages, from a sample comparison rendered by web.py itself."""
    sys.path.insert(0, str(WEB))
    try:
        import web  # type: ignore[import-not-found]
    finally:
        sys.path.pop(0)
    result = web.compare_texts(_SAMPLE_OLD, _SAMPLE_NEW, str(WEB / "lexicon.json"))
    scripts = {s for html in result["pages"].values() for s in re.findall(r"<script>(.*?)</script>", html, re.DOTALL)}
    return sorted("'sha256-" + base64.b64encode(hashlib.sha256(s.encode()).digest()).decode() + "'" for s in scripts)


def csp() -> str:
    return "; ".join(
        [
            "default-src 'none'",
            "script-src 'self' " + " ".join(_inline_script_hashes()),
            "worker-src 'self'",
            "connect-src 'self'",
            "style-src 'self' 'unsafe-inline'",
            "img-src 'self' data:",
            "font-src 'self'",
            "base-uri 'none'",
            "form-action 'none'",
        ]
    )


def build(out: Path, runtime: bool = False) -> None:
    out.mkdir(parents=True, exist_ok=True)
    page = (WEB / "index.html").read_text()
    page = page.replace("<!--CSP-->", f'<meta http-equiv="Content-Security-Policy" content="{csp()}">')
    (out / "index.html").write_text(page)
    for name in ("compare.js", "compare.css", "worker.js", "lexicon.json"):
        shutil.copyfile(WEB / name, out / name)
    entries = [(f"budget_differ/{p.relative_to(SRC).as_posix()}", p.read_bytes()) for p in SRC.rglob("*.py")]
    entries.append(("web.py", (WEB / "web.py").read_bytes()))
    _zip(entries, out / "app.zip")
    if runtime:
        fetch_runtime(out / "runtime")


def _download(url: str, sha256: str) -> bytes:
    with urllib.request.urlopen(url, timeout=120) as resp:
        data = resp.read()
    got = hashlib.sha256(data).hexdigest()
    if got != sha256:
        raise RuntimeError(f"{url}: SHA-256 {got} does not match the pinned {sha256}")
    return data


def fetch_runtime(dest: Path) -> None:
    """Download the pinned runtime into dest (verified by SHA-256) and write runtime.js naming the files for the worker."""
    dest.mkdir(parents=True, exist_ok=True)
    with tarfile.open(fileobj=io.BytesIO(_download(*PYODIDE)), mode="r:gz") as tf:
        for name in PYODIDE_FILES:
            member = tf.extractfile(f"package/{name}")
            assert member is not None, name
            (dest / name).write_bytes(member.read())
    wheel = PYMUPDF[0].rsplit("/", 1)[1]
    (dest / wheel).write_bytes(_download(*PYMUPDF))
    # rapidfuzz has no WebAssembly build; its sdist carries pure-Python versions of every function (the *_py modules), which it falls back to when the compiled ones are absent.
    entries = []
    with tarfile.open(fileobj=io.BytesIO(_download(*RAPIDFUZZ)), mode="r:gz") as tf:
        for member in tf.getmembers():
            m = re.match(r"rapidfuzz-[\d.]+/src/(rapidfuzz/.+\.py)$", member.name)
            if m and member.isfile():
                f = tf.extractfile(member)
                assert f is not None
                entries.append((m.group(1), f.read()))
    _zip(entries, dest / "rapidfuzz_py.zip")
    (dest / "runtime.js").write_text(
        f'// Generated by budget_differ.compare_page; names the pinned runtime files.\nconst RUNTIME = {{ pymupdf: "{wheel}", rapidfuzz: "rapidfuzz_py.zip" }};\n'
    )


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    runtime = "--runtime" in args
    args = [a for a in args if a != "--runtime"]
    out = Path(args[0]) if args else ROOT / "demo" / "compare"
    build(out, runtime=runtime)
    print(f"built {out}" + (" with runtime" if runtime else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
