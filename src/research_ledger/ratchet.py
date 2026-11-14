"""The ratchet: guarded metrics may improve, and may not get worse.

A check says how things are; it does not say they got worse. A metric that worsens by
one every pass never trips a threshold and still doubles in a month. So every audit is
compared with a stored baseline, and the baseline only ever moves in the good
direction (same idea as Betterer or a coverage ratchet).

Two details make it usable:

* **Density, not count**, for metrics that grow with the corpus: adding a page adds
  numbers, and forbidding that would forbid writing. Those metrics are stored per
  1000 words.
* **Adoption.** On an existing project the current debt becomes the baseline
  (``ledger audit --adopt``), so the ratchet stops things getting worse from day one
  without demanding that the backlog be cleared first.

A non-zero exit is a signal, not a lock: a deliberate regression is recorded with a
note and re-adopted.

State lives in ``.ledger/ratchet.json`` (baseline) and ``.ledger/history.jsonl``
(every pass), both machine-owned.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from research_ledger.config import Vault

RATCHET_FILE = "ratchet.json"
HISTORY_FILE = "history.jsonl"


class Change(BaseModel):
    model_config = ConfigDict(frozen=True)

    metric: str
    baseline: float
    current: float

    @property
    def worse(self) -> bool:
        return self.current > self.baseline

    @property
    def better(self) -> bool:
        return self.current < self.baseline


class RatchetResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    had_baseline: bool
    changes: tuple[Change, ...]

    @property
    def regressions(self) -> list[Change]:
        return [c for c in self.changes if c.worse]

    @property
    def improvements(self) -> list[Change]:
        return [c for c in self.changes if c.better]


def _paths(vault: Vault) -> tuple[Path, Path]:
    return vault.state_dir / RATCHET_FILE, vault.state_dir / HISTORY_FILE


def load_baseline(vault: Vault) -> dict[str, float]:
    path, _ = _paths(vault)
    if not path.is_file():
        return {}
    return {k: float(v) for k, v in json.loads(path.read_text(encoding="utf-8")).items()}


def compare(vault: Vault, metrics: dict[str, float]) -> RatchetResult:
    baseline = load_baseline(vault)
    changes = tuple(
        Change(metric=m, baseline=baseline[m], current=float(metrics[m]))
        for m in vault.config.ratchet.guarded
        if m in baseline and m in metrics
    )
    return RatchetResult(had_baseline=bool(baseline), changes=changes)


def record_pass(vault: Vault, metrics: dict[str, float], adopt: bool = False) -> None:
    """Append the pass to history and tighten (or, with ``adopt``, reset) the baseline.

    Tightening keeps ``min(baseline, current)`` per metric, so a regression never
    loosens the baseline; only ``adopt`` can, and that is an explicit decision.
    """
    ratchet_path, history_path = _paths(vault)
    vault.state_dir.mkdir(parents=True, exist_ok=True)
    guarded = {m: float(metrics[m]) for m in vault.config.ratchet.guarded if m in metrics}
    baseline = {} if adopt else load_baseline(vault)
    new = {m: min(v, baseline.get(m, v)) for m, v in guarded.items()}
    ratchet_path.write_text(json.dumps(new, indent=2, sort_keys=True), encoding="utf-8")
    entry = {"when": datetime.now().astimezone().isoformat(timespec="seconds"), **metrics}
    with open(history_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def history(vault: Vault) -> list[dict[str, float | str]]:
    _, path = _paths(vault)
    if not path.is_file():
        return []
    return [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line
    ]


def stalled(vault: Vault, window: int = 10) -> list[str]:
    """Guarded metrics, non-zero, that have not improved in the last ``window`` passes.

    The pairwise ratchet cannot see this: a metric frozen for twenty passes looks
    healthy pass to pass, and is in fact abandoned.
    """
    passes = history(vault)[-window:]
    if len(passes) < window:
        return []
    out = []
    for metric in vault.config.ratchet.guarded:
        values = [float(p[metric]) for p in passes if metric in p]
        if len(values) == window and values[-1] > 0 and min(values) >= values[0]:
            out.append(metric)
    return out
