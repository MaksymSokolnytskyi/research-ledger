# research-ledger

Provenance, failure memory and a quality ratchet for Obsidian vaults that people and
AI agents write together.

An LLM can maintain a research wiki. The open problem is whether you can **trust**
what it maintains. research-ledger treats a vault like a codebase under CI:

- **every number names its source** (a run record, a log, a script, a URL), and the
  audit counts the ones that do not;
- **what happened is kept apart from what is true**: notes are edited freely, records
  are append-only and checked against git history;
- **failures are remembered**: a failed command is captured automatically (secrets
  masked), recognised when it happens again, and its lesson is shown to the agent
  *before* the same command runs next time;
- **the agent gets the right context**: a task prompt is turned into a short, ranked
  pack of relevant notes and known failures under a token budget;
- **quality can only go up**: guarded metrics are compared with a baseline that only
  moves in the good direction.

It works on a new vault and on an existing project: `init` never overwrites a file, and
existing debt becomes the starting baseline instead of a wall of errors.

## Install

```bash
pip install "git+https://github.com/MaksymSokolnytskyi/research-ledger"
```

Then, for Claude Code (hooks and skills; inert in folders without `ledger.toml`):

```
/plugin install research-ledger --marketplace MaksymSokolnytskyi/research-ledger
```

or in a shell: `claude plugin marketplace add MaksymSokolnytskyi/research-ledger`
followed by `claude plugin install research-ledger@research-ledger`.

## Start

```bash
ledger init my-research --language en        # new vault (or --language uk)
ledger init . --existing --dry-run           # preview on an existing project
ledger init . --existing                     # adopt: current state = baseline
ledger audit                                 # checks + ratchet + _generated/_health.md
```

Open the folder in Obsidian. The `examples/demo-vault` folder shows every check with
one planted problem of each kind:

```
$ ledger audit --check --path examples/demo-vault
notes                                   11
dangling_links                           1
orphans                                  1
numbers_total                            8
numbers_unsourced                        1
lifecycle_missing                        1
failures                                 1
failures_without_lesson                  0
...
```

The planted problems: `verdict-drift` links to a missing `sampling-notes`; `old-plan`
is linked from nowhere and declares no lifecycle; "71.3%" has no source in its
paragraph; one recorded failure (`run_pilot.py`: connection refused) has its lesson.
`tests/test_corpus_graph.py` checks that the audit finds exactly these.

## What happens inside a Claude Code session

| hook | what it does | when it speaks |
|---|---|---|
| `SessionStart` | three-line brief: vault size, failures with no lesson | in a ledger |
| `UserPromptSubmit` | **task-context intake**: the prompt becomes a query; matching notes and known failures are attached | only if something clears the relevance threshold |
| `PreToolUse` (Bash) | known failures of the same command, with lessons | only if the command failed before |
| `PostToolUseFailure` (Bash) | captures the failure (redacted), detects repeats | on failure |

Skills: `/research-ledger:ledger` (rules), `:audit`, `:onboard`, `:record`.

The same functions are available as commands:

```bash
ledger context "why do judge verdicts flip between runs"
ledger record run "pilot with cache" --body "..." --source runs/pilot.log
ledger capture --command "pytest -q" --error - < err.txt
ledger lesson <failure-id> "start ollama serve before the pilot"
ledger failures --command "python run_pilot.py"
ledger serve                                  # live HTML/JS pages for <iframe> embeds
ledger doctor
```

## The checks

| metric | meaning | guarded |
|---|---|---|
| `dangling_links` | links to notes that do not exist (one click in Obsidian creates an empty impostor) | yes |
| `orphans` | notes nothing links to (records and entry points exempt) | yes |
| `numbers_unsourced_per_1k_words` | numbers with no link, URL or footnote in their paragraph or table row, and no `runs:`/`sources:` header | yes |
| `lifecycle_missing` | notes that do not declare `living` / `snapshot` / `closed` | yes |
| `repeat_failure_rate` | share of failures that happened again after a lesson existed: does the vault learn? | yes |
| `lifecycle_stale` | living notes not verified within `stale_after_days` | |
| `merge_candidates` | mutually linked notes sharing most neighbours: one topic cut in half | |
| `records_rewritten` | append-only records modified after commit (from git) | |

Number detection is a heuristic (decimals, percentages, integers of 3+ digits; dates,
years, versions and list ordinals skipped). Read it as a trend under the ratchet, not as
a verdict on one number. The rules themselves are in the `LEDGER.md` that `init`
writes into the vault.

## Design notes

- **Configuration in one file.** `ledger.toml` holds every folder name and threshold;
  nothing is hard-coded. Machine state lives in `.ledger/` (add it to `.gitignore`).
- **Checks return data, not text.** The audit's metrics dictionary is the interface;
  printing and page generation are separate, so rewording a message cannot break the
  ratchet.
- **Generated pages are not evidence.** Pages marked `generated: true` are skipped by
  every check: a report listing every orphan must not make those orphans reachable.
- **Hooks never break the turn.** Every error is swallowed and logged to
  `.ledger/hook_errors.log` (see `ledger doctor`).
- **Retrieval is BM25.** Technical vaults are queried by identifiers and numbers, where
  exact-term ranking wins and stays explainable. Vectors are planned as a second ranker.

Origin: extracted and generalised from the documentation tooling of a research project
(32 scripts, about 7,000 lines, tied to one vault and two agents). See
[docs/ROADMAP.md](docs/ROADMAP.md) for what comes next and [docs/OBSIDIAN.md](docs/OBSIDIAN.md)
for themes and live pages.

## Development

```bash
pip install -e ".[dev]"
pytest && ruff check . && pyright src
claude plugin validate .
```

MIT licence.
