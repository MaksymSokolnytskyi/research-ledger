"""Task-context packs: what an agent should read before working on a task.

Instead of letting an agent wander the vault (or read all of it), the task text is
turned into a short, ranked pack under a token budget:

1. **Entities named in the task** -- notes whose name or alias appears verbatim. The
   strongest signal: the user said the word.
2. **Relevant notes** -- BM25 over note text, boosted by authority. A definition
   outranks a claim, a claim outranks a report, a report outranks a raw record, so a
   pack reads from "what this is" down to "what happened".
3. **Known failures** -- failure records whose text matches the task, with their
   lessons, so a known mistake is shown before it is repeated.

The pack is silent when nothing clears ``context.min_score``: a briefing printed on
every prompt stops being read, and then the one that mattered is missed too.
"""

from __future__ import annotations

import re

from pydantic import BaseModel, ConfigDict

from research_ledger.corpus import Corpus, Note, strip_blocks
from research_ledger.failures import load_index
from research_ledger.search import BM25

CHARS_PER_TOKEN = 4
EXCERPT_CHARS = 600

# Authority by tier: tier 0-1 are curated reading, tier 3 is raw evidence.
_TIER_WEIGHT = {0: 1.6, 1: 1.4, 2: 1.0, 3: 0.7}


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


def _excerpt(note: Note, query_terms: set[str], limit: int = EXCERPT_CHARS) -> str:
    """The paragraph that best matches the task, not just the note's first lines."""
    text = strip_blocks(note.body)
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    paragraphs = [p for p in paragraphs if not p.startswith("# ")] or paragraphs
    if not paragraphs:
        return ""

    def overlap(p: str) -> int:
        return sum(term in p.lower() for term in query_terms)

    best = max(paragraphs, key=overlap)
    text = " ".join(best.split())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def _weight(note: Note, definitions: str) -> float:
    tier = note.frontmatter.tier if note.frontmatter.tier is not None else 2
    weight = _TIER_WEIGHT.get(tier, 1.0)
    if note.path.parts[:1] == (definitions,):
        weight *= 1.5
    if note.frontmatter.lifecycle == "closed":
        weight *= 0.3
    return weight


def build_context(
    corpus: Corpus, task: str, budget_tokens: int | None = None
) -> ContextPack:
    cfg = corpus.vault.config
    budget = (budget_tokens or cfg.context.budget_tokens) * CHARS_PER_TOKEN
    lowered = task.lower()
    terms = {t for t in re.findall(r"[^\W_]{3,}", lowered)}
    records_dir = cfg.folders.records
    notes = [
        n for n in corpus.notes if not n.generated and n.path.parts[:1] != (records_dir,)
    ]

    # 1. entities named verbatim in the task
    named: dict[str, float] = {}
    for note in notes:
        names = {note.stem.lower(), *(a.lower() for a in note.frontmatter.aliases)}
        if any(
            len(n) > 2 and re.search(rf"(?<!\w){re.escape(n)}(?!\w)", lowered)
            for n in names
        ):
            named[note.path.as_posix()] = 10.0

    # 2. BM25, weighted by authority
    index = BM25([f"{n.title}\n{n.stem}\n{n.prose}" for n in notes])
    scored: dict[str, tuple[float, str, Note]] = {}
    for i, score in index.rank(task):
        note = notes[i]
        weighted = score * _weight(note, cfg.folders.definitions)
        if weighted >= cfg.context.min_score:
            scored[note.path.as_posix()] = (weighted, "matches the task", note)
    for path, bonus in named.items():
        note = next(n for n in notes if n.path.as_posix() == path)
        previous = scored.get(path, (0.0, "", note))[0]
        scored[path] = (previous + bonus, "named in the task", note)

    items: list[PackItem] = []
    used = 0
    for path, (score, reason, note) in sorted(scored.items(), key=lambda kv: -kv[1][0]):
        excerpt = _excerpt(note, terms)
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

    # 3. failures whose text matches the task
    failure_index = load_index(corpus.vault)
    failure_records = list(failure_index.failures.items())
    failures: list[PackItem] = []
    if failure_records:
        fbm = BM25([f"{rec.title}\n{rec.body}" for _, rec in failure_records])
        for i, score in fbm.rank(task)[:3]:
            if score < cfg.context.min_score:
                continue
            sig, rec = failure_records[i]
            lessons = [lesson.title for lesson in failure_index.lessons_for(sig)]
            times = 1 + len(failure_index.occurrences.get(sig, []))
            lesson_text = (
                f"Lesson: {'; '.join(lessons)}" if lessons else "No lesson recorded yet."
            )
            failures.append(
                PackItem(
                    path=rec.path.as_posix(),
                    title=rec.title,
                    reason=f"seen {times}x",
                    score=round(score, 2),
                    excerpt=lesson_text,
                )
            )
    return ContextPack(task=task, items=tuple(items), failures=tuple(failures))
