---
name: ledger
description: Rules and commands for working inside a research ledger (a folder or Obsidian vault with ledger.toml). Use whenever you read, write or change notes, numbers or records in such a folder.
---

# Working in a research ledger

A folder with `ledger.toml` is a research ledger: Markdown notes kept trustworthy by
`ledger audit`. Follow these rules when you edit it.

1. **Every number names its source.** Put a link to the record, log, script or URL in
   the same paragraph or table row, or list it under `runs:` / `sources:` in the
   frontmatter. Never type a number from memory.
2. **Claims about code name a test** in `checks:` (`tests/test_x.py::test_y`).
3. **Records (folder `records/`, or `ledger/records/` in an adopted project) are append-only.** Never edit or
   delete one. To correct a record, write a new one with `--ref <old-id>`.
4. **Generated pages** (`generated: true` in frontmatter) are rewritten by tools. Do
   not edit them; change their source and run `ledger audit`.
5. **Every new note declares** `lifecycle:` (`living` | `snapshot` | `closed`) and
   `expires_when:`; living notes also `last_verified:`.
6. **Link the first mention** of a defined entity (`[[name]]`), not every mention.

## Commands

| goal | command |
|---|---|
| background for a task | `ledger context "<task>"` |
| log what you ran or decided | `ledger record run "<title>" --body "..." --source <log or url>` |
| after fixing a recorded failure | `ledger lesson <failure-id> "<one line: cause and fix>"` |
| what failed before for a command | `ledger failures --command "<command>"` |
| check the vault | `ledger audit --check` |

Failed shell commands are captured automatically by the plugin's hooks, with secrets
masked. When a context block says a command failed before, read its lesson first.

## Do not game the ratchet

The audit counts dangling links, orphans, unsourced numbers and missing lifecycles.
Fix the cause, never the count: do not add links nobody would follow, cite a source
that does not contain the number, or mark a note `closed` to hide it.
