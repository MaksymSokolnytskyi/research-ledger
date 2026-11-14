# Obsidian setup

`ledger init` writes `.obsidian/` settings only into a folder that has none. An existing
vault keeps its own settings; the `ledger` CSS snippet is added beside them and stays
off until you enable it (Settings -> Appearance -> CSS snippets).

## Core plugins switched on

Properties (frontmatter editing), Backlinks and Outgoing links, Graph, Templates
(folder `templates/`, holding definition, claim, decision and source templates),
Bases (tables over frontmatter: tier, lifecycle, last_verified), Canvas, Slides,
Web viewer, Footnotes, Page preview, Outline, Word count.

## Themes

Themes are not shipped in this repository: they belong to their authors. Install any
from Settings -> Appearance -> Themes -> Manage. All of these work with the `ledger`
snippet, which only uses the theme's own colour variables:

- **Minimal** (kepano): quiet, highly configurable with its companion plugin;
- **Primary**: high-contrast reading;
- **Typomagical**: book-like typography for long notes;
- **Obsidian gruvbox** / **Material Gruvbox**: warm, low-glare palettes;
- **Things**: clean, colourful headings;
- **AnuPpuccin**: many colour schemes, good for dark mode.

## Live HTML and JavaScript pages

Obsidian does not run a local `.html` file inside a note, but it does render an
`<iframe>` in reading view. Run

```bash
ledger serve            # http://127.0.0.1:8765/ serves the vault folder
```

and embed a page from the vault in any note:

```html
<iframe src="http://127.0.0.1:8765/demo/dashboard.html"></iframe>
```

The demo vault's `notes/run-dashboard.md` does exactly this. The Web viewer core plugin
opens ordinary links (including `http://127.0.0.1:8765/...`) in an Obsidian tab.

## Syncing across machines

Records are one file per event with collision-free names, so two machines never write
the same file. Generated pages (`_generated/`, `atlas/`) are rewritten by `ledger
audit`; let one machine regenerate them, or exclude them from sync, to avoid conflicts.
