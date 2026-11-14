---
tier: 2
lifecycle: living
expires_when: "when the judging setup changes"
last_verified: 2099-01-01
aliases: [LLM judge]
---

# judge

The model that scores a generated text against a rubric and returns
`{"score", "feedback"}`. Its verdict is derived from the score, never from a flag the
model sets itself. Results that depend on it: [[verdict-drift]].
