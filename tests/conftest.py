from __future__ import annotations

import shutil
import uuid
from pathlib import Path

import pytest


@pytest.fixture
def workspace_tmp_path() -> Path:
    root = Path("tmp_runtime_logs") / "pytest"
    root.mkdir(parents=True, exist_ok=True)
    path = root / f"pytest_{uuid.uuid4().hex}"
    path.mkdir(parents=True, exist_ok=False)
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)
