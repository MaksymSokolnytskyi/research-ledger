"""Failure memory: capture every failed command, recognise repeats, surface lessons.

The loop:

1. **Capture.** A Claude Code ``PostToolUseFailure`` hook (or ``ledger capture``)
   hands over the command and its error. The text is redacted first. Commands whose
   non-zero exit is an answer rather than a mistake (``grep`` with no match, ``test``,
   ``diff``) are ignored: see ``capture.ignore_commands``.
2. **Signature.** The error is normalised (numbers, paths, hex ids and quoted values
   replaced by placeholders) and hashed together with the tool and command head, so
   the same mistake on another file or line is still the same mistake.
3. **Record.** A new signature becomes a ``failure`` record. Repeats are counted in
   ``.ledger/failures.json`` instead of filling the vault with copies; only a repeat
   that happens *after* a lesson exists is written as an ``occurrence`` record,
   because that is evidence the lesson did not work. Records are append-only.
4. **Lesson.** A person or agent attaches a one-line ``lesson`` to a failure.
5. **Recall.** Before a command runs, :func:`known_failures` finds failures for the same
   command head, so the agent sees "this broke before, and here is why" -- and stays
   silent when there is nothing to say.

The number that says whether the vault learns is :func:`repeat_failure_rate`: the
share of failure events that happened *after* a lesson for that signature existed.
"""

from __future__ import annotations

import hashlib
import json
import re
import shlex
from datetime import datetime

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
    """Failures, post-lesson repeats and lessons from the records folder, plus counts."""

    model_config = ConfigDict(frozen=True)

    failures: dict[str, StoredRecord]  # signature -> first failure record
    occurrences: dict[str, list[StoredRecord]]  # signature -> repeats after a lesson
    lessons: dict[str, list[StoredRecord]]  # failure record id -> lessons
    counts: dict[str, dict[str, int | str]]  # signature -> {"count", "after_lesson"}

    def lessons_for(self, sig: str) -> list[StoredRecord]:
        first = self.failures.get(sig)
        return self.lessons.get(first.id, []) if first else []

    def count(self, sig: str) -> int:
        """Times seen. Falls back to the records when this machine has no counter."""
        recorded = 1 + len(self.occurrences.get(sig, []))
        return max(int(self.counts.get(sig, {}).get("count", 0)), recorded)


COUNTS_FILE = "failures.json"


