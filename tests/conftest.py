import os
from pathlib import Path

import pytest

from budget_differ.config import ENV_VAR


def approps_repo_or_none() -> Path | None:
    candidate = Path(os.environ.get(ENV_VAR, "../appropriations-committee-reports")).resolve()
    if (candidate / "data" / "reference" / "report_catalog.json").exists():
        return candidate
    return None


requires_corpus = pytest.mark.skipif(
    approps_repo_or_none() is None,
    reason=f"approps corpus not found (set {ENV_VAR})",
)
