"""Notes, links and the graph checks, on the demo vault and small fixtures."""

from __future__ import annotations

from pathlib import Path

from conftest import write

from research_ledger.audit import run_audit
from research_ledger.corpus import load_corpus, parse_links, split_frontmatter
from research_ledger.graph import build_graph, merge_candidates, orphans


def test_demo_vault_findings_are_exactly_the_planted_ones(demo) -> None:
    r = run_audit(demo)
    assert [(d.source.as_posix(), d.target) for d in r.graph.dangling] == [
        ("notes/verdict-drift.md", "sampling-notes")
    ]
    assert r.orphans == ("notes/old-plan.md",)
    assert [u.number for u in r.provenance.unsourced] == ["71.3%"]
    assert [p.as_posix() for p in r.lifecycle.missing] == ["notes/old-plan.md"]
    assert r.failures == 1 and r.failures_without_lesson == 0


def test_links_ignore_code_and_external_urls() -> None:
    body = (
        "See [[alpha|the alpha]] and [b](notes/beta.md#x) and ![[img.png]].\n"
        "`[[not a link]]` and https://x.org and [web](https://x.org)\n"
        "```\n[[also not]]\n```\n"
    )
    links = parse_links(body)
    assert [(link.target, link.kind) for link in links] == [
        ("alpha", "wiki"),
        ("img.png", "wiki"),
        ("notes/beta.md", "markdown"),
    ]


def test_broken_yaml_is_reported_not_fatal() -> None:
    data, body, error = split_frontmatter("---\ntier: [1\n---\n# T\n")
    assert data == {} and body.startswith("# T") and error


def test_resolution_by_alias_and_relative_markdown(blank) -> None:
    write(blank.root, "def/judge.md", "---\naliases: [LLM judge]\n---\n# judge\n")
    write(blank.root, "notes/a.md", "[[LLM judge]] and [j](../def/judge.md)\n")
    corpus = load_corpus(blank)
    graph = build_graph(corpus)
    assert graph.edges[Path("notes/a.md")] == {Path("def/judge.md")}
    assert graph.dangling == ()


def test_generated_pages_do_not_rescue_orphans(blank) -> None:
    write(blank.root, "lonely.md", "# lonely\n")
    write(blank.root, "_generated/_health.md", "---\ngenerated: true\n---\n[[lonely]]\n")
    corpus = load_corpus(blank)
    assert Path("lonely.md") in orphans(corpus, build_graph(corpus))


def test_merge_candidates_find_one_topic_cut_in_half(blank) -> None:
    for name in ("x", "y", "z"):
        write(blank.root, f"{name}.md", f"# {name}\n[[a]] [[b]]\n")
    write(blank.root, "a.md", "[[b]] [[x]] [[y]] [[z]]\n")
    write(blank.root, "b.md", "[[a]] [[x]] [[y]] [[z]]\n")
    pairs = merge_candidates(build_graph(load_corpus(blank)))
    assert (Path("a.md"), Path("b.md")) == pairs[0][:2]


def test_escaped_pipe_inside_a_table_link_resolves() -> None:
    from research_ledger.corpus import parse_links

    (link,) = parse_links("| see | [[1_RESULT\\|result]] |\n")
    assert link.target == "1_RESULT"
    assert link.shown == "result"
