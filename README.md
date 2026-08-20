# Local Dev Tools

A small collection of local developer utilities that launch from the terminal:

- `mdp` — Markdown editor and live previewer
- `dct` — side-by-side text diff checker
- `df` — technology-first definition finder

The desktop tools work entirely on local files. They normally detach from the terminal after launch so you can keep using that terminal session. Add `--debug` when you want the app to remain attached and print startup errors in the terminal.

## Requirements and installation

Install [uv](https://docs.astral.sh/uv/) first. The two desktop apps require Python 3.12+ with Tk support.

### macOS (Apple Silicon)

The uv-managed Python 3.13 runtime may not include a compatible Tk installation on macOS. Use Homebrew's Python 3.12 plus its Tk package for this tool:

```sh
brew install python-tk@3.12

/opt/homebrew/opt/python@3.12/bin/python3.12 -c "import tkinter; print(tkinter.TkVersion)"

uv tool install --editable \
  --python /opt/homebrew/opt/python@3.12/bin/python3.12 \
  .
```

If you rebuild or reinstall this tool environment later, include the same `--python` argument:

```sh
uv tool install --editable --reinstall \
  --python /opt/homebrew/opt/python@3.12/bin/python3.12 \
  .
```

With the editable installation above, ordinary changes under `src/` take effect the next time you launch a tool—no reinstall is needed.

### Windows

Install Python 3.12+ with Tk support (the standard Python installer normally includes it), then install the tools from this project folder:

```powershell
uv tool install --editable .
```

For a Windows rebuild, use:

```powershell
uv tool install --editable --reinstall .
```

### Linux

Install Python 3.12+ and its Tk bindings (often named `python3-tk`), then run:

```sh
uv tool install --editable .
```

## Markdown Previewer (`mdp`)

`mdp` is a small Markdown editor and previewer. Its source editor is on the left; its live, readable preview is on the right.

### Launch examples

```sh
# Open one document.
mdp README.md

# Open several documents, one tab each.
mdp README.md docs/notes.md docs/plan.md

# Open a blank document.
mdp

# Keep the app attached to the terminal and show startup errors.
mdp --debug README.md
```

### Features

- Open, edit, save, Save As, and close independent Markdown document tabs.
- Open several Markdown files directly from the command line.
- Drag a Markdown file onto the app to open it in a new tab.
- Drag tabs to rearrange them.
- Live rendering for headings, lists, quotes, code blocks, emphasis, links, horizontal rules, and tables.
- Preview Only mode hides the Markdown editor until you choose **Show Markdown**.
- Optional **Sync Scroll** keeps the editor and preview at matching relative positions.
- Light, dark, and sepia themes, plus adjustable text size.
- Standard editing shortcuts on both platforms: Ctrl on Windows and Command on macOS.
- Ctrl/Command+W closes the current tab; when it is the final tab, the app closes.
- No file content is uploaded anywhere.

### App icon

Place a square PNG at `src/mdp/assets/icon.png`. With an editable install, relaunch `mdp` to use it. With a non-editable install, reinstall the tool afterward. Tk uses it as the window icon and, where supported, the Dock or task-switcher icon.

## Diff Checker Tool (`dct`)

`dct` compares local text files side by side. It is useful for quick code, configuration, and document comparisons without opening a browser or a full IDE.

### Launch examples

```sh
# Compare two files.
dct path/to/before-file.py path/to/after-file.py

# Start with a blank comparison, then choose or drop files into the panes.
dct

# Keep the app attached to the terminal and show startup errors.
dct --debug path/to/before-file.py path/to/after-file.py
```

### Features

- Side-by-side comparison with line numbers and highlighting for added, removed, and changed lines.
- Multiple comparison tabs that can be reordered by dragging.
- Drag a file onto the left or right pane to replace that side of the active comparison.
- **Choose…** buttons above each pane for file selection.
- **Edit** controls above both source panes. The two files can be edited at the same time; choose **Done Editing** on either pane to save changes to its underlying file, discard them, or keep editing. Saved edits refresh the diff immediately.
- Source and merged-result editors support native undo/redo shortcuts: Ctrl+Z / Ctrl+Shift+Z on Windows and Command+Z / Command+Shift+Z on macOS.
- Optional **Merged View** adds a center pane. One-sided changes are included, while incompatible replacements remain explicit conflict blocks for review. You can edit that result and use **Save As…** to export it to a file you choose.
- Light, dark, and sepia themes, plus adjustable text size.
- Ctrl/Command+W closes the current tab; when it is the final tab, the app closes.
- No file content is uploaded anywhere.

### App icon

Optionally place a square PNG at `src/dct/assets/icon.png`. If it is absent or invalid, `dct` starts normally with the platform's default icon.

## Definition Finder (`df`)

`df` is a compact, technology-first dictionary for the terminal. It includes 147,982 concise WordNet-derived local definitions in a 3.9 MB compressed glossary, with preferred definitions for common software and data terms. When a term is absent locally, it can use the no-key [Free Dictionary API](https://dictionaryapi.dev/) and cache a successful result for future lookups.

```sh
df determinism
df idempotency
df apple
```

WordNet attribution is included at `src/df/assets/WORDNET-ATTRIBUTION.md`.

`df` is terminal-only, so it does not have a desktop-window, Dock, or task-switcher icon.
