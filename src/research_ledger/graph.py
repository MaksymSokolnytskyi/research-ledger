"""The link graph and the structural defects it reveals.

* **dangling** -- a link to a note that does not exist. In Obsidian one click on it
  creates an empty file that then looks like the real document.
* **orphan** -- a note nothing links to. Nobody reaches it, so nobody reads it, and it
  rots while looking authoritative. Entry points and generated pages are exempt.
* **merge candidate** -- two notes that link to each other and share most of their
  neighbours: one document cut in half.
"""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from research_ledger.corpus import Corpus, in_folder

MERGE_JACCARD = 0.6
MERGE_MIN_NEIGHBOURS = 3


class Dangling(BaseModel):
    model_config = ConfigDict(frozen=True)

    source: Path
    target: str


class LinkGraph(BaseModel):
    """Directed note graph; generated notes are excluded on both ends.

    A generated page that links to everything would otherwise make every note look
    reachable: a report is not evidence about the corpus it reports on.
    """

    model_config = ConfigDict(frozen=True)

    edges: dict[Path, frozenset[Path]]
    dangling: tuple[Dangling, ...]

    def inbound(self) -> dict[Path, set[Path]]:
        result: dict[Path, set[Path]] = defaultdict(set)
        for source, targets in self.edges.items():
            for target in targets:
                result[target].add(source)
        return result


def build_graph(corpus: Corpus) -> LinkGraph:
    edges: dict[Path, frozenset[Path]] = {}
    dangling: list[Dangling] = []
    for note in corpus.notes:
        if note.generated:
            continue
        targets: set[Path] = set()
        for link in note.links:
            if corpus.is_attachment(link):
                continue
            target = corpus.resolve(note, link)
            if target is None:
                dangling.append(Dangling(source=note.path, target=link.target))
            elif target.path != note.path and not target.generated:
                targets.add(target.path)
        edges[note.path] = frozenset(targets)
    return LinkGraph(edges=edges, dangling=tuple(dangling))


def orphans(corpus: Corpus, graph: LinkGraph) -> list[Path]:
    """Notes with no inbound link. Entry points and records are exempt: records are
    evidence reached through ``refs`` and the notes that cite them, not reading."""
    entry = {e.lower() for e in corpus.vault.config.entry_points}
    records = corpus.vault.config.folders.records
    inbound = graph.inbound()
    return sorted(
        path
        for path in graph.edges
        if not inbound.get(path)
        and path.stem.lower() not in entry
        and not in_folder(path, records)
    )


def merge_candidates(graph: LinkGraph) -> list[tuple[Path, Path, float]]:
    """Mutually linked pairs whose other neighbours overlap by Jaccard >= 0.6."""
    inbound = graph.inbound()

    def neighbours(node: Path) -> set[Path]:
        return set(graph.edges.get(node, ())) | inbound.get(node, set())

    out: list[tuple[Path, Path, float]] = []
    for a, targets in graph.edges.items():
        for b in targets:
            if a < b and a in graph.edges.get(b, ()):
                na, nb = neighbours(a) - {b}, neighbours(b) - {a}
                union = na | nb
                if len(union) < MERGE_MIN_NEIGHBOURS:
                    continue
                score = len(na & nb) / len(union)
                if score >= MERGE_JACCARD:
                    out.append((a, b, score))
    return sorted(out, key=lambda t: -t[2])
