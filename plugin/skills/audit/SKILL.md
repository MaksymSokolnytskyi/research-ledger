---
name: audit
description: Run the research-ledger audit, explain what got worse, and fix the most important problems properly. Use when the user asks to check, audit or clean up a ledger vault.
---

# Audit a research ledger

1. Run `ledger audit --check` from the vault (it writes nothing) and read the metrics.
   Lines marked `WORSE` are ratchet regressions against the stored baseline.
2. Open `_generated/_health.md` (or run `ledger audit` without `--check` to refresh it)
   for the concrete list behind each number.
3. Fix in this order, because each one hides the next:
   1. invalid frontmatter (the note's other checks cannot run);
   2. dangling links (create the missing note only if it should exist; otherwise fix
      the link);
   3. numbers without a source (find the record, log or URL; if none exists, say so
      in the text instead of inventing one);
   4. orphans (link from the note that should lead here, or archive);
   5. missing lifecycle.
4. Never change a number to make a check pass, and never edit records (the `records/` folder, or `ledger/records/` in an adopted project).
5. Run `ledger audit` (without `--check`) to record the pass. If a regression is
   deliberate, explain why in a `ledger record decision ...` and only then run
   `ledger audit --adopt`.
6. Report what changed in each metric, and anything you could not fix and why.
