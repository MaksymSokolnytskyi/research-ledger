"""Append-only records: what happened, kept apart from what is currently true.

Notes hold current truth and are edited freely. Records hold history and are **never
edited**: a correction is a new record that references the old one, so the reasoning
behind a mistake survives next to its fix.

* **One file per record, named so that two writers cannot collide**:
  ``<date>_<agent>_<kind>_<slug>_<hhmmss>.md``. There is no shared index to append
  to, so agents on two machines (or two parallel sessions) cannot corrupt each other.
* **Numbers carry their source or are refused**, because a sourceless number in a log
  is exactly what the log exists to prevent.
* :func:`check_integrity` asks git whether any record was modified after it was first
  committed.
"""

from __future__ import annotations

import re
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from research_ledger.config import Vault
from research_ledger.corpus import split_frontmatter

RecordKind = Literal[
    "run", "decision", "failure", "occurrence", "lesson", "note", "agent_call", "research"
]
SLUG_CHARS = r"a-z0-9а-яґєіїё\-"
_NAME_RE = re.compile(
    rf"^\d{{4}}-\d{{2}}-\d{{2}}_[\w\-]+_[a-z_]+_[{SLUG_CHARS}]+_\d{{6}}(?:-\d+)?\.md$"
)


class SourcedNumber(BaseModel):
    model_config = ConfigDict(frozen=True)

    value: float | int | str
    source: str = Field(min_length=1, description="Log, script, URL or record id.")


class Record(BaseModel):
    """One thing that happened."""

    model_config = ConfigDict(frozen=True)

    kind: RecordKind
    title: str = Field(min_length=1)
    body: str = ""
    agent: str = "main"
    when: datetime = Field(default_factory=lambda: datetime.now().astimezone())
    refs: tuple[str, ...] = Field(default=(), description="Ids of related records.")
    sources: tuple[str, ...] = Field(default=(), description="URLs or files relied on.")
    numbers: dict[str, SourcedNumber] = Field(default_factory=dict)
    extra: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _agent_is_a_filename_part(self) -> Record:
        if not re.fullmatch(r"[\w\-]+", self.agent):
            raise ValueError(f"agent {self.agent!r} must be letters, digits, _ or -")
        return self


def slug(text: str) -> str:
    """Filename fragment that still says what the record is (Cyrillic kept)."""
    return re.sub(rf"[^{SLUG_CHARS}]+", "-", text.lower()).strip("-")[:48] or "record"


def write_record(vault: Vault, record: Record) -> Path:
    """Write ``record`` as a new file and return its path. Never overwrites."""
    folder = vault.folder("records")
    folder.mkdir(parents=True, exist_ok=True)
    stem = (
        f"{record.when:%Y-%m-%d}_{record.agent}_{record.kind}_"
        f"{slug(record.title)}_{record.when:%H%M%S}"
    )
    path = folder / f"{stem}.md"
    n = 2
    while path.exists():
        path = folder / f"{stem}-{n}.md"
        n += 1
    header: dict[str, Any] = {
        "kind": record.kind,
        "agent": record.agent,
        "when": record.when.isoformat(timespec="microseconds"),
        "tier": 3,
    }
    if record.refs:
        header["refs"] = list(record.refs)
    if record.sources:
        header["sources"] = list(record.sources)
    if record.numbers:
        header["numbers"] = {k: v.model_dump() for k, v in record.numbers.items()}
    header.update(record.extra)
    text = (
        "---\n"
        + yaml.safe_dump(header, allow_unicode=True, sort_keys=False)
        + f"---\n\n# {record.title}\n\n{record.body.strip()}\n"
    )
    with open(path, "x", encoding="utf-8") as f:  # "x": fail rather than overwrite
        f.write(text)
    return path


class StoredRecord(BaseModel):
    """A record read back from disk."""

    model_config = ConfigDict(frozen=True)

    id: str
    path: Path
    header: dict[str, Any]
    title: str
    body: str

    @property
    def kind(self) -> str:
        return str(self.header.get("kind", ""))

    @property
    def when(self) -> str:
        return str(self.header.get("when", ""))


def read_records(vault: Vault, kind: str | None = None) -> list[StoredRecord]:
    folder = vault.folder("records")
    if not folder.is_dir():
        return []
    out: list[StoredRecord] = []
    for path in sorted(folder.glob("*.md")):
        header, body, _ = split_frontmatter(path.read_text(encoding="utf-8"))
        if kind is not None and header.get("kind") != kind:
            continue
        lines = body.strip().splitlines()
        title = lines[0][2:].strip() if lines and lines[0].startswith("# ") else path.stem
        out.append(
            StoredRecord(
                id=path.stem,
                path=path.relative_to(vault.root),
                header=header,
                title=title,
                body="\n".join(lines[1:]).strip(),
            )
        )
    return out


class IntegrityReport(BaseModel):
    model_config = ConfigDict(frozen=True)

    checked: int
    bad_names: tuple[str, ...]
    rewritten: tuple[str, ...]
    git_available: bool


def check_integrity(vault: Vault) -> IntegrityReport:
    """Records must follow the naming rule and must never be modified after commit."""
    folder = vault.folder("records")
    files = sorted(folder.glob("*.md")) if folder.is_dir() else []
    bad = tuple(p.name for p in files if not _NAME_RE.match(p.name))
    try:
        out = subprocess.run(
            [
                "git",
                "log",
                "--diff-filter=M",
                "--name-only",
                "--pretty=format:",
                "--",
                ".",
            ],
            cwd=folder if folder.is_dir() else vault.root,
            capture_output=True,
            text=True,
            timeout=30,
            encoding="utf-8",
        )
        git_ok = out.returncode == 0
        rewritten = (
            tuple(sorted({Path(line).name for line in out.stdout.splitlines() if line}))
            if git_ok
            else ()
        )
    except (OSError, subprocess.SubprocessError):
        git_ok, rewritten = False, ()
    return IntegrityReport(
        checked=len(files), bad_names=bad, rewritten=rewritten, git_available=git_ok
    )
