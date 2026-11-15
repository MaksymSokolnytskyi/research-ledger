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
_WIKI_ALIAS_RE = re.compile(r"\[\[[^\]|]*\|([^\]]*)\]\]")
_WIKI_RE = re.compile(r"\[\[([^\]]*)\]\]")
_MD_LINK_RE = re.compile(r"\[([^\]]*)\]\([^)]*\)")
_MARKUP_RE = re.compile(r"[`*_~]")
_WORD_RE = re.compile(r"[^\W_]+(?:[.,]\d+)?%?")
ANCHOR_WORDS = 3  # words kept on each side of a number in its identity
_HEADING_RE = re.compile(r"^\s*#")


class UnsourcedNumber(BaseModel):
    model_config = ConfigDict(frozen=True)

    path: Path
    line: int
    number: str
    context: str
    anchor: str = ""  # markup- and wrap-independent identity; see ``_anchors``


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


def _plain(text: str) -> str:
    """Prose without link syntax, emphasis or line breaks: what a reader sees."""
    text = _WIKI_ALIAS_RE.sub(r"\1", text)
    text = _WIKI_RE.sub(r"\1", text)
    text = _MD_LINK_RE.sub(r"\1", text)
    return " ".join(_MARKUP_RE.sub("", text).lower().split())


def _is_number(word: str) -> bool:
    return word.rstrip("%").replace(",", "").replace(".", "").isdigit()


def _anchors(block: str, numbers: list[str]) -> list[str]:
    """Identity of each number by the words around it, in reading order.

    An issue's identity must survive edits that do not touch the number: re-wrapping
    a paragraph, linking a nearby word, adding emphasis. The line text (the old key)
    changes under all three, so an untouched number looked new after every such
    edit. The anchor is ``ANCHOR_WORDS`` words either side in the plain text,
    skipping other numbers, so updating a neighbour in a table row does not
    re-identify this one.
    """
    words = _WORD_RE.findall(_plain(block))
    anchors, cursor = [], 0
    for number in numbers:
        target = number.replace(" ", "").lower()
        idx = next((i for i in range(cursor, len(words)) if words[i] == target), None)
        if idx is None:  # e.g. the number sat inside link syntax; fall back softly
            anchors.append(target)
            continue
        left = [w for w in words[:idx] if not _is_number(w)]
        right = [w for w in words[idx + 1 :] if not _is_number(w)]
        before = " ".join(left[-ANCHOR_WORDS:])
        after = " ".join(right[:ANCHOR_WORDS])
        anchors.append(f"{before}|{after}")
        cursor = idx + 1
    return anchors


def note_provenance(note: Note) -> tuple[int, list[UnsourcedNumber]]:
    extra = note.frontmatter.model_extra or {}
    declared = bool(
        note.frontmatter.runs or note.frontmatter.sources or extra.get("numbers")
    )
    total = 0
    unsourced: list[UnsourcedNumber] = []
    for start, lines in _blocks(note.prose):
        sourced = declared or bool(_SOURCE_RE.search(" ".join(lines)))
        found = [
            (offset, line, number)
            for offset, line in enumerate(lines)
            for number in numbers_in(line)
        ]
        total += len(found)
        if sourced or not found:
            continue
        anchors = _anchors(" ".join(lines), [n for _, _, n in found])
        for (offset, line, number), anchor in zip(found, anchors, strict=True):
            unsourced.append(
                UnsourcedNumber(
                    path=note.path,
                    line=start + offset,
                    number=number,
                    context=line.strip()[:160],
                    anchor=anchor,
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
