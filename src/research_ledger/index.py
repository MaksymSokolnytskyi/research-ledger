"""Incremental search index, cached in ``.ledger/``.

The prompt hook runs on every message, so it must not re-read the vault each time. On
3,000 notes a cold build took over five seconds, almost all of it YAML parsing and
tokenisation. Two cache files keep the warm path small:

* ``index-notes.pkl`` -- per-note metadata and term counts, read only when some note
  changed, so a single edited note is re-parsed instead of the vault;
* ``index-search.pkl`` -- note metadata plus BM25 postings in flat arrays, read on every
  query. It is cheap to unpickle and a query touches only its own terms.

Freshness is decided by each file's size and modification time. Both files are machine
state: safe to delete, rebuilt on the next call.
"""

from __future__ import annotations

import os
import pickle
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from research_ledger.config import Vault
from research_ledger.corpus import iter_note_paths, read_note
from research_ledger.search import Postings, tokenize

NOTES_CACHE = "index-notes.pkl"
SEARCH_CACHE = "index-search.pkl"
CACHE_VERSION = 4

Signature = tuple[int, int]


@dataclass(frozen=True)
class IndexedNote:
    """What retrieval needs from a note. Text is re-read only for notes that are shown."""

    path: str
    stem: str
    title: str
    aliases: tuple[str, ...]
    tier: int | None
    lifecycle: str | None
    generated: bool


@dataclass(frozen=True)
class NoteIndex:
    notes: tuple[IndexedNote, ...]
    postings: Postings
    rebuilt: int  # notes parsed on this call (0 = everything came from the cache)


def _signatures(vault: Vault) -> dict[str, Signature]:
    out: dict[str, Signature] = {}
    for rel in iter_note_paths(vault):
        try:
            st = os.stat(vault.root / rel)
        except OSError:
            continue
        out[rel.as_posix()] = (st.st_mtime_ns, st.st_size)
    return out


def _parse(vault: Vault, rel: str) -> tuple[IndexedNote, Counter[str]]:
    note = read_note(vault, Path(rel))
    meta = IndexedNote(
        path=rel,
        stem=note.stem,
        title=note.title,
        aliases=note.frontmatter.aliases,
        tier=note.frontmatter.tier,
        lifecycle=note.frontmatter.lifecycle,
        generated=note.generated,
    )
    return meta, Counter(tokenize(f"{note.title}\n{note.stem}\n{note.prose}"))


def _load(path: Path) -> Any:
    try:
        with open(path, "rb") as f:
            version, payload = pickle.load(f)
        return payload if version == CACHE_VERSION else None
    except (
        OSError,
        pickle.UnpicklingError,
        EOFError,
        ValueError,
        TypeError,
        AttributeError,
    ):
        return None


def _dump(path: Path, payload: object) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        with open(tmp, "wb") as f:
            pickle.dump((CACHE_VERSION, payload), f, protocol=pickle.HIGHEST_PROTOCOL)
        tmp.replace(path)  # atomic: a parallel reader never sees half a file
    except OSError:
        pass


def load_index(vault: Vault) -> NoteIndex:
    signatures = _signatures(vault)
    search = _load(vault.state_dir / SEARCH_CACHE)
    if search is not None and search["signatures"] == signatures:
        return NoteIndex(notes=search["notes"], postings=search["postings"], rebuilt=0)

    cached: dict[str, tuple[Signature, IndexedNote, Counter[str]]] = (
        _load(vault.state_dir / NOTES_CACHE) or {}
    )
    fresh: dict[str, tuple[Signature, IndexedNote, Counter[str]]] = {}
    rebuilt = 0
    for rel, sig in signatures.items():
        hit = cached.get(rel)
        if hit is not None and hit[0] == sig:
            fresh[rel] = hit
        else:
            meta, tf = _parse(vault, rel)
            fresh[rel] = (sig, meta, tf)
            rebuilt += 1
    notes = tuple(v[1] for v in fresh.values())
    postings = Postings.build([v[2] for v in fresh.values()])
    _dump(vault.state_dir / NOTES_CACHE, fresh)
    _dump(
        vault.state_dir / SEARCH_CACHE,
        {"signatures": signatures, "notes": notes, "postings": postings},
    )
    return NoteIndex(notes=notes, postings=postings, rebuilt=rebuilt)
