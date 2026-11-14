"""Reading a vault: notes, frontmatter and links, with Obsidian's resolution rules.

Single source of truth for "what is a note", "what is a link" and "which note does a
link point to". Every check builds on :func:`load_corpus`, so two checks can never
disagree about the graph they are looking at.
"""

from __future__ import annotations

import fnmatch
import re
from datetime import date
from functools import cached_property
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from research_ledger.config import Vault

Lifecycle = Literal["living", "snapshot", "closed"]

_FRONTMATTER_RE = re.compile(r"\A---\s*\n(.*?)\n---\s*(?:\n|\Z)", re.DOTALL)
_FENCE_RE = re.compile(r"^(```|~~~).*?^\1", re.DOTALL | re.MULTILINE)
_INLINE_CODE_RE = re.compile(r"`[^`\n]*`")
_MATH_BLOCK_RE = re.compile(r"\$\$.*?\$\$", re.DOTALL)
_WIKILINK_RE = re.compile(r"!?\[\[([^\]|#^]*)(?:[#^][^\]|]*)?(?:\|([^\]]*))?\]\]")
_MDLINK_RE = re.compile(r"!?\[([^\]]*)\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
_WORD_RE = re.compile(r"[^\W_]+", re.UNICODE)


class Frontmatter(BaseModel):
    """Fields the ledger understands. Unknown keys are kept in ``extra``.

    Every field is optional: a note without a header is still a note, and the
    lifecycle check is what reports the missing declaration.
    """

    model_config = ConfigDict(frozen=True, extra="allow")

    tier: int | None = Field(default=None, ge=0, le=3)
    lifecycle: Lifecycle | None = None
    expires_when: str | None = None
    last_verified: date | None = None
    generated: bool = False
    aliases: tuple[str, ...] = ()
    checks: tuple[str, ...] = Field(
        default=(), description="Test ids that witness this note's claims about code."
    )
    runs: tuple[str, ...] = Field(
        default=(), description="Records or logs this note's numbers come from."
    )
    sources: tuple[str, ...] = Field(default=(), description="External URLs relied on.")

    @field_validator("aliases", "checks", "runs", "sources", mode="before")
    @classmethod
    def _listify(cls, value: Any) -> Any:
        if value is None:
            return ()
        if isinstance(value, str):
            return (value,)
        return value


class Link(BaseModel):
    model_config = ConfigDict(frozen=True)

    target: str = Field(description="Raw target as written, without heading or alias.")
    shown: str
    kind: Literal["wiki", "markdown"]
    embed: bool = False


class Note(BaseModel):
    """One Markdown file in the vault."""

    model_config = ConfigDict(frozen=True)

    path: Path = Field(description="Relative to the vault root.")
    frontmatter: Frontmatter
    frontmatter_error: str | None = None
    body: str
    links: tuple[Link, ...]

    @property
    def stem(self) -> str:
        return self.path.stem

    @property
    def title(self) -> str:
        for line in self.body.splitlines():
            if line.startswith("# "):
                return line[2:].strip()
        return self.stem

    @property
    def prose(self) -> str:
        """Body with code and display math removed: what checks of the text read."""
        return strip_code(self.body)

    @property
    def words(self) -> int:
        return len(_WORD_RE.findall(self.prose))

    @property
    def generated(self) -> bool:
        return self.frontmatter.generated


def _blank(match: re.Match[str]) -> str:
    return "\n" * match.group().count("\n")


def strip_blocks(text: str) -> str:
    """Remove fenced code and display math, keeping line structure and inline code."""
    return _MATH_BLOCK_RE.sub(_blank, _FENCE_RE.sub(_blank, text))


def strip_code(text: str) -> str:
    """Remove fenced blocks, display math and inline code, keeping line structure."""
    return _INLINE_CODE_RE.sub(" ", strip_blocks(text))


def split_frontmatter(text: str) -> tuple[dict[str, Any], str, str | None]:
    """Return ``(fields, body, error)``. Broken YAML is reported, not fatal."""
    match = _FRONTMATTER_RE.match(text)
    if not match:
        return {}, text, None
    body = text[match.end() :]
    try:
        data = yaml.safe_load(match.group(1)) or {}
    except yaml.YAMLError as exc:
        return {}, body, f"invalid YAML: {exc}".splitlines()[0]
    if not isinstance(data, dict):
        return {}, body, "frontmatter is not a mapping"
    return data, body, None


def parse_links(body: str) -> tuple[Link, ...]:
    """Wiki and Markdown links outside code. External URLs are not links between notes."""
    text = strip_code(body)
    links: list[Link] = []
    for m in _WIKILINK_RE.finditer(text):
        target = m.group(1).strip()
        if target:
            links.append(
                Link(
                    target=target,
                    shown=(m.group(2) or target).strip(),
                    kind="wiki",
                    embed=m.group().startswith("!"),
                )
            )
    for m in _MDLINK_RE.finditer(text):
        target = m.group(2).split("#")[0]
        if not target or re.match(r"^[a-z][a-z0-9+.-]*:", target, re.IGNORECASE):
            continue
        links.append(
            Link(
                target=target.replace("%20", " "),
                shown=m.group(1),
                kind="markdown",
                embed=m.group().startswith("!"),
            )
        )
    return tuple(links)


def _matches(path: str, patterns: tuple[str, ...]) -> bool:
    return any(
        fnmatch.fnmatch(path, p) or fnmatch.fnmatch("/" + path, "*/" + p)
        for p in patterns
    )


def iter_note_paths(vault: Vault) -> list[Path]:
    cfg = vault.config
    found: set[Path] = set()
    for pattern in cfg.include:
        for path in vault.root.glob(pattern):
            rel = path.relative_to(vault.root)
            if path.is_file() and not _matches(rel.as_posix(), cfg.exclude):
                found.add(rel)
    return sorted(found)


def read_note(vault: Vault, rel: Path) -> Note:
    text = (vault.root / rel).read_text(encoding="utf-8", errors="replace")
    data, body, error = split_frontmatter(text)
    try:
        frontmatter = Frontmatter.model_validate(data)
    except ValidationError as exc:
        frontmatter, error = Frontmatter(), f"invalid field: {exc.errors()[0]['loc']}"
    return Note(
        path=rel,
        frontmatter=frontmatter,
        frontmatter_error=error,
        body=body,
        links=parse_links(body),
    )


class Corpus(BaseModel):
    """All notes of a vault plus Obsidian-style link resolution."""

    model_config = ConfigDict(frozen=True)

    vault: Vault
    notes: tuple[Note, ...]

    def by_path(self) -> dict[Path, Note]:
        return {n.path: n for n in self.notes}

    @cached_property
    def name_index(self) -> dict[str, list[Note]]:
        """Lower-cased stem, alias and vault-relative path (no suffix) -> notes."""
        index: dict[str, list[Note]] = {}
        for note in self.notes:
            keys = {
                note.stem.lower(),
                note.path.with_suffix("").as_posix().lower(),
                *(a.lower() for a in note.frontmatter.aliases),
            }
            for key in keys:
                index.setdefault(key, []).append(note)
        return index

    def resolve(self, source: Note, link: Link) -> Note | None:
        """The note a link points to, or None if it dangles.

        Wiki links resolve by name like Obsidian (shortest path wins on ties);
        Markdown links resolve relative to the linking note.
        """
        if link.kind == "markdown":
            target = (source.path.parent / link.target).as_posix()
            parts: list[str] = []
            for part in target.split("/"):
                if part == "..":
                    if parts:
                        parts.pop()
                elif part not in ("", "."):
                    parts.append(part)
            key = "/".join(parts)
            key = key[:-3] if key.lower().endswith(".md") else key
            candidates = self.name_index.get(key.lower(), [])
        else:
            key = link.target[:-3] if link.target.lower().endswith(".md") else link.target
            candidates = self.name_index.get(key.lower(), [])
        if not candidates:
            return None
        return min(candidates, key=lambda n: (len(n.path.parts), n.path.as_posix()))

    def is_attachment(self, link: Link) -> bool:
        """Links to images, PDFs or HTML are attachments, not notes."""
        suffix = Path(link.target).suffix.lower()
        return bool(suffix) and suffix != ".md"


def load_corpus(vault: Vault) -> Corpus:
    notes = tuple(read_note(vault, rel) for rel in iter_note_paths(vault))
    return Corpus(vault=vault, notes=notes)
