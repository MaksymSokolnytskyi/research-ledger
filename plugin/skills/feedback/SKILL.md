---
name: feedback
description: Send a bug report, idea or comment about research-ledger to its author, with diagnostics attached. Use when the user complains about the ledger, says something about it is noisy, broken or missing, or asks to report or suggest something.
---

# Report feedback about research-ledger

1. Decide the kind: `bug` (something broke or misbehaved), `idea` (a wish), or
   `comment` (anything else, including "this was noisy" or "this helped").
2. Write the message in the user's own words, plus what you observed in this session
   that matters (the command, the hook output that seemed wrong). Do not include note
   contents, file contents, prompts or anything secret.
3. Run `ledger feedback --kind <kind> -m "<message>"` and show the user the full report
   it prints. It contains only versions, counts and redacted hook errors.
4. Ask the user whether to file it. Only after an explicit yes:
   - if `gh` is installed and logged in: `ledger feedback --kind <kind> -m "<message>" --submit`;
   - otherwise give them the link the command printed; they submit it on GitHub.
5. Never submit without that yes.
