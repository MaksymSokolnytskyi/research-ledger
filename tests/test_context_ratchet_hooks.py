"""Context packs, the ratchet, init on existing projects, hooks and the CLI."""

from __future__ import annotations

import json
from pathlib import Path

from conftest import write

from research_ledger.cli import main
from research_ledger.config import find_vault
from research_ledger.context import build_context
from research_ledger.corpus import load_corpus
from research_ledger.hooks import run_hook
from research_ledger.ratchet import compare, load_baseline, record_pass
from research_ledger.scaffold import apply, plan
from research_ledger.search import BM25, tokenize


def test_tokenize_keeps_identifiers_whole_and_split() -> None:
    tokens = tokenize("gpu_search.py failed")
    assert {"gpu_search.py", "gpu", "search", "py", "failed"} <= set(tokens)


def test_bm25_prefers_the_matching_document() -> None:
    index = BM25(["cache hit rate of the judge", "unrelated text about weather"])
    assert index.rank("judge cache")[0][0] == 0


def test_context_puts_named_entities_first_and_surfaces_lessons(demo) -> None:
    pack = build_context(load_corpus(demo), "why do judge verdicts flip between runs")
    assert pack.items[0].path == "def/judge.md"
    assert "verdict-drift" in " ".join(i.path for i in pack.items)
    failing = build_context(
        load_corpus(demo), "run_pilot.py fails with connection refused"
    )
    assert "ollama serve" in failing.failures[0].excerpt


def test_context_is_silent_when_nothing_matches(demo) -> None:
    assert (
        build_context(load_corpus(demo), "quarterly tax filing in Belize").render() == ""
    )


def test_ratchet_tightens_flags_regressions_and_adopts(blank) -> None:
    record_pass(blank, {"orphans": 5, "dangling_links": 2})
    record_pass(blank, {"orphans": 3, "dangling_links": 2})
    assert load_baseline(blank)["orphans"] == 3  # tightened
    result = compare(blank, {"orphans": 4, "dangling_links": 1})
    assert [c.metric for c in result.regressions] == ["orphans"]
    assert [c.metric for c in result.improvements] == ["dangling_links"]
    record_pass(blank, {"orphans": 4, "dangling_links": 1})
    assert load_baseline(blank)["orphans"] == 3  # a regression never loosens it
    record_pass(blank, {"orphans": 4, "dangling_links": 1}, adopt=True)
    assert load_baseline(blank)["orphans"] == 4  # only an explicit adopt does


def test_init_on_an_existing_project_touches_nothing(tmp_path: Path) -> None:
    write(tmp_path, "docs/notes.md", "# mine\n")
    write(tmp_path, "CLAUDE.md", "my rules\n")
    write(tmp_path, ".obsidian/appearance.json", '{"theme": "mine"}')
    (tmp_path / ".git").mkdir()
    files, notes = plan(tmp_path, name="proj")
    created = {f.path.relative_to(tmp_path).as_posix() for f in files}
    assert created == {"ledger.toml", ".obsidian/snippets/ledger.css"}
    assert any("CLAUDE.md left untouched" in n for n in notes)
    assert any(".gitignore" in n for n in notes)
    apply(files)
    assert (tmp_path / "CLAUDE.md").read_text() == "my rules\n"
    assert json.loads((tmp_path / ".obsidian/appearance.json").read_text()) == {
        "theme": "mine"
    }


def test_cli_init_then_audit_passes_and_detects_regression(
    tmp_path: Path, capsys
) -> None:
    assert main(["init", str(tmp_path), "--name", "t", "--language", "uk"]) == 0
    assert "Як працює цей vault" in (tmp_path / "LEDGER.md").read_text(encoding="utf-8")
    assert main(["audit", "--path", str(tmp_path)]) == 0
    write(tmp_path, "stray.md", "# stray\n[[missing]]\n")
    assert main(["audit", "--path", str(tmp_path), "--check"]) == 1
    assert "WORSE" in capsys.readouterr().out


def test_hooks_are_inert_outside_a_ledger(tmp_path: Path) -> None:
    payload = {"cwd": str(tmp_path), "prompt": "something long enough to match"}
    assert run_hook("user-prompt", json.dumps(payload)) == ""


def test_hooks_never_raise_on_garbage() -> None:
    assert run_hook("user-prompt", "{not json") == ""
    assert run_hook("no-such-event", "{}") == ""


def test_prompt_hook_injects_context(demo) -> None:
    payload = {
        "cwd": str(demo.root),
        "prompt": "Why do judge verdicts flip between runs?",
    }
    out = json.loads(run_hook("user-prompt", json.dumps(payload)))
    ctx = out["hookSpecificOutput"]
    assert ctx["hookEventName"] == "UserPromptSubmit"
    assert "def/judge.md" in ctx["additionalContext"]


def test_failure_hooks_capture_then_recall(demo) -> None:
    cwd = str(demo.root)
    fail = {
        "cwd": cwd,
        "tool_name": "Bash",
        "tool_input": {"command": "python train.py"},
        "error": "Exit code 1\nRuntimeError: CUDA out of memory",
    }
    first = json.loads(run_hook("tool-failure", json.dumps(fail)))
    assert "Failure recorded" in first["hookSpecificOutput"]["additionalContext"]
    assert (
        run_hook("pre-bash", json.dumps({**fail, "error": None})) == ""
    )  # once, no lesson
    run_hook("tool-failure", json.dumps(fail))
    recall = json.loads(run_hook("pre-bash", json.dumps({**fail, "error": None})))
    assert "x2" in recall["hookSpecificOutput"]["additionalContext"]
    assert find_vault(demo.root).root == demo.root
