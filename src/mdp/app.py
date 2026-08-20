"""Native Tk application for editing and previewing Markdown files."""

from __future__ import annotations

import re
import tkinter as tk
import webbrowser
from dataclasses import dataclass
from pathlib import Path
from tkinter import filedialog, font, messagebox, ttk
from typing import Any

try:
    from tkinterdnd2 import DND_FILES as installed_dnd_files
    from tkinterdnd2 import TkinterDnD as installed_tkinter_dnd
except ImportError:
    # Drag-and-drop is optional so the previewer still works without tkinterdnd2.
    DND_FILES: str | None = None
    TkinterDnD: Any | None = None
else:
    DND_FILES = installed_dnd_files
    TkinterDnD = installed_tkinter_dnd


APP_NAME = "Markdown Previewer"
PREVIEW_DELAY_MS = 180
DEFAULT_FONT_SIZE = 13
MARKDOWN_EXTENSIONS = frozenset({".md", ".markdown", ".mdown"})


@dataclass(frozen=True)
class Theme:
    """Colors used by each document editor and preview."""

    background: str
    foreground: str
    editor_background: str
    gutter: str
    muted: str
    accent: str
    code_background: str


THEMES: dict[str, Theme] = {
    "Light": Theme("#f6f7fb", "#1f2937", "#ffffff", "#e5e7eb", "#6b7280", "#2563eb", "#eef2ff"),
    "Dark": Theme("#18181b", "#f4f4f5", "#27272a", "#3f3f46", "#a1a1aa", "#93c5fd", "#27272a"),
    "Sepia": Theme("#f5eedc", "#433422", "#fffaf0", "#e7dbc4", "#80664a", "#8a4b08", "#ede1c9"),
}


