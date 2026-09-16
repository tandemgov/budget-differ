"""Locate the sibling appropriations-committee-reports repo and its data artifacts."""

from __future__ import annotations

import os
from pathlib import Path

ENV_VAR = "BUDGET_DIFFER_APPROPS_REPO"
DEFAULT_RELATIVE = "../appropriations-committee-reports"


def approps_repo() -> Path:
    """Resolve the approps repo path: env var, then ../appropriations-committee-reports."""
    candidate = Path(os.environ.get(ENV_VAR, DEFAULT_RELATIVE)).expanduser().resolve()
    catalog = candidate / "data" / "reference" / "report_catalog.json"
    if not catalog.exists():
        raise FileNotFoundError(
            f"approps repo not found at {candidate} (no {catalog}). "
            f"Set {ENV_VAR} to the appropriations-committee-reports checkout."
        )
    return candidate


def catalog_path(repo: Path) -> Path:
    return repo / "data" / "reference" / "report_catalog.json"


def raw_dir(repo: Path) -> Path:
    return repo / "data" / "raw"


def pdfhier_cache_dir() -> Path:
    """Where extracted PDF heading tiers are cached (JSON per package)."""
    default = Path(__file__).resolve().parents[2] / ".pdfhier-cache"
    return Path(os.environ.get("BUDGET_DIFFER_PDFHIER_CACHE", default))
