"""Local usage statistics: what the hooks did, kept on this machine only.

Every hook call appends one line to ``.ledger/usage.jsonl``: event, latency, how many
characters it added to the conversation, and the outcome. Nothing is sent anywhere.
``ledger feedback`` summarises it, so a beta tester's report can say "the prompt hook
spoke on 40 of 120 prompts, median 80 ms" instead of "it felt noisy".

No prompt text, note text or command is stored here, only counts.
"""

from __future__ import annotations

import json
import statistics
from collections import defaultdict
from datetime import datetime

from research_ledger.config import Vault

USAGE_FILE = "usage.jsonl"


def log_event(vault: Vault, event: str, ms: float, chars: int, outcome: str) -> None:
    try:
        vault.state_dir.mkdir(parents=True, exist_ok=True)
        line = {
            "when": datetime.now().astimezone().isoformat(timespec="seconds"),
            "event": event,
            "ms": round(ms, 1),
            "chars": chars,
            "outcome": outcome,
        }
        with open(vault.state_dir / USAGE_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(line) + "\n")
    except OSError:
        pass


def summary(vault: Vault) -> dict[str, dict[str, float | int]]:
    """Per event: calls, how often it spoke, median and p95 latency, characters added."""
    path = vault.state_dir / USAGE_FILE
    if not path.is_file():
        return {}
    rows: dict[str, list[dict[str, float | int | str]]] = defaultdict(list)
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            row = json.loads(line)
        except ValueError:
            continue
        rows[str(row.get("event"))].append(row)
    out: dict[str, dict[str, float | int]] = {}
    for event, items in sorted(rows.items()):
        ms = sorted(float(r.get("ms", 0)) for r in items)
        out[event] = {
            "calls": len(items),
            "spoke": sum(int(r.get("chars", 0)) > 0 for r in items),
            "errors": sum(r.get("outcome") == "error" for r in items),
            "median_ms": round(statistics.median(ms), 1),
            "p95_ms": round(ms[min(len(ms) - 1, int(0.95 * len(ms)))], 1),
            "chars_added": sum(int(r.get("chars", 0)) for r in items),
        }
    return out
