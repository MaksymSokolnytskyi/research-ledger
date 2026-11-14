"""Number provenance heuristics and lifecycle declarations."""

from __future__ import annotations

from datetime import date

from conftest import write

from research_ledger.corpus import load_corpus
from research_ledger.lifecycle import lifecycle
from research_ledger.provenance import numbers_in, provenance


def test_labels_are_not_counted_as_results() -> None:
    assert numbers_in("Released 2026-03-02 in v1.2.3 during 2025.") == []
    assert numbers_in("1. first step") == []
    assert numbers_in("## 3.2 Results") == []
    assert numbers_in("accuracy 0.913 on 1,000 items, 54% of 812") == [
        "0.913",
        "1,000",
        "54%",
        "812",
    ]


def test_a_link_sources_its_paragraph_and_table_row_only(blank) -> None:
    write(
        blank.root,
        "n.md",
        "Score 0.81 ([run](logs/r.md)).\n\nScore 0.77 alone.\n\n"
        "| a | b |\n|---|---|\n| 0.5 | [[r]] |\n| 0.6 | none |\n",
    )
    found = [u.number for u in provenance(load_corpus(blank)).unsourced]
    assert found == ["0.77", "0.6"]


def test_frontmatter_runs_source_the_whole_note(blank) -> None:
    write(blank.root, "n.md", "---\nruns: [r1]\n---\nScore 0.77 and 0.81.\n")
    assert provenance(load_corpus(blank)).unsourced == ()


def test_lifecycle_missing_stale_and_closed(blank) -> None:
    write(blank.root, "a.md", "# no header\n")
    write(blank.root, "b.md", "---\nlifecycle: living\nlast_verified: 2026-01-01\n---\n")
    write(blank.root, "c.md", "---\nlifecycle: closed\n---\n")
    write(blank.root, "archive/d.md", "---\nlifecycle: closed\n---\n")
    write(blank.root, "records/2026-01-01_main_run_x_101010.md", "# record\n")
    report = lifecycle(load_corpus(blank), today=date(2026, 3, 1))
    assert [p.name for p in report.missing] == ["a.md"]
    assert [(p.name, age) for p, age in report.stale] == [("b.md", 59)]
    assert [p.name for p in report.closed_outside_archive] == ["c.md"]