class DocumentView(ttk.Frame):
    """One independently editable Markdown document inside a notebook tab."""

    def __init__(self, parent: ttk.Notebook, app: MarkdownPreviewApp, path: Path | None = None) -> None:
        super().__init__(parent)
        self.app = app
        self.path = path
        self.is_dirty = False
        self.preview_after_id: str | None = None
        self.preview_theme = THEMES["Light"]
        self.preview_font_size = DEFAULT_FONT_SIZE
        self.is_preview_only = False
        self.is_syncing_scroll = False
        self._build_widgets()
        if path is not None:
            self.load_file(path)
        else:
            self.refresh_preview()

    @property
    def label(self) -> str:
        """Return the short label shown in the tab strip."""
        name = self.path.name if self.path is not None else "Untitled.md"
        return f"● {name}" if self.is_dirty else name

    def _build_widgets(self) -> None:
        self.paned = ttk.Panedwindow(self, orient=tk.HORIZONTAL)
        self.paned.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        self.editor_frame = ttk.Frame(self.paned)
        self.preview_frame = ttk.Frame(self.paned)
        self.paned.add(self.editor_frame, weight=1)
        self.paned.add(self.preview_frame, weight=1)

        ttk.Label(self.editor_frame, text="Markdown").pack(anchor=tk.W, pady=(0, 5))
        editor_body = ttk.Frame(self.editor_frame)
        editor_body.pack(fill=tk.BOTH, expand=True)
        self.editor = tk.Text(editor_body, wrap=tk.WORD, undo=True, padx=12, pady=12, borderwidth=0)
        self.editor_scroll = ttk.Scrollbar(editor_body, orient=tk.VERTICAL, command=self.editor.yview)
        self.editor.configure(yscrollcommand=self.editor_scroll.set)
        self.editor.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.editor_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.editor.bind("<<Modified>>", self._on_editor_modified)
        self.editor.bind("<Control-z>", self._undo_shortcut)
        self.editor.bind("<Command-z>", self._undo_shortcut)
        self.editor.bind("<Control-Shift-z>", self._redo_shortcut)
        self.editor.bind("<Control-Shift-Z>", self._redo_shortcut)
        self.editor.bind("<Command-Shift-z>", self._redo_shortcut)
        self.editor.bind("<Command-Shift-Z>", self._redo_shortcut)
        self.editor.bind("<Control-y>", self._redo_shortcut)
        self.app.register_drop_target(self.editor)

        ttk.Label(self.preview_frame, text="Preview").pack(anchor=tk.W, pady=(0, 5))
        preview_body = ttk.Frame(self.preview_frame)
        preview_body.pack(fill=tk.BOTH, expand=True)
        self.preview = tk.Text(preview_body, wrap=tk.WORD, state=tk.DISABLED, padx=18, pady=14, borderwidth=0, cursor="arrow")
        self.preview_scroll = ttk.Scrollbar(preview_body, orient=tk.VERTICAL, command=self.preview.yview)
        self.preview.configure(yscrollcommand=self.preview_scroll.set)
        self.preview.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.preview_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.editor.configure(yscrollcommand=self._on_editor_yview)
        self.preview.configure(yscrollcommand=self._on_preview_yview)
        self._register_preview_scroll_target(self.preview)
        self.app.register_drop_target(self.preview)

    def set_preview_only(self, enabled: bool) -> None:
        """Collapse or restore the Markdown editor pane for this document."""
        if enabled == self.is_preview_only:
            return
        if enabled:
            self.paned.forget(self.editor_frame)
        else:
            self.paned.insert(0, self.editor_frame, weight=1)
        self.is_preview_only = enabled

    def _register_preview_scroll_target(self, widget: tk.Misc) -> None:
        """Forward wheel events from embedded preview widgets to the preview text."""
        widget.bind("<MouseWheel>", self._on_preview_mousewheel)
        widget.bind("<Button-4>", self._scroll_preview_up)
        widget.bind("<Button-5>", self._scroll_preview_down)

    def _on_editor_yview(self, first: float, last: float) -> None:
        """Update the editor scrollbar and optionally mirror its vertical position."""
        self.editor_scroll.set(first, last)
        self._sync_other_view(self.preview, first)

    def _on_preview_yview(self, first: float, last: float) -> None:
        """Update the preview scrollbar and optionally mirror its vertical position."""
        self.preview_scroll.set(first, last)
        self._sync_other_view(self.editor, first)

    def _sync_other_view(self, target: tk.Text, position: float) -> None:
        """Mirror a scroll position when the shared Sync Scroll toggle is enabled."""
        if not self.app.sync_scroll_enabled.get() or self.is_syncing_scroll:
            return
        self.is_syncing_scroll = True
        target.yview_moveto(float(position))
        self.is_syncing_scroll = False

    def sync_preview_to_editor(self) -> None:
        """Immediately align the preview to the editor when Sync Scroll is enabled."""
        self.preview.yview_moveto(self.editor.yview()[0])

    def _on_preview_mousewheel(self, event: tk.Event[tk.Misc]) -> str:
        """Scroll consistently on macOS and Windows when the pointer is over a table cell."""
        delta = event.delta
        if delta == 0:
            return "break"
        units = max(1, abs(delta) // 120)
        self.preview.yview_scroll(-units if delta > 0 else units, "units")
        return "break"

    def _scroll_preview_up(self, _event: tk.Event[tk.Misc]) -> str:
        """Handle wheel-up events used by some Linux Tk builds."""
        self.preview.yview_scroll(-1, "units")
        return "break"

    def _scroll_preview_down(self, _event: tk.Event[tk.Misc]) -> str:
        """Handle wheel-down events used by some Linux Tk builds."""
        self.preview.yview_scroll(1, "units")
        return "break"

    def load_file(self, path: Path) -> bool:
        """Load a UTF-8 document into this tab, returning whether it succeeded."""
        try:
            content = path.read_text(encoding="utf-8")
        except OSError as error:
            messagebox.showerror(APP_NAME, f"Could not open {path.name}:\n{error}")
            return False
        self.path = path.resolve()
        self.editor.delete("1.0", tk.END)
        self.editor.insert("1.0", content)
        self.editor.edit_modified(False)
        self.is_dirty = False
        self.refresh_preview()
        return True

    def undo(self) -> bool:
        """Undo one editor action, returning whether an action was available."""
        try:
            self.editor.edit_undo()
        except tk.TclError:
            return False
        self.schedule_preview()
        return True

    def redo(self) -> bool:
        """Redo one editor action, returning whether an action was available."""
        try:
            self.editor.edit_redo()
        except tk.TclError:
            return False
        self.schedule_preview()
        return True

    def _undo_shortcut(self, _event: tk.Event[tk.Misc]) -> str:
        """Handle editor undo before Tk's default class binding can act twice."""
        self.undo()
        return "break"

    def _redo_shortcut(self, _event: tk.Event[tk.Misc]) -> str:
        """Handle editor redo before Tk's default class binding can act twice."""
        self.redo()
        return "break"

    def save(self) -> bool:
        """Save this document, prompting for a location when it is untitled."""
        if self.path is None:
            return self.save_as()
        return self._write_file(self.path)

    def save_as(self) -> bool:
        """Choose a new location and save this document."""
        selected = filedialog.asksaveasfilename(
            title="Save Markdown file",
            defaultextension=".md",
            filetypes=[("Markdown files", "*.md"), ("All files", "*.*")],
        )
        if not selected:
            return False
        self.path = Path(selected).resolve()
        return self._write_file(self.path)

    def _write_file(self, path: Path) -> bool:
        try:
            path.write_text(self.editor.get("1.0", "end-1c"), encoding="utf-8")
        except OSError as error:
            messagebox.showerror(APP_NAME, f"Could not save {path.name}:\n{error}")
            return False
        self.is_dirty = False
        self.app.update_document_label(self)
        self.app.status.config(text=f"Saved {path}")
        return True

    def confirm_close(self) -> bool:
        """Ask to save when this tab has unsaved edits."""
        if not self.is_dirty:
            return True
        choice = messagebox.askyesnocancel(APP_NAME, f"Save changes to {self.label.removeprefix('● ')}?")
        if choice is None:
            return False
        return self.save() if choice else True

    def apply_theme(self, theme: Theme, size: int) -> None:
        """Apply shared colors and text sizing to this document."""
        self.preview_theme = theme
        self.preview_font_size = size
        body_font = font.Font(family="TkTextFont", size=size)
        self.editor.configure(background=theme.editor_background, foreground=theme.foreground, insertbackground=theme.foreground, font=body_font)
        self.preview.configure(background=theme.background, foreground=theme.foreground, font=body_font)
        self.preview.tag_configure("body", foreground=theme.foreground, font=body_font)
        self.preview.tag_configure("h1", foreground=theme.foreground, font=("TkTextFont", size + 11, "bold"), spacing1=8)
        self.preview.tag_configure("h2", foreground=theme.foreground, font=("TkTextFont", size + 6, "bold"), spacing1=6)
        self.preview.tag_configure("h3", foreground=theme.foreground, font=("TkTextFont", size + 3, "bold"), spacing1=4)
        self.preview.tag_configure("body_bold", font=("TkTextFont", size, "bold"))
        self.preview.tag_configure("body_italic", font=("TkTextFont", size, "italic"))
        self.preview.tag_configure("bullet", foreground=theme.accent, font=body_font)
        self.preview.tag_configure("quote", foreground=theme.muted, font=("TkTextFont", size, "italic"))
        self.preview.tag_configure("quote_mark", foreground=theme.accent, font=body_font)
        self.preview.tag_configure("code", background=theme.code_background, foreground=theme.foreground, font=("TkFixedFont", size - 1))
        self.preview.tag_configure("inline_code", background=theme.code_background, foreground=theme.accent, font=("TkFixedFont", size - 1))
        self.preview.tag_configure("rule", foreground=theme.gutter)
        self.preview.tag_configure("link", foreground=theme.accent, underline=True)
        self.preview.tag_configure("table_header", background=theme.code_background, foreground=theme.foreground, font=("TkFixedFont", size - 1, "bold"))
        self.preview.tag_configure("table_body", foreground=theme.foreground, font=("TkFixedFont", size - 1))
        self.preview.tag_configure("table_rule", foreground=theme.accent, font=("TkFixedFont", size - 1))
        self.refresh_preview()

    def _on_editor_modified(self, _event: tk.Event[tk.Misc]) -> None:
        if not self.editor.edit_modified():
            return
        self.editor.edit_modified(False)
        self.is_dirty = True
        self.app.update_document_label(self)
        self.schedule_preview()

    def schedule_preview(self) -> None:
        """Debounce preview updates while the user is typing."""
        if self.preview_after_id is not None:
            self.after_cancel(self.preview_after_id)
        self.preview_after_id = self.after(PREVIEW_DELAY_MS, self.refresh_preview)

    def refresh_preview(self) -> None:
        """Render the current source into the read-only preview pane."""
        self.preview_after_id = None
        self.preview.configure(state=tk.NORMAL)
        self.preview.delete("1.0", tk.END)
        self._render_markdown(self.editor.get("1.0", "end-1c"))
        self.preview.configure(state=tk.DISABLED)

    def _render_markdown(self, content: str) -> None:
        lines = content.splitlines()
        in_code_block = False
        line_index = 0
        while line_index < len(lines):
            line = lines[line_index]
            if line.startswith("```"):
                in_code_block = not in_code_block
            elif in_code_block:
                self._write(line + "\n", "code")
            elif self._is_table_header(lines, line_index):
                line_index = self._render_table(lines, line_index)
                continue
            elif line.startswith("### "):
                self._write_inline(line[4:] + "\n\n", "h3")
            elif line.startswith("## "):
                self._write_inline(line[3:] + "\n\n", "h2")
            elif line.startswith("# "):
                self._write_inline(line[2:] + "\n\n", "h1")
            elif re.fullmatch(r"\s{0,3}([-*_])(?:\s*\1){2,}\s*", line):
                self._write("─" * 40 + "\n\n", "rule")
            elif match := re.match(r"\s*[-*+]\s+(.*)", line):
                self._write("•  ", "bullet")
                self._write_inline(match.group(1) + "\n", "body")
            elif match := re.match(r"\s*(\d+)\.\s+(.*)", line):
                self._write(f"{match.group(1)}.  ", "bullet")
                self._write_inline(match.group(2) + "\n", "body")
            elif line.startswith("> "):
                self._write("▌ ", "quote_mark")
                self._write_inline(line[2:] + "\n", "quote")
            elif not line.strip():
                self._write("\n", "body")
            else:
                self._write_inline(line + "\n", "body")
            line_index += 1

    def _is_table_header(self, lines: list[str], line_index: int) -> bool:
        """Return whether a line and its successor begin a Markdown table."""
        if line_index + 1 >= len(lines) or "|" not in lines[line_index]:
            return False
        divider_cells = self._table_cells(lines[line_index + 1])
        return bool(divider_cells) and all(re.fullmatch(r":?-{3,}:?", cell) for cell in divider_cells)

    def _render_table(self, lines: list[str], header_index: int) -> int:
        """Render a basic GitHub-style Markdown table using a wrapped cell grid."""
        table_rows = [self._table_cells(lines[header_index])]
        line_index = header_index + 2
        while line_index < len(lines) and "|" in lines[line_index] and lines[line_index].strip():
            table_rows.append(self._table_cells(lines[line_index]))
            line_index += 1
        column_count = max(len(row) for row in table_rows)
        normalized_rows = [row + [""] * (column_count - len(row)) for row in table_rows]
        cell_width = max(100, min(210, 510 // column_count))
        table_frame = tk.Frame(self.preview, background=self.preview_theme.gutter, padx=1, pady=1)
        self._register_preview_scroll_target(table_frame)
        for row_index, row in enumerate(normalized_rows):
            for column_index, cell in enumerate(row):
                is_header = row_index == 0
                label = tk.Label(
                    table_frame,
                    text=cell,
                    anchor=tk.W,
                    background=self.preview_theme.code_background if is_header else self.preview_theme.background,
                    foreground=self.preview_theme.foreground,
                    font=("TkTextFont", self.preview_font_size, "bold" if is_header else "normal"),
                    justify=tk.LEFT,
                    padx=7,
                    pady=5,
                    wraplength=cell_width - 14,
                )
                self._register_preview_scroll_target(label)
                label.grid(row=row_index, column=column_index, padx=1, pady=1, sticky="nsew")
                table_frame.grid_columnconfigure(column_index, minsize=cell_width, weight=1)
        self.preview.window_create(tk.END, window=table_frame, align="top")
        self._write("\n", "body")
        return line_index

    def _table_cells(self, line: str) -> list[str]:
        """Split a basic pipe-delimited Markdown table row into stripped cells."""
        stripped_line = line.strip().strip("|")
        return [cell.strip() for cell in stripped_line.split("|")]

    def _write_inline(self, value: str, base_tag: str) -> None:
        pattern = re.compile(r"(\*\*[^*]+\*\*|`[^`]+`|\*[^*]+\*|\[[^]]+\]\([^)]+\))")
        position = 0
        for match in pattern.finditer(value):
            self._write(value[position:match.start()], base_tag)
            token = match.group(0)
            if token.startswith("**"):
                self._write(token[2:-2], f"{base_tag}_bold")
            elif token.startswith("`"):
                self._write(token[1:-1], "inline_code")
            elif token.startswith("*"):
                self._write(token[1:-1], f"{base_tag}_italic")
            else:
                link_match = re.match(r"\[([^]]+)\]\(([^)]+)\)", token)
                if link_match is not None:
                    link_text, url = link_match.groups()
                    tag_name = f"url:{url}"
                    self._write(link_text, ("link", tag_name))
                    def open_url(_event: tk.Event[tk.Misc], target: str = url) -> None:
                        webbrowser.open_new_tab(target)

                    self.preview.tag_bind(tag_name, "<Button-1>", open_url)
            position = match.end()
        self._write(value[position:], base_tag)

    def _write(self, value: str, tags: str | tuple[str, ...]) -> None:
        self.preview.insert(tk.END, value, tags)


class MarkdownPreviewApp:
    """The root window coordinating a set of independently editable tabs."""

    def __init__(self, root: tk.Tk, initial_files: list[Path]) -> None:
        self.root = root
        self.theme_name = tk.StringVar(value="Light")
        self.font_size = tk.IntVar(value=DEFAULT_FONT_SIZE)
        self.sync_scroll_enabled = tk.BooleanVar(value=False)
        self.documents: list[DocumentView] = []
        self.app_icon: tk.PhotoImage | None = None
        self.dragged_tab_index: int | None = None
        self._build_window()
        self._bind_shortcuts()
        if initial_files:
            for initial_file in initial_files:
                self.new_document(initial_file)
        else:
            self.new_document()
        self.root.after_idle(self._activate_window)

    def _build_window(self) -> None:
        self.root.title(APP_NAME)
        self.root.geometry("1200x760")
        self.root.minsize(760, 520)
        self.root.protocol("WM_DELETE_WINDOW", self.close_window)
        self._set_window_icon()
        self._build_menu()
        toolbar = ttk.Frame(self.root, padding=(10, 8))
        toolbar.pack(fill=tk.X)
        ttk.Button(toolbar, text="New", command=lambda: self.new_document()).pack(side=tk.LEFT)
        ttk.Button(toolbar, text="Open…", command=self.open_file).pack(side=tk.LEFT, padx=(6, 0))
        ttk.Button(toolbar, text="Undo", command=self.undo_active).pack(side=tk.LEFT, padx=(6, 0))
        ttk.Button(toolbar, text="Redo", command=self.redo_active).pack(side=tk.LEFT, padx=(6, 0))
        ttk.Button(toolbar, text="Save", command=self.save_active).pack(side=tk.LEFT, padx=(6, 0))
        ttk.Button(toolbar, text="Save As…", command=self.save_active_as).pack(side=tk.LEFT, padx=(6, 0))
        ttk.Button(toolbar, text="Close Tab", command=self.close_active).pack(side=tk.LEFT, padx=(6, 0))
        self.preview_only_button = ttk.Button(toolbar, text="Preview Only", command=self.toggle_preview_only)
        self.preview_only_button.pack(side=tk.LEFT, padx=(6, 0))
        ttk.Checkbutton(toolbar, text="Sync Scroll", variable=self.sync_scroll_enabled, command=self.sync_active_document).pack(side=tk.LEFT, padx=(12, 0))
        ttk.Label(toolbar, text="Theme:").pack(side=tk.RIGHT, padx=(12, 5))
        theme_picker = ttk.Combobox(toolbar, state="readonly", textvariable=self.theme_name, values=list(THEMES), width=9)
        theme_picker.pack(side=tk.RIGHT)
        theme_picker.bind("<<ComboboxSelected>>", self.apply_theme)
        ttk.Label(toolbar, text="Text size:").pack(side=tk.RIGHT, padx=(12, 5))
        ttk.Spinbox(toolbar, from_=10, to=22, textvariable=self.font_size, width=4, command=self.apply_theme).pack(side=tk.RIGHT)
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill=tk.BOTH, expand=True)
        self.notebook.bind("<<NotebookTabChanged>>", self._on_tab_changed)
        self.notebook.bind("<ButtonPress-1>", self._start_tab_drag)
        self.notebook.bind("<B1-Motion>", self._drag_tab)
        self.notebook.bind("<ButtonRelease-1>", self._finish_tab_drag)
        self.register_drop_target(self.notebook)
        self.status = ttk.Label(self.root, anchor=tk.W, padding=(10, 5))
        self.status.pack(fill=tk.X)

    def _build_menu(self) -> None:
        menu = tk.Menu(self.root)
        file_menu = tk.Menu(menu, tearoff=False)
        file_menu.add_command(label="New", command=lambda: self.new_document(), accelerator="Ctrl+N")
        file_menu.add_command(label="Open…", command=self.open_file, accelerator="Ctrl+O")
        file_menu.add_command(label="Save", command=self.save_active, accelerator="Ctrl+S")
        file_menu.add_command(label="Save As…", command=self.save_active_as, accelerator="Ctrl+Shift+S")
        file_menu.add_command(label="Close Tab", command=self.close_active, accelerator="Ctrl+W")
        file_menu.add_separator()
        file_menu.add_command(label="Quit", command=self.close_window, accelerator="Ctrl+Q")
        menu.add_cascade(label="File", menu=file_menu)
        edit_menu = tk.Menu(menu, tearoff=False)
        edit_menu.add_command(label="Undo", command=self.undo_active, accelerator="Ctrl+Z / Cmd+Z")
        edit_menu.add_command(label="Redo", command=self.redo_active, accelerator="Ctrl+Shift+Z / Cmd+Shift+Z")
        menu.add_cascade(label="Edit", menu=edit_menu)
        view_menu = tk.Menu(menu, tearoff=False)
        view_menu.add_command(label="Toggle Preview Only", command=self.toggle_preview_only, accelerator="Ctrl+Shift+P")
        view_menu.add_checkbutton(label="Sync Scroll", variable=self.sync_scroll_enabled, command=self.sync_active_document)
        menu.add_cascade(label="View", menu=view_menu)
        self.root.config(menu=menu)

    def _bind_shortcuts(self) -> None:
        self.root.bind_all("<Control-n>", lambda _event: self.new_document())
        self.root.bind_all("<Command-n>", lambda _event: self.new_document())
        self.root.bind_all("<Control-o>", lambda _event: self.open_file())
        self.root.bind_all("<Command-o>", lambda _event: self.open_file())
        self.root.bind_all("<Control-s>", lambda _event: self.save_active())
        self.root.bind_all("<Command-s>", lambda _event: self.save_active())
        self.root.bind_all("<Control-Shift-S>", lambda _event: self.save_active_as())
        self.root.bind_all("<Command-Shift-S>", lambda _event: self.save_active_as())
        self.root.bind_all("<Control-w>", self._close_tab_shortcut)
        self.root.bind_all("<Command-w>", self._close_tab_shortcut)
        self.root.bind_all("<Command-y>", self._close_tab_shortcut)
        self.root.bind_all("<Control-q>", lambda _event: self.close_window())
        self.root.bind_all("<Command-q>", lambda _event: self.close_window())
        self.root.bind_all("<Control-Shift-p>", lambda _event: self.toggle_preview_only())
        self.root.bind_all("<Command-Shift-p>", lambda _event: self.toggle_preview_only())

    def _close_tab_shortcut(self, _event: tk.Event[tk.Misc]) -> str:
        """Close the active tab and suppress any platform default shortcut handling."""
        self.close_active()
        return "break"

    def new_document(self, path: Path | None = None) -> None:
        """Create and focus a tab, optionally loading a Markdown file into it."""
        if path is not None:
            resolved = path.resolve()
            existing = next((document for document in self.documents if document.path == resolved), None)
            if existing is not None:
                self.notebook.select(existing)
                return
        document = DocumentView(self.notebook, self, path)
        self.documents.append(document)
        self.notebook.add(document, text=document.label)
        self.notebook.select(document)
        self.apply_theme()
        self.update_document_label(document)
        self._update_preview_only_button()

    def open_file(self) -> None:
        """Open another Markdown document in its own tab."""
        selected = filedialog.askopenfilename(
            title="Open Markdown file",
            filetypes=[("Markdown files", "*.md *.markdown *.mdown"), ("All files", "*.*")],
        )
        if selected:
            self.new_document(Path(selected))

    def register_drop_target(self, widget: tk.Misc) -> None:
        """Enable file drops on a widget when the optional DnD package is installed."""
        if DND_FILES is None:
            return
        register_target = getattr(widget, "drop_target_register", None)
        bind_drop = getattr(widget, "dnd_bind", None)
        if not callable(register_target) or not callable(bind_drop):
            return
        register_target(DND_FILES)
        bind_drop("<<Drop>>", self._on_files_dropped)

    def _on_files_dropped(self, event: tk.Event[tk.Misc]) -> None:
        """Open every dropped Markdown file in a separate tab."""
        event_data = getattr(event, "data", "")
        if not isinstance(event_data, str):
            return
        dropped_paths = self.root.tk.splitlist(event_data)
        markdown_paths = [
            Path(dropped_path)
            for dropped_path in dropped_paths
            if Path(dropped_path).is_file() and Path(dropped_path).suffix.lower() in MARKDOWN_EXTENSIONS
        ]
        for path in markdown_paths:
            self.new_document(path)
        if not markdown_paths:
            self.status.config(text="Drop a Markdown file to open it in a new tab.")

    def active_document(self) -> DocumentView | None:
        """Return the selected tab's document, when a tab is available."""
        selected = self.notebook.select()
        return next((document for document in self.documents if str(document) == selected), None)

    def save_active(self) -> None:
        document = self.active_document()
        if document is not None:
            document.save()

    def undo_active(self) -> None:
        """Undo in the active Markdown editor, when an action is available."""
        document = self.active_document()
        if document is not None:
            document.undo()

    def redo_active(self) -> None:
        """Redo in the active Markdown editor, when an action is available."""
        document = self.active_document()
        if document is not None:
            document.redo()

    def save_active_as(self) -> None:
        document = self.active_document()
        if document is not None:
            document.save_as()

    def close_active(self) -> None:
        document = self.active_document()
        if document is None or not document.confirm_close():
            return
        if len(self.documents) == 1:
            self.root.destroy()
            return
        self.notebook.forget(document)
        self.documents.remove(document)
        document.destroy()

    def close_window(self) -> None:
        """Close only after every document with edits has been handled."""
        for document in self.documents:
            if not document.confirm_close():
                return
        self.root.destroy()

    def toggle_preview_only(self) -> None:
        """Toggle the active document between split and preview-only layouts."""
        document = self.active_document()
        if document is None:
            return
        document.set_preview_only(not document.is_preview_only)
        self._update_preview_only_button()

    def sync_active_document(self) -> None:
        """Align the active preview immediately after Sync Scroll is turned on."""
        document = self.active_document()
        if document is not None and self.sync_scroll_enabled.get():
            document.sync_preview_to_editor()

    def _update_preview_only_button(self) -> None:
        """Keep the toolbar action aligned with the selected document's layout."""
        document = self.active_document()
        is_preview_only = document is not None and document.is_preview_only
        self.preview_only_button.config(text="Show Markdown" if is_preview_only else "Preview Only")

    def apply_theme(self, _event: tk.Event[tk.Misc] | None = None) -> None:
        """Apply the selected display options across all open documents."""
        theme = THEMES[self.theme_name.get()]
        size = self.font_size.get()
        self.root.configure(background=theme.background)
        for document in self.documents:
            document.apply_theme(theme, size)

    def update_document_label(self, document: DocumentView) -> None:
        """Refresh a tab label and the title/status for the selected tab."""
        self.notebook.tab(document, text=document.label)
        if self.active_document() is document:
            self._show_active_document()

    def _on_tab_changed(self, _event: tk.Event[tk.Misc]) -> None:
        self._show_active_document()
        self._update_preview_only_button()

    def _start_tab_drag(self, event: tk.Event[tk.Misc]) -> None:
        """Start reordering only when the press originated on a document tab."""
        try:
            self.dragged_tab_index = self.notebook.index(f"@{event.x},{event.y}")
        except tk.TclError:
            self.dragged_tab_index = None

    def _drag_tab(self, event: tk.Event[tk.Misc]) -> None:
        """Move the dragged tab as the pointer crosses another tab."""
        if self.dragged_tab_index is None:
            return
        try:
            target_index = self.notebook.index(f"@{event.x},{event.y}")
        except tk.TclError:
            return
        if target_index == self.dragged_tab_index:
            return
        tab_id = self.notebook.tabs()[self.dragged_tab_index]
        self.notebook.insert(target_index, tab_id)
        self.dragged_tab_index = target_index

    def _finish_tab_drag(self, _event: tk.Event[tk.Misc]) -> None:
        """Clear transient tab-drag state when the pointer is released."""
        self.dragged_tab_index = None

    def _show_active_document(self) -> None:
        document = self.active_document()
        if document is None:
            self.root.title(APP_NAME)
            self.status.config(text="")
            return
        self.root.title(f"{document.label} — {APP_NAME}")
        self.status.config(text=str(document.path) if document.path is not None else "Unsaved document")

    def _set_window_icon(self) -> None:
        """Load the bundled PNG icon when the user has supplied one."""
        icon_path = Path(__file__).parent / "assets" / "icon.png"
        if not icon_path.is_file():
            return
        try:
            self.app_icon = tk.PhotoImage(master=self.root, file=icon_path)
            self.root.iconphoto(True, self.app_icon)
        except (OSError, tk.TclError) as error:
            self.status_message_after_icon_error(error)

    def status_message_after_icon_error(self, error: OSError | tk.TclError) -> None:
        """Avoid failing startup when a supplied icon cannot be opened."""
        self.root.after_idle(lambda: self.status.config(text=f"Could not load app icon: {error}"))

    def _activate_window(self) -> None:
        """Request foreground focus after Tk has finished constructing the window."""
        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()


def launch(initial_files: list[Path]) -> None:
    """Create and run the desktop application."""
    root = TkinterDnD.Tk() if TkinterDnD is not None else tk.Tk()
    MarkdownPreviewApp(root, initial_files)
    root.mainloop()
