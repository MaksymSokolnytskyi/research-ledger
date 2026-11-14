"""One pass over the vault: run every check, return structured results.

Checks return data; printing and page generation happen elsewhere. The original
runner scraped numbers out of each script's printed text with regular expressions, so
rewording a message silently broke the ratchet. Here the metrics dictionary *is* the
interface.
"""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, ConfigDict

from research_ledger.config import Vault
from research_ledger.corpus import Corpus, load_corpus
from research_ledger.failures import load_index, repeat_failure_rate
from research_ledger.graph import LinkGraph, build_graph, merge_candidates, orphans
from research_ledger.lifecycle import LifecycleReport, lifecycle
from research_ledger.provenance import ProvenanceReport, provenance
from research_ledger.records import IntegrityReport, check_integrity


class AuditResult(BaseModel):
    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    corpus: Corpus
    graph: LinkGraph
    orphans: tuple[str, ...]
    merges: tuple[tuple[str, str, float], ...]
    provenance: ProvenanceReport
    lifecycle: LifecycleReport
    integrity: IntegrityReport
    failures: int
    failures_without_lesson: int
    repeat_failure_rate: float

    @property
    def metrics(self) -> dict[str, float]:
        """Flat numbers for the ratchet and the history. Stable names: never rename."""
        notes = [n for n in self.corpus.notes if not n.generated]
        return {
            "notes": len(notes),
            "words": sum(n.words for n in notes),
            "dangling_links": len(self.graph.dangling),
            "orphans": len(self.orphans),
            "merge_candidates": len(self.merges),
            "numbers_total": self.provenance.numbers_total,
            "numbers_unsourced": len(self.provenance.unsourced),
            "numbers_unsourced_per_1k_words": self.provenance.unsourced_per_1k_words,
            "lifecycle_missing": len(self.lifecycle.missing),
            "lifecycle_stale": len(self.lifecycle.stale),
            "invalid_frontmatter": len(self.lifecycle.invalid_frontmatter),
            "records": self.integrity.checked,
            "records_bad_names": len(self.integrity.bad_names),
            "records_rewritten": len(self.integrity.rewritten),
            "failures": self.failures,
            "failures_without_lesson": self.failures_without_lesson,
            "repeat_failure_rate": self.repeat_failure_rate,
        }


def run_audit(vault: Vault, today: date | None = None) -> AuditResult:
    corpus = load_corpus(vault)
    graph = build_graph(corpus)
    index = load_index(vault)
    without_lesson = sum(1 for sig in index.failures if not index.lessons_for(sig))
    return AuditResult(
        corpus=corpus,
        graph=graph,
        orphans=tuple(p.as_posix() for p in orphans(corpus, graph)),
        merges=tuple(
            (a.as_posix(), b.as_posix(), s) for a, b, s in merge_candidates(graph)
        ),
        provenance=provenance(corpus),
        lifecycle=lifecycle(corpus, today),
        integrity=check_integrity(vault),
        failures=len(index.failures),
        failures_without_lesson=without_lesson,
        repeat_failure_rate=repeat_failure_rate(vault),
    )
