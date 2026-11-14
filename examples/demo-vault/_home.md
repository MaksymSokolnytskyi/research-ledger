---
tier: 0
lifecycle: living
expires_when: "never: entry point"
last_verified: 2099-01-01
---

# Demo: does caching LLM-judge calls change the verdicts?

A small vault that exercises every check. The question: if identical judge prompts
are answered from a cache, do pass rates move? Results so far are in
[[cache-hit-rate]] and [[verdict-drift]]; the terms are defined in [[judge]] and
[[prompt-hash]]. A live chart of the run is embedded in [[run-dashboard]].
