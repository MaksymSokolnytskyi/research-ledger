# Roadmap

## Done in 0.1

Configuration, corpus and link resolution (Obsidian rules), dangling links, orphans,
merge candidates, number provenance, lifecycle, append-only records with git
integrity, failure memory (capture, redaction, signatures, repeats, lessons, recall),
BM25 task-context packs, ratchet with baseline adoption, `_health` page, safe `init` for
existing projects, Claude Code plugin (hooks + skills), English and Ukrainian vault
templates, demo vault.

## Next

The target these items serve is the learning loop in
[ARCHITECTURE.md](ARCHITECTURE.md): a hint is judged by its consequence.

1. **Research agents with provenance.** A provider interface with adapters for
   Perplexity (web search with citations), Gemini (long-context reading of a corpus),
   Anthropic and any OpenAI-compatible server (including Ollama). Keys come from the
   environment or a git-ignored `.env` (see `.env.example`). Every call is written as an
   `agent_call` record: model, prompt hash, tokens, cost, latency, and the URLs it
   cited, so a fact that came from an agent is sourced by construction. Facts enter as
   *unverified* and are promoted only after a check by a different model or a fetch of
   the cited page: a model must not grade its own claims.
2. **Inference control.** Per-day budgets, a prompt-hash cache, and routing by task
   type (search, long-context, cheap lint on a local model), all logged in the ledger.
3. **More of the original checks, generalised.** Claim checks (`checks:` test ids must
   exist and pass), formulas whose symbols are never defined, run matching (which log
   printed a document's numbers), blast radius (which notes rest on a run), tiers with
   word budgets, entity atlas pages, task board, language policy, and a trajectory view
   over the whole history.
4. **MCP server** exposing context packs, failure lookup and provenance as tools.
5. **Hybrid retrieval**: vectors as a second ranker beside BM25, for large corpora.
6. **Evaluation.** The same agent tasks with and without the ledger: repeated failures,
   tokens per task, and correctness of answers about the corpus.
