"""Numbers with nothing behind them.

Rule: a number must be reproducible, and a number whose origin is not written down
cannot be reproduced without archaeology. A number counts as *sourced* when its
paragraph or table row points at something that can be checked:

* a link (wiki or Markdown) to a record, a run log, a script or a source note,
* an external URL,
* a footnote reference ``[^n]``,
* the note's own ``runs:`` or ``sources:`` frontmatter (or a record's ``numbers:``
  map), which declares where all of its numbers come from.

Which numbers are counted: decimals, percentages, and integers of three or more
digits. Years, dates, versions, list ordinals and heading numbers are skipped, since
they are labels rather than results. This is a heuristic and is meant to be read as a
trend under the ratchet, not as a verdict on a single number.
"""

from __future__ import annotations

import re
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from research_ledger.corpus import Corpus, Note

_NUMBER_RE = re.compile(
    r"(?<![\w.\-/])(?:\d+[.,]\d+|\d{3,})(?:\s?%)?(?![\w./\-])|\b\d+\s?%"
)
_SKIP_RE = re.compile(
    r"\b(?:19|20)\d{2}-\d{2}-\d{2}\b"  # dates
    r"|\bv?\d+\.\d+\.\d+\b"  # versions
    r"|(?<!\d)(?:19|20)\d{2}(?!\d)"  # years
)
_SOURCE_RE = re.compile(
    r"\[\[[^\]]+\]\]|\[[^\]]*\]\([^)]+\)|https?://\S+|\[\^[^\]]+\]", re.IGNORECASE
)
_LIST_ORDINAL_RE = re.compile(r"^\s*\d+[.)]\s")
_HEADING_RE = re.compile(r"^\s*#")


class UnsourcedNumber(BaseModel):
    model_config = ConfigDict(frozen=True)

    path: Path
    line: int
    number: str
    context: str


class ProvenanceReport(BaseModel):
    model_config = ConfigDict(frozen=True)

    numbers_total: int
    numbers_sourced: int
    unsourced: tuple[UnsourcedNumber, ...]
    words: int

    @property
    def unsourced_per_1k_words(self) -> float:
        return round(len(self.unsourced) / self.words * 1000, 2) if self.words else 0.0


def _blocks(prose: str) -> list[tuple[int, list[str]]]:
    """Paragraphs and table rows, each with its starting line number (1-based).

    A table row is its own block: a link in one row does not source the next one.
    """
    blocks: list[tuple[int, list[str]]] = []
    current: list[str] = []
    start = 1
    for i, line in enumerate(prose.splitlines(), start=1):
        if line.lstrip().startswith("|"):
            if current:
                blocks.append((start, current))
                current = []
            blocks.append((i, [line]))
        elif line.strip():
            if not current:
                start = i
            current.append(line)
        elif current:
            blocks.append((start, current))
            current = []
    if current:
        blocks.append((start, current))
    return blocks


def numbers_in(line: str) -> list[str]:
    if _HEADING_RE.match(line):
        return []
    cleaned = _SKIP_RE.sub(" ", _LIST_ORDINAL_RE.sub(" ", line))
    return [m.group().strip() for m in _NUMBER_RE.finditer(cleaned)]


def note_provenance(note: Note) -> tuple[int, list[UnsourcedNumber]]:
    extra = note.frontmatter.model_extra or {}
    declared = bool(
        note.frontmatter.runs or note.frontmatter.sources or extra.get("numbers")
    )
    total = 0
    unsourced: list[UnsourcedNumber] = []
    for start, lines in _blocks(note.prose):
        sourced = declared or bool(_SOURCE_RE.search(" ".join(lines)))
        for offset, line in enumerate(lines):
            for number in numbers_in(line):
                total += 1
                if not sourced:
                    unsourced.append(
                        UnsourcedNumber(
                            path=note.path,
                            line=start + offset,
                            number=number,
                            context=line.strip()[:160],
                        )
                    )
    return total, unsourced


def provenance(corpus: Corpus) -> ProvenanceReport:
    total = 0
    unsourced: list[UnsourcedNumber] = []
    words = 0
    for note in corpus.notes:
        if note.generated:
            continue
        n, missing = note_provenance(note)
        total += n
        unsourced.extend(missing)
        words += note.words
    return ProvenanceReport(
        numbers_total=total,
        numbers_sourced=total - len(unsourced),
        unsourced=tuple(unsourced),
        words=words,
    )
