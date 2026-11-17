# CLAUDE.md

Read automatically at the start of every Claude Code session in this repository. It says
how the code is written here and what must never break. The state of the work and the
task queue are in [docs/HANDOFF.md](docs/HANDOFF.md); the target design is in
[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md); the feature list is in
[docs/ROADMAP.md](docs/ROADMAP.md).

## What this is

research-ledger keeps an Obsidian vault (or the docs of any project) trustworthy when
people and AI agents write it together: numbers name their sources, failed commands are
remembered and their lessons are shown before the same command runs again, task prompts
get a short ranked context pack, and quality metrics can only go up. It ships as a Python
CLI (`ledger`) and a Claude Code plugin (hooks + skills) that calls the CLI.

## Map

| Path | What lives there |
|---|---|
| `src/research_ledger/config.py` | `LedgerConfig` (pydantic): single source of truth for settings and constants |
| `corpus.py`, `graph.py` | reading notes, Obsidian link resolution, dangling links, orphans |
| `provenance.py`, `lifecycle.py` | numbers without a source, note lifecycle |
| `records.py` | append-only records, checked against git history |
| `failures.py`, `redact.py` | failure capture, secret masking, signatures, repeats, lessons |
| `search.py`, `index.py`, `context.py` | BM25 index and task context packs under a token budget |
| `audit.py`, `ratchet.py`, `generate.py` | all checks, the ratchet baseline, the `_health` page |
| `hooks.py` | Claude Code hook entry points (`ledger hook ...`) |
| `usage.py`, `feedback.py` | local hook statistics and bug reports |
| `scaffold.py`, `templates/` | `ledger init`, vault templates (en, uk) |
| `cli.py` | the `ledger` command |
| `plugin/` | Claude Code plugin: `hooks/hooks.json`, `skills/*/SKILL.md` |
| `.claude-plugin/marketplace.json` | plugin marketplace entry |
| `examples/demo-vault` | synthetic vault with exactly one planted problem of each kind |
| `tests/` | pytest; `test_corpus_graph.py` checks the audit finds exactly the planted problems |

## Commands

Same as CI (`.github/workflows/ci.yml`, Ubuntu and Windows, Python 3.11 and 3.13):

```bash
pip install -e ".[dev]"
ruff check .
ruff format --check .
pyright src
pytest -q
```

Run all five before saying a change is done.

## Code conventions

- `from __future__ import annotations` in every module; full type annotations on public
  functions; pyright clean. Prefer `Protocol` over `Any`.
- Settings and constants live in `LedgerConfig`, not in function bodies. A new constant
  is either a config field or a named module constant with a comment on where it comes
  from.
- Domain objects are frozen pydantic models or frozen dataclasses, not loose dicts.
- Docstrings say why and state the contract, not a line-by-line retelling.
- No side effects on import. Hooks and CLI entry points do the work.
- Every new check, parser or engine gets at least one test against a known answer, and
  the demo vault stays in sync with the checks.
- Code that generalises old behaviour must reproduce the old result exactly, and a test
  must show it.
- Style follows the neighbouring files. Ruff, line length 90.

## Product invariants (never break these)

1. **`init` never overwrites a file.** In an existing project everything the ledger adds
   lives under `ledger/`; machine state lives in `.ledger/` (git-ignored).
2. **Records are append-only** and checked against git history.
3. **Hooks never break the user's turn.** On any error they exit quietly and log to
   `.ledger/`; they are silent outside a folder with `ledger.toml` and when there is
   nothing to add.
4. **Everything runs locally.** Nothing is sent anywhere unless the user explicitly
   submits feedback.
5. **Secrets are masked** before anything about a failure is stored.
6. **The ratchet only moves in the good direction**; existing debt becomes the baseline
   instead of a wall of errors.
7. From [ARCHITECTURE.md](docs/ARCHITECTURE.md): a learned policy may decide what to
   show, never what to write; no LLM judge in any reward; shadow before live.

## Repository hygiene

- English in code, docs and commits. Ukrainian user docs end in `_UK.md`.
- No real vault content in the repo: examples and tests use synthetic notes only.
- Significant changes update `docs/ROADMAP.md` or `docs/ARCHITECTURE.md` in the same
  commit, and `docs/HANDOFF.md` when the state of the work changes.
- Commit and push only when the user asks. Commit as
  `MaksymSokolnytskyi <167302202+MaksymSokolnytskyi@users.noreply.github.com>` and end the
  message with a `Co-Authored-By` line for Claude.
- Numbers in docs come from a run, not from memory; say how they were measured.
