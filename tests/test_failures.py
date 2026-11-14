"""Failure memory: redaction, signatures, repeats, lessons and the repeat rate."""

from __future__ import annotations

import pytest

from research_ledger.failures import (
    add_lesson,
    capture,
    command_head,
    known_failures,
    repeat_failure_rate,
    signature,
)
from research_ledger.records import Record, check_integrity, write_record
from research_ledger.redact import MASK, redact


@pytest.mark.parametrize(
    "secret",
    [
        "sk-ant-api03-" + "a" * 40,
        "pplx-" + "b" * 40,
        "AIza" + "c" * 35,
        "ghp_" + "d" * 36,
        "Authorization: Bearer " + "e" * 30,
        "postgres://user:hunter2@db.example.com/x",
    ],
)
def test_secrets_are_masked(secret: str) -> None:
    out = redact(f"before {secret} after")
    assert MASK in out and "before" in out and "after" in out
    assert "hunter2" not in out and "a" * 40 not in out


def test_key_value_assignments_are_masked() -> None:
    assert redact("GEMINI_API_KEY=abc123def456") == f"GEMINI_API_KEY={MASK}"
    assert redact('"password": "s3cret!"') == f'"password": "{MASK}"'


@pytest.mark.parametrize(
    ("command", "head"),
    [
        ("python -m pytest tests -q", "pytest"),
        ("FOO=1 uv run python scripts/train.py --epochs 3", "scripts/train.py"),
        ("git push origin main", "git push"),
        ("npm test", "npm test"),
        ("ruff check .", "ruff"),
    ],
)
def test_command_head(command: str, head: str) -> None:
    assert command_head(command) == head


def test_signature_ignores_volatile_details_but_not_the_cause() -> None:
    a = signature("Bash", "pytest a.py", 'File "/x/a.py", line 3\nKeyError: 17')
    b = signature("Bash", "pytest b.py", 'File "/y/b.py", line 99\nKeyError: 42')
    assert a == b
    skrf = signature("Bash", "pytest", "ModuleNotFoundError: No module named 'skrf'")
    numpy = signature("Bash", "pytest", "ModuleNotFoundError: No module named 'numpy'")
    assert skrf != numpy


def test_capture_repeat_lesson_and_rate(blank) -> None:
    err = "Exit code 1\nModuleNotFoundError: No module named 'skrf'\nTOKEN=abcd1234efgh"
    first = capture(blank, "Bash", "python -m pytest -q", err)
    assert first is not None and not first.repeat
    text = (blank.root / "records" / f"{first.record_id}.md").read_text(encoding="utf-8")
    assert "abcd1234efgh" not in text and MASK in text

    second = capture(blank, "Bash", "pytest tests/other.py", err)
    assert second is not None and second.repeat and second.lessons == ()
    assert repeat_failure_rate(blank) == 0.0  # no lesson existed yet

    add_lesson(blank, first.record_id, "install scikit-rf")
    third = capture(blank, "Bash", "pytest", err)
    assert third is not None and third.lessons == ("install scikit-rf",)
    assert repeat_failure_rate(blank) == pytest.approx(1 / 3, abs=1e-3)

    known = known_failures(blank, "python -m pytest tests")
    assert known[0].times == 3 and known[0].lessons == ("install scikit-rf",)
    assert known_failures(blank, "ruff check .") == []


def test_capture_can_be_switched_off(tmp_path) -> None:
    from research_ledger.config import find_vault

    (tmp_path / "ledger.toml").write_text(
        "[capture]\nenabled = false\n", encoding="utf-8"
    )
    assert capture(find_vault(tmp_path), "Bash", "x", "boom") is None


def test_records_never_overwrite_and_names_are_checked(blank) -> None:
    rec = Record(kind="run", title="Same title", agent="lab")
    p1, p2 = write_record(blank, rec), write_record(blank, rec)
    assert p1 != p2 and p1.exists() and p2.exists()
    (blank.root / "records" / "renamed by hand.md").write_text("x", encoding="utf-8")
    assert check_integrity(blank).bad_names == ("renamed by hand.md",)


def test_lesson_requires_a_real_failure(blank) -> None:
    with pytest.raises(KeyError):
        add_lesson(blank, "no-such-failure", "x")
