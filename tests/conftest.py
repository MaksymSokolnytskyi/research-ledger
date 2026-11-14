from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from research_ledger.config import Vault, find_vault

DEMO = Path(__file__).resolve().parents[1] / "examples" / "demo-vault"


@pytest.fixture
def demo(tmp_path: Path) -> Vault:
    """A writable copy of the demo vault."""
    target = tmp_path / "demo"
    shutil.copytree(DEMO, target, ignore=shutil.ignore_patterns(".ledger", "_generated"))
    return find_vault(target)


def write(root: Path, rel: str, text: str) -> Path:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


@pytest.fixture
def blank(tmp_path: Path) -> Vault:
    (tmp_path / "ledger.toml").write_text('name = "t"\n', encoding="utf-8")
    return find_vault(tmp_path)
