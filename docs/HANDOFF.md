# Handoff: state of the work and what comes next

Written on 2026-11-17 to start a new Claude Code session on this repository. Read
[CLAUDE.md](../CLAUDE.md) first (conventions and invariants), then this file.
Update it when the state of the work changes.

## Where things stand

- **Version 0.1**, public repository, MIT. 51 tests; CI on Ubuntu and Windows, Python
  3.11 and 3.13 (ruff, ruff format, pyright, pytest).
- Everything in "Done in 0.1" of [ROADMAP.md](ROADMAP.md) works: audit, provenance,
  lifecycle, append-only records, failure memory, BM25 context packs, ratchet, safe
  `init` for existing projects, Claude Code plugin with hooks and skills.
- **Recent changes:**
  - `4eb63c8`: the identity of an unsourced number no longer depends on the line's text
    (it uses the words around the number), and `[[note\|alias]]` inside tables resolves.
    Replaying a real 61-commit vault history, spurious issue churn fell from 29.3% to
    6.4% (one 180-file restructure commit excluded).
  - `92e9080`: [ARCHITECTURE.md](ARCHITECTURE.md), the target learning loop with a
    verification checklist per component.
  - `b2100b8`: the project is open (no more closed beta); install leads with `uv`, so
    people who do not use Python can install it; the `onboard` skill installs the CLI
    the same way.
- **Users:** the author and one early user.

## Decisions already made

- English first, Ukrainian as an option (`--language uk`, `*_UK.md` docs).
- The vault is the single source of truth; nothing is exported from the repo into it.
- Third-party Obsidian themes are recommended in [OBSIDIAN.md](OBSIDIAN.md), never
  bundled.
- Research agents (Perplexity, Gemini and other providers, ROADMAP item 1) are deferred.
- Records stay append-only under the ratchet; a learned policy only chooses what to show.

## Task queue

In this order unless the user says otherwise.

1. **Install prompt in the README and QUICKSTART_UK.** A copy-paste block a user gives
   to any coding agent where nothing is installed yet: read the Install section, use uv
   (install it if missing), install the plugin, check `ledger --version`, ask before
   installing anything, then `ledger init . --existing --dry-run` and show the plan.
   Small; no new components.
2. **MCP server** (ROADMAP item 4). Expose the ledger as tools to any MCP client
   (Claude Desktop, Cursor, Claude Code), not only through hooks:
   - tools: context pack for a task; failure lookup for a command plus its lesson;
     source of a number in a note; audit summary; write a lesson (ask before writing);
   - a `ledger mcp` command over stdio, built on the official MCP Python SDK as an
     optional extra (`pip install "research-ledger[mcp]"`), so the core stays at two
     dependencies. Check the SDK's current API in its docs before writing code;
   - read-only by default; tools that write go through the same functions as the CLI,
     so the invariants hold;
   - tests that call each tool on the demo vault and compare with the CLI output;
   - docs: how to add it to Claude Desktop, and whether the plugin can bundle it (check
     the current Claude Code plugin docs).
3. **Success hook** (ARCHITECTURE component 1). `PostToolUse` on Bash with exit 0. When
   a command that failed earlier now succeeds, store the failure → fix pair (the diff
   between the two). Measure how many pairs a normal week produces before building on
   them.
4. **Hint log** (component 4). Record which notes and failures were attached, with what
   score, for which prompt hash and session, so outcomes can be joined to hints later.
5. **PPR retriever in shadow** (component 3). Personalised PageRank over wiki links,
   seeded by BM25 hits; log its choice beside BM25, do not show it yet.

Later: research agents with provenance (ROADMAP 1), LintBench (a benchmark of vault
upkeep built from git history and synthetic corruptions), evaluation of the ledger
itself (ROADMAP 6).

## Known gaps

- The uv install path is documented but not exercised in CI. First real check: someone
  who does not use Python installs it and reports where they got stuck.
- Dangling-link counts include links to targets outside the folders the ledger reads,
  so they are an upper bound in projects adopted with `--docs`.
- Repeat-failure counters live in `.ledger/` per machine; records and lessons sync with
  the vault.

## First prompt for the new session

```
Read CLAUDE.md and docs/HANDOFF.md. Start with task 1 from the queue (the install
prompt), run the full CI command set, and show me the diff before committing. Then
propose a design for task 2 (the MCP server): tools, their inputs and outputs, and
tests. Do not write the server code until I agree with the design.
```
