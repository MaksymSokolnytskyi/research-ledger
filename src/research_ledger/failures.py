"""Failure memory: capture every failed command, recognise repeats, surface lessons.

The loop:

1. **Capture.** A Claude Code ``PostToolUseFailure`` hook (or ``ledger capture``)
   hands over the command and its error. The text is redacted first.
2. **Signature.** The error is normalised (numbers, paths, hex ids and quoted values
   replaced by placeholders) and hashed together with the tool and command head, so
   the same mistake on another file or line is still the same mistake.
3. **Record.** A new signature becomes a ``failure`` record; a known one becomes an
   ``occurrence`` record referencing the first. Records are append-only.
4. **Lesson.** A person or agent attaches a one-line ``lesson`` to a failure.
5. **Recall.** Before a command runs, :func:`known_failures` finds failures for the same
   command head, so the agent sees "this broke before, and here is why" -- and stays
   silent when there is nothing to say.

The number that says whether the vault learns is :func:`repeat_failure_rate`: the
share of failure events that happened *after* a lesson for that signature existed.
"""

from __future__ import annotations

import hashlib
import re
import shlex

from pydantic import BaseModel, ConfigDict

from research_ledger.config import Vault
from research_ledger.records import Record, StoredRecord, read_records, write_record
from research_ledger.redact import redact

_EXCEPTION_RE = re.compile(
    r"^\s*([A-Za-z_][\w.]*(?:Error|Exception|Exit|Interrupt))\b:?(.*)$"
)
_ERRORISH_RE = re.compile(r"(?i)\b(error|fatal|failed|not found|cannot|denied|invalid)\b")
_QUOTED_RE = re.compile(r"(['\"`])(.*?)\1")
_IDENTIFIER_RE = re.compile(r"[A-Za-z_][\w.\-]{0,39}")
_NORMALISERS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"(?:[A-Za-z]:)?[\\/][\w.\-\\/~]+"), "<path>"),
    (re.compile(r"\b0x[0-9a-fA-F]+\b|\b[0-9a-f]{7,40}\b"), "<hex>"),
    (re.compile(r"\d+(?:\.\d+)?"), "<n>"),
    (re.compile(r"\s+"), " "),
)
_WRAPPERS = {"sudo", "uv", "poetry", "pipenv", "npx", "env", "time"}
_RUNNERS = {"run", "exec"}


def command_head(command: str) -> str:
    """The part of a command that names *what* is run: ``python -m pytest`` -> ``pytest``.

    Two words are kept for tools whose first argument is the real verb
    (``git push``, ``npm test``); a script path is kept for interpreters.
    """
    try:
        tokens = shlex.split(command, posix=True)
    except ValueError:
        tokens = command.split()
    tokens = [t for t in tokens if "=" not in t.split("/")[0] or t.startswith("-")]
    while tokens and (tokens[0] in _WRAPPERS or tokens[0] in _RUNNERS):
        tokens = tokens[1:]
    if not tokens:
        return ""
    first = tokens[0].split("/")[-1].split("\\")[-1].lower()
    rest = [t for t in tokens[1:] if not t.startswith("-")]
    if first in {"python", "python3", "py", "node", "bash", "sh", "pwsh"}:
        if len(tokens) > 2 and tokens[1] == "-m":
            return tokens[2]
        return rest[0].replace("\\", "/") if rest else first
    if first in {"git", "npm", "pnpm", "yarn", "cargo", "go", "docker", "make", "pip"}:
        return f"{first} {rest[0]}" if rest else first
    return first


def normalise_error(error: str) -> str:
    """The stable part of an error message, with volatile details replaced."""
    lines = [line for line in error.splitlines() if line.strip()]
    exceptions = [m for line in lines if (m := _EXCEPTION_RE.match(line))]
    if exceptions:
        last = exceptions[-1]
        core = f"{last.group(1)}:{last.group(2)}"
    else:
        body = [line for line in lines if not line.startswith("Exit code")]
        errorish = [line for line in body if _ERRORISH_RE.search(line)]
        core = (errorish or body or lines or [""])[0]
    core = _QUOTED_RE.sub(_quoted, core)
    for pattern, placeholder in _NORMALISERS:
        core = pattern.sub(placeholder, core)
    return core.strip()[:200]


def _quoted(match: re.Match[str]) -> str:
    """Keep a quoted identifier (a module or key name is the point of the error);
    replace quoted values that vary between runs (paths, sentences, numbers)."""
    inner = match.group(2)
    if _IDENTIFIER_RE.fullmatch(inner):
        return f"'{inner}'"
    return "<str>"


