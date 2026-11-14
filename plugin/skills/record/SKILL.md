---
name: record
description: Write an append-only record of a run, decision, research finding or agent call in a research ledger. Use after running an experiment, making a design decision, or gathering external facts.
---

# Write a record

Records are history, kept apart from notes (current truth). They are never edited.

- Experiment or script run: `ledger record run "<what ran>" --body "<command, key numbers, where the output is>" --source <log path>`
- Decision: `ledger record decision "<choice>" --body "<context, options, why, what we gave up>"`
- External findings: `ledger record research "<question>" --body "<answer in your words>" --source <url> --source <url>` (every URL actually used)
- Correction of an earlier record: write a new one with `--ref <old-record-id>`.

Every number in a record body needs its source in the same record. Then link the record
from the note that uses its result, so the number in the note is sourced too.
