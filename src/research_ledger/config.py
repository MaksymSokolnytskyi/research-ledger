"""Vault configuration, read from ``ledger.toml`` at the vault root.

Single source of truth for every path, threshold and switch the tools use. Nothing in
the package hard-codes a folder name: the original tooling had the vault path written
into 25 of 32 scripts, which is why it could not leave its first project.

The file is optional. A folder without ``ledger.toml`` gets the defaults below, so the
tools can be pointed at any existing Markdown folder before anyone commits to them.
"""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

CONFIG_NAME = "ledger.toml"
STATE_DIR = ".ledger"

Language = Literal["en", "uk"]


class Folders(BaseModel):
    """Vault-relative folders with a fixed meaning."""

    model_config = ConfigDict(frozen=True)

    definitions: str = Field(default="def", description="One note per defined entity.")
    atlas: str = Field(default="atlas", description="Generated entity pages.")
    tasks: str = "tasks"
    records: str = Field(default="logs", description="Append-only records.")
    registry: str = Field(
        default="registry", description="Claims, failures, predictions."
    )
    generated: str = Field(default="_generated", description="Other generated pages.")
    archive: str = "archive"


class Capture(BaseModel):
    """Automatic failure capture from Claude Code hooks."""

    model_config = ConfigDict(frozen=True)

    enabled: bool = True
    redact: bool = Field(
        default=True, description="Mask secrets before anything is written."
    )
    extra_secret_patterns: tuple[str, ...] = Field(
        default=(), description="Additional regexes whose matches are masked."
    )
    max_output_chars: int = Field(default=4000, ge=200)


class Context(BaseModel):
    """Task-context packs assembled for agents."""

    model_config = ConfigDict(frozen=True)

    budget_tokens: int = Field(default=3000, ge=200)
    min_score: float = Field(
        default=1.5, ge=0, description="Below this BM25 score a note is not relevant."
    )
    inject_on_prompt: bool = Field(
        default=True,
        description="Add a context pack to Claude Code prompts when relevant.",
    )


class Ratchet(BaseModel):
    """Guarded metrics: may not get worse between audits."""

    model_config = ConfigDict(frozen=True)

    guarded: tuple[str, ...] = (
        "dangling_links",
        "orphans",
        "numbers_unsourced_per_1k_words",
        "lifecycle_missing",
        "repeat_failure_rate",
    )


class LedgerConfig(BaseModel):
    """Everything the tools need to know about one vault."""

    model_config = ConfigDict(frozen=True)

    name: str = "research-ledger"
    language: Language = "en"
    include: tuple[str, ...] = ("**/*.md",)
    exclude: tuple[str, ...] = (
        ".obsidian/**",
        "templates/**",
        ".ledger/**",
        ".git/**",
        "node_modules/**",
        ".venv/**",
        "**/__pycache__/**",
    )
    entry_points: tuple[str, ...] = Field(
        default=("_home", "README", "index"),
        description="Notes nobody needs to link to (they are where reading starts).",
    )
    agents: tuple[str, ...] = Field(
        default=("main",), description="Callsigns of agents or stations writing records."
    )
    folders: Folders = Folders()
    capture: Capture = Capture()
    context: Context = Context()
    ratchet: Ratchet = Ratchet()
    stale_after_days: int = Field(default=30, ge=1)


class Vault(BaseModel):
    """A vault root together with its configuration."""

    model_config = ConfigDict(frozen=True)

    root: Path
    config: LedgerConfig

    @property
    def state_dir(self) -> Path:
        """Machine state (ratchet history, caches). Not notes; safe to git-ignore."""
        return self.root / STATE_DIR

    def folder(self, name: str) -> Path:
        return self.root / getattr(self.config.folders, name)


def load_config(path: Path) -> LedgerConfig:
    with open(path, "rb") as f:
        return LedgerConfig.model_validate(tomllib.load(f))


def find_vault(start: Path | None = None) -> Vault:
    """Walk up from ``start`` to the nearest folder holding ``ledger.toml``.

    Falls back to ``start`` itself with default settings, so a bare folder of notes
    works without setup.
    """
    start = (start or Path.cwd()).resolve()
    for folder in (start, *start.parents):
        candidate = folder / CONFIG_NAME
        if candidate.is_file():
            return Vault(root=folder, config=load_config(candidate))
    return Vault(root=start, config=LedgerConfig())
