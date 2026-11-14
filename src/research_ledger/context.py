"""Task-context packs: what an agent should read before working on a task.

Instead of letting an agent wander the vault (or read all of it), the task text is
turned into a short, ranked pack under a token budget:

1. **Entities named in the task** -- notes whose name or alias appears verbatim. The
   strongest signal: the user said the word.
2. **Relevant notes** -- BM25 over note text, weighted by authority. A definition
   outranks a claim, a claim outranks a report, a report outranks a raw record, so a
   pack reads from "what this is" down to "what happened".
3. **Known failures** -- failure records whose text matches the task, with their
   lessons, so a known mistake is shown before it is repeated.

How eagerly a pack is attached to Claude Code prompts is ``context.inject``:
``relevant`` (any note clears ``min_score``), ``named`` (only when the prompt names a
vault entity or matches a known failure: quieter), or ``off``.
"""

from __future__ import annotations

import re
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from research_ledger.config import Vault
from research_ledger.corpus import in_folder, read_note, strip_blocks
from research_ledger.failures import load_failures
from research_ledger.index import IndexedNote, load_index
from research_ledger.search import BM25

CHARS_PER_TOKEN = 4
EXCERPT_CHARS = 600

# Authority by tier: tier 0-1 are curated reading, tier 3 is raw evidence.
_TIER_WEIGHT = {0: 1.6, 1: 1.4, 2: 1.0, 3: 0.7}
NAMED_BONUS = 10.0


class PackItem(BaseModel):
    model_config = ConfigDict(frozen=True)

    path: str
    title: str
    reason: str
    score: float
    excerpt: str


class ContextPack(BaseModel):
    model_config = ConfigDict(frozen=True)

    task: str
    items: tuple[PackItem, ...]
    failures: tuple[PackItem, ...]

    @property
    def empty(self) -> bool:
        return not self.items and not self.failures

    @property
    def names_an_entity(self) -> bool:
        return any(i.reason == "named in the task" for i in self.items)

    def render(self) -> str:
        if self.empty:
            return ""
        lines = ["<ledger-context>", f"Task: {self.task.strip()[:200]}", ""]
        if self.failures:
            lines.append("Known failures related to this task:")
            for f in self.failures:
                lines.append(f"- {f.title} ({f.path}) {f.excerpt}")
            lines.append("")
        if self.items:
            lines.append("Relevant notes, most authoritative first:")
            for item in self.items:
                lines.append(f"## {item.title}  [{item.path}] ({item.reason})")
                lines.append(item.excerpt)
                lines.append("")
        lines.append("</ledger-context>")
        return "\n".join(lines)


def _excerpt(
    vault: Vault, note: IndexedNote, query_terms: set[str], limit: int = EXCERPT_CHARS
) -> str:
    """The paragraph that best matches the task, not just the note's first lines.

    Read from disk here rather than cached: only the handful of notes that make it
    into a pack are ever shown.
    """
    try:
        body = read_note(vault, Path(note.path)).body
    except OSError:
        return ""
    paragraphs = [
        p.strip() for p in re.split(r"\n\s*\n", strip_blocks(body)) if p.strip()
    ]
    paragraphs = [p for p in paragraphs if not p.startswith("# ")] or paragraphs
    if not paragraphs:
        return ""
    best = max(paragraphs, key=lambda p: sum(t in p.lower() for t in query_terms))
    text = " ".join(best.split())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def _weight(note: IndexedNote, definitions: str) -> float:
    weight = _TIER_WEIGHT.get(note.tier if note.tier is not None else 2, 1.0)
    if in_folder(note.path, definitions):
        weight *= 1.5
    if note.lifecycle == "closed":
        weight *= 0.3
    return weight


def _named(note: IndexedNote, lowered_task: str) -> bool:
    names = {note.stem.lower(), *(a.lower() for a in note.aliases)}
    return any(
        len(n) > 2 and re.search(rf"(?<!\w){re.escape(n)}(?!\w)", lowered_task)
        for n in names
    )


def build_context(
    vault: Vault,
    task: str,
    budget_tokens: int | None = None,
    max_notes: int | None = None,
    relative_cutoff: float = 0.0,
) -> ContextPack:
    """Rank notes for ``task``. ``relative_cutoff`` drops notes scoring below that share
    of the best one: specific tasks have a clear leader and a long weak tail."""
    cfg = vault.config
    budget = (budget_tokens or cfg.context.budget_tokens) * CHARS_PER_TOKEN
    lowered = task.lower()
    terms = set(re.findall(r"[^\W_]{3,}", lowered))
    index = load_index(vault)

    def eligible(n: IndexedNote) -> bool:
        return not n.generated and not in_folder(n.path, cfg.folders.records)

    notes = [n for n in index.notes if eligible(n)]
    scored: dict[str, tuple[float, str, IndexedNote]] = {}
    for i, score in index.postings.rank(task):
        note = index.notes[i]
        if eligible(note):
            weighted = score * _weight(note, cfg.folders.definitions)
            if weighted >= cfg.context.min_score:
                scored[note.path] = (weighted, "matches the task", note)
    for note in notes:
        if _named(note, lowered):
            previous = scored.get(note.path, (0.0, "", note))[0]
            scored[note.path] = (previous + NAMED_BONUS, "named in the task", note)

    ranked = sorted(scored.items(), key=lambda kv: -kv[1][0])
    if ranked and relative_cutoff:
        best = ranked[0][1][0]
        ranked = [
            kv
            for kv in ranked
            if kv[1][0] >= relative_cutoff * best or kv[1][1] == "named in the task"
        ]
    if max_notes is not None:
        ranked = ranked[:max_notes]
    items: list[PackItem] = []
    used = 0
    for path, (score, reason, note) in ranked:
        excerpt = _excerpt(vault, note, terms)
        cost = len(excerpt) + len(note.title) + 40
        if used + cost > budget:
            break
        used += cost
        items.append(
            PackItem(
                path=path,
                title=note.title,
                reason=reason,
                score=round(score, 2),
                excerpt=excerpt,
            )
        )
    return ContextPack(
        task=task, items=tuple(items), failures=_failure_items(vault, task)
    )


def _failure_items(vault: Vault, task: str) -> tuple[PackItem, ...]:
    index = load_failures(vault)
    entries = list(index.failures.items())
    if not entries:
        return ()
    bm25 = BM25([f"{rec.title}\n{rec.body}" for _, rec in entries])
    out = []
    for i, score in bm25.rank(task)[:3]:
        if score < vault.config.context.min_score:
            continue
        sig, rec = entries[i]
        lessons = [lesson.title for lesson in index.lessons_for(sig)]
        text = f"Lesson: {'; '.join(lessons)}" if lessons else "No lesson recorded yet."
        out.append(
            PackItem(
                path=rec.path.as_posix(),
                title=rec.title,
                reason=f"seen {index.count(sig)}x",
                score=round(score, 2),
                excerpt=text,
            )
        )
    return tuple(out)


def pack_for_prompt(vault: Vault, prompt: str) -> str:
    """What the prompt hook attaches, honouring ``context.inject``."""
    mode = vault.config.context.inject
    if mode == "off" or len(prompt.strip()) < 12:
        return ""
    ctx = vault.config.context
    pack = build_context(
        vault,
        prompt,
        budget_tokens=ctx.prompt_budget_tokens,
        max_notes=ctx.prompt_max_notes,
        relative_cutoff=ctx.prompt_relative_cutoff,
    )
    if mode == "named" and not (pack.names_an_entity or pack.failures):
        return ""
    return pack.render()
