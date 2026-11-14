"""Every note declares how it ends; this finds the ones that did not, or that lapsed.

The disease: a note is written for a reason, serves it, and nobody ever decides it is
dead. It keeps looking authoritative while the corpus grows around it. So a note
declares its end condition when it is born:

* ``snapshot`` -- a write-up of something that happened; finished at birth, never
  edited, only superseded;
* ``living`` -- maintained indefinitely; carries ``last_verified``;
* ``closed`` -- belongs in the archive.

Generated notes and append-only records are exempt: their lifecycle is implied by
where they come from.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from research_ledger.corpus import Corpus, in_folder


class LifecycleReport(BaseModel):
    model_config = ConfigDict(frozen=True)

    missing: tuple[Path, ...]
    stale: tuple[tuple[Path, int], ...]
    closed_outside_archive: tuple[Path, ...]
    invalid_frontmatter: tuple[tuple[Path, str], ...]


def lifecycle(corpus: Corpus, today: date | None = None) -> LifecycleReport:
    today = today or date.today()
    cfg = corpus.vault.config
    records = cfg.folders.records
    archive = cfg.folders.archive
    missing: list[Path] = []
    stale: list[tuple[Path, int]] = []
    closed: list[Path] = []
    invalid: list[tuple[Path, str]] = []
    for note in corpus.notes:
        if note.frontmatter_error:
            invalid.append((note.path, note.frontmatter_error))
        if note.generated or in_folder(note.path, records):
            continue
        fm = note.frontmatter
        if fm.lifecycle is None:
            missing.append(note.path)
        elif fm.lifecycle == "living":
            if fm.last_verified is None:
                stale.append((note.path, -1))
            else:
                age = (today - fm.last_verified).days
                if age > cfg.stale_after_days:
                    stale.append((note.path, age))
        elif fm.lifecycle == "closed" and not in_folder(note.path, archive):
            closed.append(note.path)
    return LifecycleReport(
        missing=tuple(missing),
        stale=tuple(stale),
        closed_outside_archive=tuple(closed),
        invalid_frontmatter=tuple(invalid),
    )
