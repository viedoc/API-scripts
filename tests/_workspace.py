from __future__ import annotations

import shutil
import uuid
from contextlib import contextmanager
from pathlib import Path

from tests._loader import REPO_ROOT


@contextmanager
def workspace_tempdir(prefix: str):
    root = REPO_ROOT / "test_tmp"
    root.mkdir(exist_ok=True)
    path = root / f"{prefix}_{uuid.uuid4().hex}"
    path.mkdir()
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)