def _load_counts(vault: Vault) -> dict[str, dict[str, int | str]]:
    try:
        data = json.loads((vault.state_dir / COUNTS_FILE).read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _save_counts(vault: Vault, counts: dict[str, dict[str, int | str]]) -> None:
    vault.state_dir.mkdir(parents=True, exist_ok=True)
    tmp = vault.state_dir / (COUNTS_FILE + ".tmp")
    tmp.write_text(json.dumps(counts, indent=1), encoding="utf-8")
    tmp.replace(vault.state_dir / COUNTS_FILE)


def load_failures(vault: Vault) -> FailureIndex:
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
    return FailureIndex(
        failures=failures,
        occurrences=occurrences,
        lessons=lessons,
        counts=_load_counts(vault),
    )


def ignored(vault: Vault, command: str) -> bool:
    """True when the failing part of ``command`` is on the ignore list.

    The exit status of a pipeline or ``&&`` chain is that of its last command, so that
    is the one checked: ``cat x | grep y`` exiting 1 means grep found nothing.
    """
    segments = [s for s in re.split(r"\|\||&&|\||;", command) if s.strip()]
    if not segments:
        return False
    head = command_head(segments[-1])
    ignore = {c.lower() for c in vault.config.capture.ignore_commands}
    return head.lower() in ignore or head.split(" ")[0].lower() in ignore


def _has_message(error: str) -> bool:
    return any(
        line.strip() and not line.startswith("Exit code") for line in error.splitlines()
    )


def capture(
    vault: Vault, tool: str, command: str, error: str, agent: str = "main"
) -> CaptureResult | None:
    """Record a failed command. None when capture is off or the command is ignored."""
    cfg = vault.config.capture
    if not cfg.enabled or (tool == "Bash" and ignored(vault, command)):
        return None
    if not _has_message(error):  # a bare "Exit code 1" carries nothing to learn from
        return None
    if cfg.redact:
        command = redact(command, cfg.extra_secret_patterns)
        error = redact(error, cfg.extra_secret_patterns)
    error = error[: cfg.max_output_chars]
    sig = signature(tool, command, error)
    index = load_failures(vault)
    first = index.failures.get(sig)
    lessons = tuple(lesson.title for lesson in index.lessons_for(sig))

    counts = dict(index.counts)
    entry = dict(counts.get(sig, {"count": 0, "after_lesson": 0}))
    entry["count"] = int(entry.get("count", 0)) + 1
    entry["last"] = datetime.now().astimezone().isoformat(timespec="seconds")
    if lessons:
        entry["after_lesson"] = int(entry.get("after_lesson", 0)) + 1
    counts[sig] = entry

    head = command_head(command)
    body = f"```\n$ {command}\n{error}\n```"
    extra = {"signature": sig, "tool": tool, "command_head": head}
    record_id = first.id if first is not None else ""
    if first is None:
        record_id = write_record(
            vault,
            Record(
                kind="failure",
                title=f"{head or tool}: {normalise_error(error)}"[:120],
                body=body,
                agent=agent,
                extra=extra,
            ),
        ).stem
    elif lessons:  # the lesson did not prevent it: that is evidence worth keeping
        record_id = write_record(
            vault,
            Record(
                kind="occurrence",
                title=f"again after lesson: {first.title}"[:120],
                body=body,
                agent=agent,
                refs=(first.id,),
                extra=extra,
            ),
        ).stem
    _save_counts(vault, counts)
    return CaptureResult(
        record_id=record_id, signature=sig, repeat=first is not None, lessons=lessons
    )


def resolve_failure_id(vault: Vault, ref: str) -> str:
    """Full failure id from an exact id or a unique prefix. Raises KeyError otherwise."""
    ids = [f.id for f in load_failures(vault).failures.values()]
    if ref in ids:
        return ref
    matches = [i for i in ids if i.startswith(ref)]
    if len(matches) == 1:
        return matches[0]
    if not matches:
        raise KeyError(f"no failure record matches {ref!r}; see `ledger failures`")
    raise KeyError(f"{ref!r} matches {len(matches)} failures; give more of the id")


def add_lesson(vault: Vault, failure_id: str, lesson: str, agent: str = "main") -> str:
    """Attach a one-line lesson to a failure record. Returns the lesson record id."""
    full = resolve_failure_id(vault, failure_id)
    return write_record(
        vault, Record(kind="lesson", title=lesson, agent=agent, refs=(full,))
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
    index = load_failures(vault)
    out = []
    for sig, first in index.failures.items():
        if first.header.get("command_head") != head:
            continue
        out.append(
            KnownFailure(
                failure_id=first.id,
                title=first.title,
                times=index.count(sig),
                lessons=tuple(lesson.title for lesson in index.lessons_for(sig)),
            )
        )
    return sorted(out, key=lambda k: (-bool(k.lessons), -k.times))[:limit]


def repeat_failure_rate(vault: Vault) -> float:
    """Share of failure events that happened after a lesson for them was recorded.

    Uses this machine's counters; where they are missing (another machine's records),
    the post-lesson ``occurrence`` records stand in, which undercounts but never
    invents repeats.
    """
    index = load_failures(vault)
    total = repeats = 0
    for sig in index.failures:
        counted = index.counts.get(sig)
        if counted:
            total += int(counted.get("count", 0))
            repeats += int(counted.get("after_lesson", 0))
        else:
            total += index.count(sig)
            repeats += len(index.occurrences.get(sig, []))
    return round(repeats / total, 4) if total else 0.0
