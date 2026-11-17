---
name: onboard
description: Set up research-ledger in a new or existing folder or Obsidian vault. Use when the user wants to start a ledger, add it to an existing project, or check the installation.
---

# Set up a research ledger

1. Check the CLI: `ledger --version`. If missing, install it with uv, which works
   without any Python knowledge and fetches a suitable Python by itself:
   - if `uv --version` fails, install uv first (macOS/Linux:
     `curl -LsSf https://astral.sh/uv/install.sh | sh`; Windows PowerShell:
     `powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"`);
   - `uv tool install "git+https://github.com/MaksymSokolnytskyi/research-ledger"`;
   - if `ledger` is still not found, run `uv tool update-shell` and ask the user to open a
     new terminal.
   For a user who already works with Python, `pip install` or `pipx install` with the
   same URL is fine. Ask before installing anything.
2. Preview, then initialise. `init` never overwrites a file:
   - new vault: `ledger init <folder> --name "<name>" [--language uk] --dry-run`, then
     the same without `--dry-run`;
   - existing project or vault: add `--existing`. Existing notes, `.obsidian/`
     settings and `CLAUDE.md` are left untouched, and the current state becomes the
     ratchet baseline, so existing debt does not block anyone.
3. Suggest adding `.ledger/` to `.gitignore` (machine state).
4. Run `ledger audit --check` and summarise the starting point in plain words.
5. `ledger doctor` diagnoses the installation and shows recent hook errors.

Explain to the user what the hooks do: they add relevant notes and known failures to
prompts, and record failed commands with secrets masked. Capture can be switched off
with `[capture] enabled = false` in `ledger.toml`.
