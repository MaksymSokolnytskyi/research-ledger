---
kind: run
agent: lab
when: '2026-03-02T10:15:00+02:00'
tier: 3
numbers:
  judge_calls: {value: 810, source: runs/pilot/judgments.jsonl}
  cache_hits: {value: 412, source: runs/pilot/cache_stats.json}
---

# Pilot judge run with cache

`python run_pilot.py --cache` over 270 generations x 3 judges.
