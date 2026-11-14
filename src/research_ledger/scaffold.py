"""``ledger init``: make a folder a ledger, without touching what is already there.

The same command serves a new vault and an existing project (a repository with docs,
an Obsidian vault in use). The rule that makes the second case safe: **create, never
overwrite**. Every file is written only if absent, and the plan is reported before
anything happens.

* ``ledger.toml`` -- configuration (language, folders, capture, ratchet).
* ``.ledger/`` -- machine state; suggested for ``.gitignore``.
* Starter notes (``_home``, ``LEDGER``) and note templates -- only in a new vault, or
  with ``--with-notes``.
* ``.obsidian/`` settings -- only if the folder has no ``.obsidian/`` yet. An existing
  vault keeps its own settings; the CSS snippet is added beside them, since a new
  file in ``snippets/`` changes nothing until it is switched on.

On an existing project the current state is adopted as the ratchet's baseline, so
existing debt does not block anyone, and from then on it may only shrink.
"""

from __future__ import annotations

from datetime import date
from importlib import resources
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from research_ledger.config import CONFIG_NAME, STATE_DIR, Language

GITIGNORE_LINE = f"{STATE_DIR}/"


class PlannedFile(BaseModel):
    model_config = ConfigDict(frozen=True)

    path: Path
    content: str
    reason: str


def _template(*parts: str) -> str:
    node = resources.files("research_ledger").joinpath("templates", *parts)
    return node.read_text(encoding="utf-8")


def _vault_files(language: Language) -> list[tuple[str, str]]:
    root = resources.files("research_ledger").joinpath("templates", "vault", language)
    out = []
    for name in ("_home.md", "LEDGER.md"):
        out.append((name, root.joinpath(name).read_text(encoding="utf-8")))
    for item in root.joinpath("templates").iterdir():
        if item.name.endswith(".md"):
            out.append((f"templates/{item.name}", item.read_text(encoding="utf-8")))
    return out


def plan(
    root: Path,
    name: str,
    language: Language = "en",
    existing: bool | None = None,
    with_notes: bool | None = None,
) -> tuple[list[PlannedFile], list[str]]:
    """Files to create and notes for the user. Nothing is written here.

    ``existing`` defaults to "the folder already contains Markdown files".
    """
    has_markdown = any(root.rglob("*.md")) if root.exists() else False
    existing = has_markdown if existing is None else existing
    with_notes = (not existing) if with_notes is None else with_notes
    today = date.today().isoformat()
    files: list[PlannedFile] = []
    notes: list[str] = []

    config = _template("ledger.toml").replace('name = "my-research"', f'name = "{name}"')
    config = config.replace('language = "en"', f'language = "{language}"')
    files.append(
        PlannedFile(path=root / CONFIG_NAME, content=config, reason="configuration")
    )

    if with_notes:
        for rel, text in _vault_files(language):
            if not rel.startswith("templates/"):
                text = text.replace("{today}", today).replace("{name}", name)
            files.append(
                PlannedFile(path=root / rel, content=text, reason="starter note")
            )

    obsidian = root / ".obsidian"
    if not obsidian.exists():
        for rel in (
            "app.json",
            "core-plugins.json",
            "templates.json",
            "appearance.json",
            "webviewer.json",
        ):
            files.append(
                PlannedFile(
                    path=obsidian / rel,
                    content=_template("obsidian", rel),
                    reason="Obsidian settings",
                )
            )
    else:
        notes.append(
            "Existing .obsidian/ kept as is. Enable the 'ledger' CSS snippet in "
            "Settings -> Appearance -> CSS snippets if you want it."
        )
    files.append(
        PlannedFile(
            path=obsidian / "snippets" / "ledger.css",
            content=_template("obsidian", "snippets", "ledger.css"),
            reason="CSS snippet",
        )
    )

    gitignore = root / ".gitignore"
    if (root / ".git").exists() and (
        not gitignore.is_file()
        or GITIGNORE_LINE not in gitignore.read_text(encoding="utf-8")
    ):
        notes.append(f"Add `{GITIGNORE_LINE}` to .gitignore (machine state, not notes).")
    if (root / "CLAUDE.md").is_file():
        notes.append(
            "CLAUDE.md left untouched; the Claude Code plugin brings the ledger's hooks "
            "and skills without editing it."
        )
    if existing:
        notes.append("Existing project: the current audit becomes the ratchet baseline.")
    return [f for f in files if not f.path.exists()], notes


def apply(files: list[PlannedFile]) -> list[Path]:
    written = []
    for f in files:
        f.path.parent.mkdir(parents=True, exist_ok=True)
        with open(f.path, "x", encoding="utf-8") as out:  # never overwrite
            out.write(f.content)
        written.append(f.path)
    return written