def signature(tool: str, command: str, error: str) -> str:
    key = f"{tool}|{command_head(command)}|{normalise_error(error)}"
    return hashlib.sha1(key.encode("utf-8")).hexdigest()[:12]


class CaptureResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    record_id: str
    signature: str
    repeat: bool
    lessons: tuple[str, ...]


class FailureIndex(BaseModel):
    """Failures, occurrences and lessons read from the records folder."""

    model_config = ConfigDict(frozen=True)

    failures: dict[str, StoredRecord]  # signature -> first failure record
    occurrences: dict[str, list[StoredRecord]]  # signature -> later records
    lessons: dict[str, list[StoredRecord]]  # failure record id -> lessons

    def lessons_for(self, sig: str) -> list[StoredRecord]:
        first = self.failures.get(sig)
        return self.lessons.get(first.id, []) if first else []


def load_index(vault: Vault) -> FailureIndex:
    failures: dict[str, StoredRecord] = {}
    occurrences: dict[str, list[StoredRecord]] = {}
    lessons: dict[str, list[StoredRecord]] = {}
    for rec in read_records(vault):
        sig = str(rec.header.get("signature", ""))
        if rec.kind == "failure" and sig and sig not in failures:
            failures[sig] = rec
        elif rec.kind == "occurrence" and sig:
            occurrences.setdefault(sig, []).append(rec)
        elif rec.kind == "lesson":
            for ref in rec.header.get("refs", []) or []:
                lessons.setdefault(str(ref), []).append(rec)
    return FailureIndex(failures=failures, occurrences=occurrences, lessons=lessons)


def capture(
    vault: Vault, tool: str, command: str, error: str, agent: str = "main"
) -> CaptureResult | None:
    """Record a failed command. Returns None when capture is disabled."""
    cfg = vault.config.capture
    if not cfg.enabled:
        return None
    if cfg.redact:
        command = redact(command, cfg.extra_secret_patterns)
        error = redact(error, cfg.extra_secret_patterns)
    error = error[: cfg.max_output_chars]
    sig = signature(tool, command, error)
    index = load_index(vault)
    first = index.failures.get(sig)
    head = command_head(command)
    body = f"```\n$ {command}\n{error}\n```"
    extra = {"signature": sig, "tool": tool, "command_head": head}
    if first is None:
        record = Record(
            kind="failure",
            title=f"{head or tool}: {normalise_error(error)}"[:120],
            body=body,
            agent=agent,
            extra=extra,
        )
    else:
        record = Record(
            kind="occurrence",
            title=f"again: {first.title}"[:120],
            body=body,
            agent=agent,
            refs=(first.id,),
            extra=extra,
        )
    path = write_record(vault, record)
    lessons = tuple(lesson.title for lesson in index.lessons_for(sig))
    return CaptureResult(
        record_id=path.stem, signature=sig, repeat=first is not None, lessons=lessons
    )


def add_lesson(vault: Vault, failure_id: str, lesson: str, agent: str = "main") -> str:
    """Attach a one-line lesson to a failure record. Returns the lesson record id."""
    index = load_index(vault)
    if not any(f.id == failure_id for f in index.failures.values()):
        raise KeyError(f"no failure record {failure_id!r}")
    return write_record(
        vault, Record(kind="lesson", title=lesson, agent=agent, refs=(failure_id,))
    ).stem


class KnownFailure(BaseModel):
    model_config = ConfigDict(frozen=True)

    failure_id: str
    title: str
    times: int
    lessons: tuple[str, ...]


def known_failures(vault: Vault, command: str, limit: int = 3) -> list[KnownFailure]:
    """Failures recorded for the same command head, most frequent first."""
    head = command_head(command)
    if not head:
        return []
    index = load_index(vault)
    out = []
    for sig, first in index.failures.items():
        if first.header.get("command_head") != head:
            continue
        out.append(
            KnownFailure(
                failure_id=first.id,
                title=first.title,
                times=1 + len(index.occurrences.get(sig, [])),
                lessons=tuple(lesson.title for lesson in index.lessons_for(sig)),
            )
        )
    return sorted(out, key=lambda k: (-bool(k.lessons), -k.times))[:limit]


def repeat_failure_rate(vault: Vault) -> float:
    """Share of failure events that happened after a lesson for them was recorded."""
    index = load_index(vault)
    total = repeats = 0
    for sig, first in index.failures.items():
        events = [first, *index.occurrences.get(sig, [])]
        lesson_times = sorted(lesson.when for lesson in index.lessons_for(sig))
        total += len(events)
        if lesson_times:
            repeats += sum(e.when > lesson_times[0] for e in events)
    return round(repeats / total, 4) if total else 0.0
