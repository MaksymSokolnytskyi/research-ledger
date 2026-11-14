---
tier: 1
lifecycle: living
expires_when: "when the ledger's rules change"
last_verified: {today}
---

# How this vault works

This vault is a research ledger: notes are maintained by people and agents, and
`ledger audit` checks that they stay trustworthy. Ten rules, each with the check that
enforces it.

## 1. A number names its source

A number without a written origin cannot be reproduced. Put a link to the record,
run log, script or URL in the same paragraph or table row, or declare `runs:` /
`sources:` in the note's header. *Check: unsourced numbers per thousand words.*

## 2. A claim about code names a test

`checks: [tests/test_x.py::test_y]` in the header. The test must exist and pass;
code can be run, so this kind of claim is the cheapest one to verify.

## 3. Every note declares how it ends

```yaml
lifecycle: living | snapshot | closed
expires_when: "the condition under which it stops being current"
last_verified: 2026-01-31   # living notes only
```

A snapshot is finished at birth and never edited, only superseded. A living note is
re-verified. A closed note goes to `archive/`. *Check: missing or stale lifecycle.*

## 4. Define once, link the first mention

One note per entity in `def/`. Link its first mention in each note and leave the rest
as plain words. A page where every noun is a link is unreadable.

## 5. A note nothing links to does not exist

Orphans rot while looking authoritative. Link it from somewhere, or archive it.
*Check: orphans, dangling links.*

## 6. Generated pages are not edited and are not evidence

Pages with `generated: true` are rewritten by the tools. They are skipped by every
check, because a report is not evidence about the corpus it reports on.

## 7. What happened is kept apart from what is true

Notes hold current truth and are edited freely. Records in `logs/` hold history and
are **never edited**: a correction is a new record that references the old one.
*Check: records modified after commit.*

## 8. Failures are remembered

Failed commands are captured automatically (secrets masked). When you fix one, record
the lesson: `ledger lesson <failure-id> "one line"`. *Check: repeat-failure rate, the
share of failures that happened again after a lesson existed.*

## 9. Reading has tiers

| tier | what | rule |
|---|---|---|
| 0 | one page: what was asked, what came out | self-contained |
| 1 | a few topic pages | readable without tier 2 |
| 2 | reports and tracks | never required |
| 3 | records, registry, generated pages | evidence, not reading |

## 10. The ratchet

`ledger audit` compares guarded metrics with the stored baseline. They may improve and
may not get worse. A deliberate regression is written down and re-adopted with
`ledger audit --adopt`.
