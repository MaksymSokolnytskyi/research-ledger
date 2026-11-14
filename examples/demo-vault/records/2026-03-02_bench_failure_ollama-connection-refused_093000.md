---
kind: failure
agent: bench
when: '2026-03-02T09:30:00+02:00'
tier: 3
signature: 0f3c2a9d1b7e
tool: Bash
command_head: run_pilot.py
---

# run_pilot.py: requests.exceptions.ConnectionError: Connection refused

```
$ python run_pilot.py --cache
requests.exceptions.ConnectionError: HTTPConnectionPool(host=<str>, port=<n>): Connection refused
```
