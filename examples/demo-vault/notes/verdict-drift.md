---
tier: 1
lifecycle: snapshot
expires_when: "superseded by the full-dataset comparison"
runs: [2026-03-02_lab_run_pilot-judge-run-with-cache_101500]
---

# Verdict drift

With temperature 0.1 the [[judge]] gave a different pass/fail verdict on 23 of 398
uncached repeats (5.8%), so the cache freezes a verdict that would otherwise flip.
See also [[verdict-drift-appendix]] and [[sampling-notes]].
