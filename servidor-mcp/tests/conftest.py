from __future__ import annotations

import os
import secrets
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = REPO_ROOT / "dados"

os.environ.setdefault("REQUEST_STATE_SECRET", secrets.token_hex(32))
os.environ.setdefault("DATA_DIR", str(DATA_DIR))


@pytest.fixture
def data_dir() -> Path:
    return DATA_DIR
