"""Beta-readiness: quiet failure capture, injection modes, caching, existing projects."""

from __future__ import annotations

import json
import os
from pathlib import Path

from conftest import write

from research_ledger.audit import load_adopted, run_audit, save_adopted
from research_ledger.cli import main
from research_ledger.config import find_vault
from research_ledger.context import pack_for_prompt
from research_ledger.failures import add_lesson, capture, load_failures
from research_ledger.generate import health_page
from research_ledger.hooks import run_hook
from research_ledger.index import load_index
from research_ledger.ratchet import compare
from research_ledger.usage import summary


def _records(vault) -> list[Path]:
    return sorted(vault.folder("records").glob("*.md"))


def test_answers_are_not_failures(blank) -> None:
    assert capture(blank, "Bash", "grep -rn TODO src", "Exit code 1") is None
    assert capture(blank, "Bash", "cat a.txt | grep foo", "Exit code 1") is None
    assert capture(blank, "Bash", "git diff --exit-code", "Exit code 1") is None
    assert capture(blank, "Bash", "make build", "Exit code 2") is None  # nothing to learn
    assert (
        capture(blank, "Bash", "pytest -q", "Exit code 1\nAssertionError: x") is not None
    )


def test_repeats_are_counted_not_copied(blank) -> None:
    err = "Exit code 1\nRuntimeError: CUDA out of memory"
    first = capture(blank, "Bash", "python train.py", err)
    for _ in range(4):
        capture(blank, "Bash", "python train.py --lr 3e-4", err)
    assert len(_records(blank)) == 1
    assert first is not None
    assert load_failures(blank).count(first.signature) == 5

    add_lesson(blank, first.record_id, "lower the batch size to 16 on 12 GB")
    capture(blank, "Bash", "python train.py", err)  # lesson did not prevent it
    kinds = [p.name.split("_")[2] for p in _records(blank)]
    assert sorted(kinds) == ["failure", "lesson", "occurrence"]


def test_injection_modes(demo, tmp_path) -> None:
    generic = "rewrite the verdict drift section"  # matches, names no entity
    assert pack_for_prompt(demo, generic) != ""  # relevant: speaks on weak matches
    cfg = demo.root / "ledger.toml"
    cfg.write_text(cfg.read_text() + '\n[context]\ninject = "named"\n', encoding="utf-8")
    named = find_vault(demo.root)
    assert pack_for_prompt(named, generic) == ""
    assert "def/judge.md" in pack_for_prompt(named, "how does the judge score texts?")
    off = demo.root / "ledger.toml"
    off.write_text(off.read_text().replace('"named"', '"off"'), encoding="utf-8")
    assert pack_for_prompt(find_vault(demo.root), "how does the judge score texts") == ""


def test_index_is_reused_until_a_note_changes(demo) -> None:
    assert load_index(demo).rebuilt > 0
    assert load_index(demo).rebuilt == 0
    note = demo.root / "def" / "judge.md"
    note.write_text(note.read_text() + "\nMore.\n", encoding="utf-8")
    stat = note.stat()
    os.utime(note, ns=(stat.st_atime_ns, stat.st_mtime_ns + 10_000_000))
    assert load_index(demo).rebuilt == 1


def test_existing_project_is_namespaced_and_scoped(tmp_path: Path) -> None:
    write(tmp_path, "README.md", "# project\n")
    write(tmp_path, "docs/guide.md", "# guide\n")
    write(tmp_path, "vendor/lib/README.md", "# vendored, not ours\n")
    write(tmp_path, "logs/app.log", "app output\n")
    assert main(["init", str(tmp_path), "--existing", "--docs", "docs"]) == 0
    vault = find_vault(tmp_path)
    assert vault.config.folders.records == "ledger/records"
    assert vault.config.include == ("docs/**/*.md", "ledger/**/*.md")
    assert not (tmp_path / ".obsidian").exists()  # a code repo is not made a vault
    paths = {n.path.as_posix() for n in run_audit(vault).corpus.notes}
    assert paths == {"docs/guide.md"}
    capture(vault, "Bash", "python app.py", "Exit code 1\nValueError: bad config")
    assert len(list((tmp_path / "ledger" / "records").glob("*.md"))) == 1
    assert sorted(p.name for p in (tmp_path / "logs").iterdir()) == ["app.log"]


def test_health_page_separates_new_issues_from_adopted_debt(demo) -> None:
    save_adopted(demo, run_audit(demo))
    write(demo.root, "notes/fresh.md", "---\nlifecycle: snapshot\n---\n[[nowhere]]\n")
    result = run_audit(demo)
    page = health_page(result, compare(demo, result.metrics), load_adopted(demo))
    assert "## Dangling links: 1 new, 1 known" in page
    new_part = page.split("## Dangling links")[1].split("> [!note]-")[0]
    assert "nowhere" in new_part and "sampling-notes" not in new_part


def test_hooks_log_local_usage_without_content(demo) -> None:
    payload = {"cwd": str(demo.root), "prompt": "why do judge verdicts flip between runs"}
    run_hook("user-prompt", json.dumps(payload))
    run_hook("user-prompt", json.dumps({**payload, "prompt": "zzzz qqqq xxxx yyyy"}))
    stats = summary(demo)["user-prompt"]
    assert stats["calls"] == 2 and stats["spoke"] == 1
    raw = (demo.state_dir / "usage.jsonl").read_text(encoding="utf-8")
    assert "verdicts" not in raw  # no prompt text is stored


def test_lesson_accepts_a_unique_prefix_and_fails_politely(blank, capsys) -> None:
    rec = capture(blank, "Bash", "python app.py", "Exit code 1\nValueError: bad config")
    assert rec is not None
    assert (
        main(["lesson", rec.record_id[:24], "fix the config", "--path", str(blank.root)])
        == 0
    )
    assert main(["lesson", "nope", "x", "--path", str(blank.root)]) == 2
    assert "no failure record matches" in capsys.readouterr().err
