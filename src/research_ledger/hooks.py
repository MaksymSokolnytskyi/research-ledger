"""Claude Code hook handlers: the ledger's entry points inside an agent session.

``ledger hook <event>`` reads the hook's JSON from stdin and prints a
``hookSpecificOutput.additionalContext`` object when it has something to add.

* ``session-start`` -- a three-line brief: vault size, failures without a lesson.
* ``user-prompt`` -- **task-context intake**: the submitted prompt becomes a query and
  the matching notes and known failures are attached to it.
* ``pre-bash`` -- before a shell command runs, known failures of the same command and
  their lessons.
* ``tool-failure`` -- a failed command is captured (redacted) as a failure or as a
  repeat of a known one.

Rules, in priority order:

1. **Never break the turn.** Every error path exits 0 with no output.
2. **Inert outside a ledger.** Without a ``ledger.toml`` above the working directory
   every handler does nothing, so a plugin installed for the user stays silent in
   ordinary projects.
3. **Silent when there is nothing to say.**
"""

from __future__ import annotations

import contextlib
import json
import os
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

from research_ledger.config import CONFIG_NAME, Vault, find_vault

EVENT_NAMES = {
    "session-start": "SessionStart",
    "user-prompt": "UserPromptSubmit",
    "pre-bash": "PreToolUse",
    "tool-failure": "PostToolUseFailure",
}


def _agent(vault: Vault) -> str:
    return os.environ.get("LEDGER_AGENT") or vault.config.agents[0]


def _vault_for(payload: dict[str, Any]) -> Vault | None:
    cwd = Path(payload.get("cwd") or os.getcwd())
    vault = find_vault(cwd)
    return vault if (vault.root / CONFIG_NAME).is_file() else None


def on_session_start(vault: Vault, payload: dict[str, Any]) -> str:
    from research_ledger.corpus import load_corpus
    from research_ledger.failures import load_index

    corpus = load_corpus(vault)
    index = load_index(vault)
    open_failures = [f for s, f in index.failures.items() if not index.lessons_for(s)]
    lines = [
        f"This folder is a research ledger ({vault.config.name}): "
        f"{len(corpus.notes)} notes. Numbers need a source; records in "
        f"`{vault.config.folders.records}/` are append-only.",
        'Use `ledger context "<task>"` for background and '
        '`ledger lesson <failure-id> "..."` after fixing a recorded failure.',
    ]
    if open_failures:
        recent = ", ".join(f"{f.id} ({f.title[:60]})" for f in open_failures[-3:])
        lines.append(f"Failures with no lesson yet: {recent}")
    return "\n".join(lines)


def on_user_prompt(vault: Vault, payload: dict[str, Any]) -> str:
    if not vault.config.context.inject_on_prompt:
        return ""
    prompt = str(payload.get("prompt", "")).strip()
    if len(prompt) < 12:
        return ""
    from research_ledger.context import build_context
    from research_ledger.corpus import load_corpus

    return build_context(load_corpus(vault), prompt).render()


def on_pre_bash(vault: Vault, payload: dict[str, Any]) -> str:
    if payload.get("tool_name") != "Bash":
        return ""
    command = str((payload.get("tool_input") or {}).get("command", ""))
    from research_ledger.failures import known_failures

    known = [k for k in known_failures(vault, command) if k.lessons or k.times > 1]
    if not known:
        return ""
    lines = ["This command has failed before in this ledger:"]
    for k in known:
        lesson = f" Lesson: {'; '.join(k.lessons)}" if k.lessons else ""
        lines.append(f"- {k.title} (x{k.times}, {k.failure_id}).{lesson}")
    return "\n".join(lines)


def on_tool_failure(vault: Vault, payload: dict[str, Any]) -> str:
    if payload.get("is_interrupt"):
        return ""
    tool = str(payload.get("tool_name", ""))
    tool_input = payload.get("tool_input") or {}
    command = str(tool_input.get("command") or tool_input.get("file_path") or "")
    error = str(payload.get("error", ""))
    if not error:
        return ""
    from research_ledger.failures import capture

    result = capture(vault, tool, command, error, agent=_agent(vault))
    if result is None:
        return ""
    if result.repeat and result.lessons:
        return (
            f"This failure is a repeat ({result.record_id}). "
            f"Recorded lesson: {'; '.join(result.lessons)}"
        )
    if result.repeat:
        return f"This failure has happened before ({result.record_id}); no lesson yet."
    return (
        f"Failure recorded as {result.record_id}. Once fixed, record the lesson with "
        f'`ledger lesson {result.record_id} "<one line>"`.'
    )


HANDLERS: dict[str, Callable[[Vault, dict[str, Any]], str]] = {
    "session-start": on_session_start,
    "user-prompt": on_user_prompt,
    "pre-bash": on_pre_bash,
    "tool-failure": on_tool_failure,
}


def run_hook(event: str, stdin: str) -> str:
    """Return the JSON to print (or ``""``). Raises nothing."""
    try:
        payload = json.loads(stdin) if stdin.strip() else {}
        vault = _vault_for(payload)
        if vault is None or event not in HANDLERS:
            return ""
        context = HANDLERS[event](vault, payload)
        if not context:
            return ""
        return json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": EVENT_NAMES[event],
                    "additionalContext": context,
                }
            },
            ensure_ascii=False,
        )
    except Exception as exc:  # a hook must never break the turn
        _log_error(event, exc)
        return ""


def _log_error(event: str, exc: Exception) -> None:
    try:
        vault = find_vault()
        vault.state_dir.mkdir(parents=True, exist_ok=True)
        with open(vault.state_dir / "hook_errors.log", "a", encoding="utf-8") as f:
            f.write(f"{event}: {type(exc).__name__}: {exc}\n")
    except Exception:
        pass


def main(event: str) -> None:
    with contextlib.suppress(Exception):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
    out = run_hook(event, sys.stdin.read())
    if out:
        print(out)
