"""Native Tk application for comparing text files side by side."""

from __future__ import annotations

import difflib
import tkinter as tk
from dataclasses import dataclass
from pathlib import Path
from tkinter import filedialog, font, messagebox, ttk
from typing import Any, Literal

try:
    from tkinterdnd2 import DND_FILES as installed_dnd_files
    from tkinterdnd2 import TkinterDnD as installed_tkinter_dnd
except ImportError:
    DND_FILES: str | None = None
    TkinterDnD: Any | None = None
else:
    DND_FILES = installed_dnd_files
    TkinterDnD = installed_tkinter_dnd


APP_NAME = "Diff Checker Tool"
DEFAULT_FONT_SIZE = 12
PaneSide = Literal["left", "right"]


@dataclass(frozen=True)
class Theme:
    """Colors shared by the application and its comparison panes."""

    background: str
    foreground: str
    pane_background: str
    muted: str
    border: str
    accent: str
    added: str
    removed: str
    changed: str


THEMES: dict[str, Theme] = {
    "Light": Theme("#f6f7fb", "#1f2937", "#ffffff", "#6b7280", "#d1d5db", "#2563eb", "#dcfce7", "#fee2e2", "#fef3c7"),
    "Dark": Theme("#18181b", "#f4f4f5", "#27272a", "#a1a1aa", "#52525b", "#93c5fd", "#14532d", "#7f1d1d", "#713f12"),
    "Sepia": Theme("#f5eedc", "#433422", "#fffaf0", "#80664a", "#d8c9ab", "#8a4b08", "#dcefdc", "#f5dddd", "#f5e7bd"),
}


class DiffView(ttk.Frame):
    """One independently configurable comparison in a notebook tab."""

    def __init__(self, parent: ttk.Notebook, app: DiffCheckerApp, left: Path | None, right: Path | None) -> None:
        super().__init__(parent)
        self.app = app
        self.left_path = left.resolve() if left is not None else None
        self.right_path = right.resolve() if right is not None else None
        self.left_text = ""
        self.right_text = ""
        self.merged_text = ""
        self.merged_override: str | None = None
        self.editing_sides: set[PaneSide] = set()
        self.is_editing_merged = False
        self.is_merged_visible = False
        self._build_widgets()
        self.refresh_diff()

    @property
    def label(self) -> str:
        """Return the concise label shown on the comparison tab."""
        left_name = self.left_path.name if self.left_path is not None else "Left"
        right_name = self.right_path.name if self.right_path is not None else "Right"
        return f"{left_name} ↔ {right_name}"

    def _build_widgets(self) -> None:
        self.paned = ttk.Panedwindow(self, orient=tk.HORIZONTAL)
        self.paned.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        self.left_frame, self.left_view = self._build_pane(self.paned, "Left file", "left")
        self.merged_frame, self.merged_view = self._build_merged_pane(self.paned)
        self.right_frame, self.right_view = self._build_pane(self.paned, "Right file", "right")
        self.paned.add(self.left_frame, weight=1)
        self.paned.add(self.right_frame, weight=1)

    def _build_pane(self, parent: ttk.Panedwindow, title: str, side: PaneSide) -> tuple[ttk.Frame, tk.Text]:
        pane = ttk.Frame(parent)
        heading = ttk.Frame(pane)
        heading.pack(fill=tk.X, pady=(0, 5))
        ttk.Label(heading, text=title).pack(side=tk.LEFT)
        ttk.Button(heading, text="Choose…", command=lambda: self.choose_file(side)).pack(side=tk.RIGHT)
        edit_button = ttk.Button(heading, text="Edit", command=lambda: self.toggle_edit(side))
        edit_button.pack(side=tk.RIGHT, padx=(0, 6))
        path_label = ttk.Label(pane, anchor=tk.W)
        path_label.pack(fill=tk.X, pady=(0, 5))
        if side == "left":
            self.left_path_label = path_label
            self.left_edit_button = edit_button
        else:
            self.right_path_label = path_label
            self.right_edit_button = edit_button

        body = ttk.Frame(pane)
        body.pack(fill=tk.BOTH, expand=True)
        text_view = tk.Text(body, wrap=tk.NONE, state=tk.DISABLED, undo=True, padx=10, pady=10, borderwidth=0, cursor="arrow")
        vertical_scroll = ttk.Scrollbar(body, orient=tk.VERTICAL, command=text_view.yview)
        horizontal_scroll = ttk.Scrollbar(pane, orient=tk.HORIZONTAL, command=text_view.xview)
        text_view.configure(yscrollcommand=vertical_scroll.set, xscrollcommand=horizontal_scroll.set)
        text_view.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        vertical_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        horizontal_scroll.pack(fill=tk.X)
        self._bind_edit_shortcuts(text_view)
        self.app.register_drop_target(text_view, self, side)
        return pane, text_view

    def _build_merged_pane(self, parent: ttk.Panedwindow) -> tuple[ttk.Frame, tk.Text]:
        """Create the center pane used to review, edit, and export a merged result."""
        pane = ttk.Frame(parent)
        heading = ttk.Frame(pane)
        heading.pack(fill=tk.X, pady=(0, 5))
        ttk.Label(heading, text="Merged result").pack(side=tk.LEFT)
        ttk.Button(heading, text="Save As…", command=self.export_merged).pack(side=tk.RIGHT)
        self.merged_edit_button = ttk.Button(heading, text="Edit", command=self.toggle_merged_edit)
        self.merged_edit_button.pack(side=tk.RIGHT, padx=(0, 6))
        ttk.Label(pane, text="One-sided changes are included; replacements remain conflict blocks.", anchor=tk.W).pack(fill=tk.X, pady=(0, 5))
        body = ttk.Frame(pane)
        body.pack(fill=tk.BOTH, expand=True)
        text_view = tk.Text(body, wrap=tk.NONE, state=tk.DISABLED, undo=True, padx=10, pady=10, borderwidth=0, cursor="arrow")
        vertical_scroll = ttk.Scrollbar(body, orient=tk.VERTICAL, command=text_view.yview)
        horizontal_scroll = ttk.Scrollbar(pane, orient=tk.HORIZONTAL, command=text_view.xview)
        text_view.configure(yscrollcommand=vertical_scroll.set, xscrollcommand=horizontal_scroll.set)
        text_view.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        vertical_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        horizontal_scroll.pack(fill=tk.X)
        self._bind_edit_shortcuts(text_view)
        return pane, text_view

    def set_merged_visible(self, enabled: bool) -> None:
        """Insert or remove the center merged pane without changing either source file."""
        if enabled == self.is_merged_visible:
            return
        if enabled:
            self.paned.insert(1, self.merged_frame, weight=1)
        else:
            self.paned.forget(self.merged_frame)
        self.is_merged_visible = enabled

    def choose_file(self, side: PaneSide) -> None:
        """Choose one replacement file for the requested side of this diff."""
        selected = filedialog.askopenfilename(title=f"Choose {side} file", filetypes=[("Text files", "*.txt *.md *.py *.json *.csv *.yaml *.yml *.xml *.html *.css *.js *.cs"), ("All files", "*.*")])
        if selected:
            self.load_file(side, Path(selected))

    def load_file(self, side: PaneSide, path: Path) -> bool:
        """Read one text file and replace its side of the comparison."""
        if not self.confirm_edits():
            return False
        if not path.is_file():
            self.app.status.config(text=f"Not a file: {path}")
            return False
        try:
            content = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            try:
                content = path.read_text(encoding="utf-8-sig")
            except (OSError, UnicodeDecodeError) as error:
                messagebox.showerror(APP_NAME, f"Could not read {path.name} as text:\n{error}")
                return False
        except OSError as error:
            messagebox.showerror(APP_NAME, f"Could not open {path.name}:\n{error}")
            return False
        if side == "left":
            self.left_path = path.resolve()
            self.left_text = content
        else:
            self.right_path = path.resolve()
            self.right_text = content
        self.merged_override = None
        self.refresh_diff()
        self.app.update_tab_label(self)
        return True

    def toggle_edit(self, side: PaneSide) -> None:
        """Enter or leave direct-edit mode for one source pane."""
        if side in self.editing_sides:
            self.finish_edit(side)
            return
        text_view = self._view_for(side)
        text_view.configure(state=tk.NORMAL, cursor="xterm")
        text_view.delete("1.0", tk.END)
        text_view.insert("1.0", self._text_for(side))
        text_view.edit_reset()
        self.editing_sides.add(side)
        self._update_edit_buttons()
        self.app.status.config(text=f"Editing {side} pane. Choose Done Editing when finished.")

    def finish_edit(self, side: PaneSide) -> bool:
        """Leave edit mode, optionally saving the edited source file."""
        if side not in self.editing_sides:
            return True
        updated_text = self._view_for(side).get("1.0", "end-1c")
        if updated_text == self._text_for(side):
            self._end_source_editing(side)
            return True
        path = self._path_for(side)
        name = path.name if path is not None else f"{side} pane"
        choice = messagebox.askyesnocancel(APP_NAME, f"Save changes to {name}?")
        if choice is None:
            return False
        if choice and not self._save_side(side, updated_text):
            return False
        if choice:
            self._set_text_for(side, updated_text)
            self.merged_override = None
        self._end_source_editing(side)
        return True

    def confirm_close(self) -> bool:
        """Resolve an active pane edit before closing its comparison tab."""
        return self.confirm_edits()

    def confirm_edits(self) -> bool:
        """Resolve every active source or merged-result editing session."""
        for side in tuple(self.editing_sides):
            if not self.finish_edit(side):
                return False
        return not self.is_editing_merged or self.finish_merged_edit()

    def _end_source_editing(self, side: PaneSide) -> None:
        """Mark one source pane read-only after its edit session is resolved."""
        self._view_for(side).configure(state=tk.DISABLED, cursor="arrow")
        self.editing_sides.remove(side)
        self._update_edit_buttons()
        if not self.editing_sides and not self.is_editing_merged:
            self.refresh_diff()
            self.app.update_tab_label(self)

    def _save_side(self, side: PaneSide, content: str) -> bool:
        """Write one edited pane to its source path, requesting one if needed."""
        path = self._path_for(side)
        if path is None:
            selected = filedialog.asksaveasfilename(
                title=f"Save {side} file",
                defaultextension=".txt",
                filetypes=[("Text files", "*.txt"), ("All files", "*.*")],
            )
            if not selected:
                return False
            path = Path(selected).resolve()
            self._set_path_for(side, path)
        try:
            path.write_text(content, encoding="utf-8")
        except OSError as error:
            messagebox.showerror(APP_NAME, f"Could not save {path.name}:\n{error}")
            return False
        self.app.status.config(text=f"Saved {path}")
        return True

    def _view_for(self, side: PaneSide) -> tk.Text:
        """Return the text widget for one source pane."""
        return self.left_view if side == "left" else self.right_view

    def _text_for(self, side: PaneSide) -> str:
        """Return the current source text for one pane."""
        return self.left_text if side == "left" else self.right_text

    def _set_text_for(self, side: PaneSide, content: str) -> None:
        """Replace the in-memory source text for one pane."""
        if side == "left":
            self.left_text = content
        else:
            self.right_text = content

    def _path_for(self, side: PaneSide) -> Path | None:
        """Return the current source path for one pane."""
        return self.left_path if side == "left" else self.right_path

    def _set_path_for(self, side: PaneSide, path: Path) -> None:
        """Assign a resolved source path to one pane."""
        if side == "left":
            self.left_path = path
        else:
            self.right_path = path

    def _update_edit_buttons(self) -> None:
        """Reflect which panes are currently editable."""
        self.left_edit_button.config(text="Done Editing" if "left" in self.editing_sides else "Edit")
        self.right_edit_button.config(text="Done Editing" if "right" in self.editing_sides else "Edit")
        self.merged_edit_button.config(text="Done Editing" if self.is_editing_merged else "Edit")

    def toggle_merged_edit(self) -> None:
        """Enter or leave edit mode for the merged result."""
        if self.is_editing_merged:
            self.finish_merged_edit()
            return
        self.merged_view.configure(state=tk.NORMAL, cursor="xterm")
        self.merged_view.delete("1.0", tk.END)
        self.merged_view.insert("1.0", self.merged_text)
        self.merged_view.edit_reset()
        self.is_editing_merged = True
        self._update_edit_buttons()
        self.app.status.config(text="Editing merged result. Choose Done Editing when finished.")

    def finish_merged_edit(self) -> bool:
        """Leave merged-result edit mode, optionally exporting the edited result."""
        if not self.is_editing_merged:
            return True
        updated_text = self.merged_view.get("1.0", "end-1c")
        if updated_text != self.merged_text:
            choice = messagebox.askyesnocancel(APP_NAME, "Save changes to the merged result?")
            if choice is None:
                return False
            if choice and not self._write_merged_export(updated_text):
                return False
            if choice:
                self.merged_text = updated_text
                self.merged_override = updated_text
        self.merged_view.configure(state=tk.DISABLED, cursor="arrow")
        self.is_editing_merged = False
        self._update_edit_buttons()
        if not self.editing_sides:
            self.refresh_diff()
        return True

    def export_merged(self) -> None:
        """Choose a destination and export the current merged result."""
        content = self.merged_view.get("1.0", "end-1c") if self.is_editing_merged else self.merged_text
        self._write_merged_export(content)

    def _write_merged_export(self, content: str) -> bool:
        """Prompt for an output path and write a merged result there."""
        selected = filedialog.asksaveasfilename(
            title="Save merged result",
            defaultextension=".txt",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")],
        )
        if not selected:
            return False
        path = Path(selected)
        try:
            path.write_text(content, encoding="utf-8")
        except OSError as error:
            messagebox.showerror(APP_NAME, f"Could not save {path.name}:\n{error}")
            return False
        self.app.status.config(text=f"Saved merged result to {path}")
        return True

    def _bind_edit_shortcuts(self, text_view: tk.Text) -> None:
        """Bind native undo and redo shortcuts to one editable text widget."""
        text_view.bind("<Control-z>", self._undo_shortcut)
        text_view.bind("<Command-z>", self._undo_shortcut)
        text_view.bind("<Control-Shift-z>", self._redo_shortcut)
        text_view.bind("<Command-Shift-z>", self._redo_shortcut)
        text_view.bind("<Control-y>", self._redo_shortcut)

    def _undo_shortcut(self, event: tk.Event[tk.Misc]) -> str:
        """Undo in the focused editable pane."""
        if isinstance(event.widget, tk.Text):
            return self._undo_edit(event.widget)
        return "break"

    def _redo_shortcut(self, event: tk.Event[tk.Misc]) -> str:
        """Redo in the focused editable pane."""
        if isinstance(event.widget, tk.Text):
            return self._redo_edit(event.widget)
        return "break"

    def _undo_edit(self, text_view: tk.Text) -> str:
        """Undo within an active editable pane without invoking a window shortcut."""
        try:
            text_view.edit_undo()
        except tk.TclError:
            pass
        return "break"

    def _redo_edit(self, text_view: tk.Text) -> str:
        """Redo within an active editable pane without invoking a window shortcut."""
        try:
            text_view.edit_redo()
        except tk.TclError:
            pass
        return "break"

    def refresh_diff(self) -> None:
        """Compute aligned rows and redraw both read-only text panes."""
        if self.left_path is not None and not self.left_text:
            self.left_text = self._read_initial_text(self.left_path)
        if self.right_path is not None and not self.right_text:
            self.right_text = self._read_initial_text(self.right_path)

        self._update_path_labels()
        left_lines = self.left_text.splitlines()
        right_lines = self.right_text.splitlines()
        left_rows: list[tuple[int | None, str, str]] = []
        right_rows: list[tuple[int | None, str, str]] = []
        merged_rows: list[tuple[int | None, str, str]] = []
        matcher = difflib.SequenceMatcher(None, left_lines, right_lines, autojunk=False)
        for operation, left_start, left_end, right_start, right_end in matcher.get_opcodes():
            left_chunk = left_lines[left_start:left_end]
            right_chunk = right_lines[right_start:right_end]
            if operation == "equal":
                for offset, line in enumerate(left_chunk):
                    left_rows.append((left_start + offset + 1, line, "normal"))
                    right_rows.append((right_start + offset + 1, line, "normal"))
                    merged_rows.append((None, line, "normal"))
            elif operation == "replace":
                self._append_aligned_rows(left_rows, right_rows, left_chunk, right_chunk, left_start, right_start, "changed", "changed")
                left_name = self.left_path.name if self.left_path is not None else "LEFT"
                right_name = self.right_path.name if self.right_path is not None else "RIGHT"
                merged_rows.append((None, f"<<<<<<< LEFT: {left_name}", "conflict"))
                merged_rows.extend((None, line, "conflict") for line in left_chunk)
                merged_rows.append((None, "=======", "conflict"))
                merged_rows.extend((None, line, "conflict") for line in right_chunk)
                merged_rows.append((None, f">>>>>>> RIGHT: {right_name}", "conflict"))
            elif operation == "delete":
                self._append_aligned_rows(left_rows, right_rows, left_chunk, [], left_start, right_start, "removed", "normal")
                merged_rows.extend((None, line, "merged_left") for line in left_chunk)
            elif operation == "insert":
                self._append_aligned_rows(left_rows, right_rows, [], right_chunk, left_start, right_start, "normal", "added")
                merged_rows.extend((None, line, "merged_right") for line in right_chunk)

        if "left" not in self.editing_sides:
            self._render_rows(self.left_view, left_rows)
        if "right" not in self.editing_sides:
            self._render_rows(self.right_view, right_rows)
        numbered_merged_rows: list[tuple[int | None, str, str]] = [
            (index + 1, line, tag) for index, (_, line, tag) in enumerate(merged_rows)
        ]
        generated_merged_text = "\n".join(line for _line_number, line, _tag in merged_rows)
        if self.merged_override is None:
            self.merged_text = generated_merged_text
        if not self.is_editing_merged:
            if self.merged_override is None:
                self._render_rows(self.merged_view, numbered_merged_rows)
            else:
                override_rows: list[tuple[int | None, str, str]] = [
                    (index + 1, line, "normal") for index, line in enumerate(self.merged_text.splitlines())
                ]
                self._render_rows(self.merged_view, override_rows)
        additions = sum(1 for _, _, tag in right_rows if tag == "added")
        removals = sum(1 for _, _, tag in left_rows if tag == "removed")
        changed = max(sum(1 for _, _, tag in left_rows if tag == "changed"), sum(1 for _, _, tag in right_rows if tag == "changed"))
        conflicts = sum(1 for _line_number, line, tag in merged_rows if tag == "conflict" and line.startswith("<<<<<<<"))
        self.app.status.config(text=f"{additions} added · {removals} removed · {changed} changed · {conflicts} merge conflicts")

    def _read_initial_text(self, path: Path) -> str:
        """Read an initial path without interrupting app construction on failure."""
        try:
            return path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as error:
            self.after_idle(lambda: messagebox.showerror(APP_NAME, f"Could not open {path.name}:\n{error}"))
            return ""

    def _append_aligned_rows(
        self,
        left_rows: list[tuple[int | None, str, str]],
        right_rows: list[tuple[int | None, str, str]],
        left_chunk: list[str],
        right_chunk: list[str],
        left_start: int,
        right_start: int,
        left_tag: str,
        right_tag: str,
    ) -> None:
        """Append two unequal line groups while keeping both panes vertically aligned."""
        row_count = max(len(left_chunk), len(right_chunk))
        for offset in range(row_count):
            left_line = left_chunk[offset] if offset < len(left_chunk) else ""
            right_line = right_chunk[offset] if offset < len(right_chunk) else ""
            left_number = left_start + offset + 1 if offset < len(left_chunk) else None
            right_number = right_start + offset + 1 if offset < len(right_chunk) else None
            left_rows.append((left_number, left_line, left_tag if left_number is not None else "normal"))
            right_rows.append((right_number, right_line, right_tag if right_number is not None else "normal"))

    def _render_rows(self, text_view: tk.Text, rows: list[tuple[int | None, str, str]]) -> None:
        """Populate a pane with line numbers and diff-state background tags."""
        text_view.configure(state=tk.NORMAL)
        text_view.delete("1.0", tk.END)
        for line_number, line, tag in rows:
            number = "    " if line_number is None else f"{line_number:>4}"
            text_view.insert(tk.END, f"{number}  {line}\n", ("line_number", tag))
        text_view.configure(state=tk.DISABLED)

    def _update_path_labels(self) -> None:
        self.left_path_label.config(text=str(self.left_path) if self.left_path is not None else "Drop a file here or choose one")
        self.right_path_label.config(text=str(self.right_path) if self.right_path is not None else "Drop a file here or choose one")

    def apply_theme(self, theme: Theme, size: int) -> None:
        """Apply display settings to both comparison panes."""
        body_font = font.Font(family="TkFixedFont", size=size)
        for text_view in (self.left_view, self.merged_view, self.right_view):
            text_view.configure(background=theme.pane_background, foreground=theme.foreground, font=body_font, insertbackground=theme.foreground)
            text_view.tag_configure("line_number", foreground=theme.muted)
            text_view.tag_configure("normal", background=theme.pane_background)
            text_view.tag_configure("added", background=theme.added)
            text_view.tag_configure("removed", background=theme.removed)
            text_view.tag_configure("changed", background=theme.changed)
            text_view.tag_configure("merged_left", background=theme.changed)
            text_view.tag_configure("merged_right", background=theme.added)
            text_view.tag_configure("conflict", background=theme.removed)


class DiffCheckerApp:
    """The root window coordinating multiple file-comparison tabs."""

    def __init__(self, root: tk.Tk, initial_left: Path | None, initial_right: Path | None) -> None:
        self.root = root
        self.theme_name = tk.StringVar(value="Light")
        self.font_size = tk.IntVar(value=DEFAULT_FONT_SIZE)
        self.merged_view_enabled = tk.BooleanVar(value=False)
        self.diffs: list[DiffView] = []
        self.app_icon: tk.PhotoImage | None = None
        self.dragged_tab_index: int | None = None
        self._build_window()
        self._bind_shortcuts()
        self.new_diff(initial_left, initial_right)
        self.root.after_idle(self._activate_window)

    def _build_window(self) -> None:
        self.root.title(APP_NAME)
        self.root.geometry("1280x760")
        self.root.minsize(800, 520)
        self.root.protocol("WM_DELETE_WINDOW", self.close_window)
        self._set_window_icon()
        self._build_menu()
        toolbar = ttk.Frame(self.root, padding=(10, 8))
        toolbar.pack(fill=tk.X)
        ttk.Button(toolbar, text="New Diff", command=lambda: self.new_diff()).pack(side=tk.LEFT)
        ttk.Button(toolbar, text="Compare Files…", command=self.choose_comparison).pack(side=tk.LEFT, padx=(6, 0))
        ttk.Button(toolbar, text="Close Tab", command=self.close_active).pack(side=tk.LEFT, padx=(6, 0))
        ttk.Checkbutton(toolbar, text="Merged View", variable=self.merged_view_enabled, command=self.toggle_merged_view).pack(side=tk.LEFT, padx=(12, 0))
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
        self.status = ttk.Label(self.root, anchor=tk.W, padding=(10, 5))
        self.status.pack(fill=tk.X)

    def _build_menu(self) -> None:
        menu = tk.Menu(self.root)
        file_menu = tk.Menu(menu, tearoff=False)
        file_menu.add_command(label="New Diff", command=lambda: self.new_diff(), accelerator="Ctrl+N")
        file_menu.add_command(label="Compare Files…", command=self.choose_comparison, accelerator="Ctrl+O")
        file_menu.add_command(label="Close Tab", command=self.close_active, accelerator="Ctrl+W")
        file_menu.add_separator()
        file_menu.add_command(label="Quit", command=self.close_window, accelerator="Ctrl+Q")
        menu.add_cascade(label="File", menu=file_menu)
        view_menu = tk.Menu(menu, tearoff=False)
        view_menu.add_checkbutton(label="Merged View", variable=self.merged_view_enabled, command=self.toggle_merged_view)
        menu.add_cascade(label="View", menu=view_menu)
        self.root.config(menu=menu)

    def _bind_shortcuts(self) -> None:
        self.root.bind_all("<Control-n>", lambda _event: self.new_diff())
        self.root.bind_all("<Command-n>", lambda _event: self.new_diff())
        self.root.bind_all("<Control-o>", lambda _event: self.choose_comparison())
        self.root.bind_all("<Command-o>", lambda _event: self.choose_comparison())
        self.root.bind_all("<Control-w>", self._close_tab_shortcut)
        self.root.bind_all("<Command-w>", self._close_tab_shortcut)
        self.root.bind_all("<Control-q>", self._quit_shortcut)
        self.root.bind_all("<Command-q>", self._quit_shortcut)

    def new_diff(self, left: Path | None = None, right: Path | None = None) -> None:
        """Create and focus a new comparison tab."""
        diff_view = DiffView(self.notebook, self, left, right)
        self.diffs.append(diff_view)
        self.notebook.add(diff_view, text=diff_view.label)
        self.notebook.select(diff_view)
        diff_view.set_merged_visible(self.merged_view_enabled.get())
        self.apply_theme()
        self.update_tab_label(diff_view)

    def choose_comparison(self) -> None:
        """Prompt for both files, then create a new comparison tab."""
        left = filedialog.askopenfilename(title="Choose left file")
        if not left:
            return
        right = filedialog.askopenfilename(title="Choose right file")
        if right:
            self.new_diff(Path(left), Path(right))

    def register_drop_target(self, widget: tk.Misc, diff_view: DiffView, side: PaneSide) -> None:
        """Enable dropping one replacement file onto one side of a comparison."""
        if DND_FILES is None:
            return
        register_target = getattr(widget, "drop_target_register", None)
        bind_drop = getattr(widget, "dnd_bind", None)
        if not callable(register_target) or not callable(bind_drop):
            return
        register_target(DND_FILES)
        bind_drop("<<Drop>>", lambda event: self._on_file_dropped(event, diff_view, side))

    def _on_file_dropped(self, event: tk.Event[tk.Misc], diff_view: DiffView, side: PaneSide) -> None:
        """Load the first dropped file into the side the user targeted."""
        event_data = getattr(event, "data", "")
        if not isinstance(event_data, str):
            return
        dropped_paths = [Path(path) for path in self.root.tk.splitlist(event_data)]
        file_path = next((path for path in dropped_paths if path.is_file()), None)
        if file_path is None:
            self.status.config(text="Drop a file onto the left or right pane.")
            return
        diff_view.load_file(side, file_path)

    def active_diff(self) -> DiffView | None:
        """Return the currently selected comparison tab."""
        selected = self.notebook.select()
        return next((diff_view for diff_view in self.diffs if str(diff_view) == selected), None)

    def close_active(self) -> None:
        """Close the selected comparison, closing the app after its last tab."""
        diff_view = self.active_diff()
        if diff_view is None or not diff_view.confirm_close():
            return
        if len(self.diffs) == 1:
            self.root.destroy()
            return
        self.notebook.forget(diff_view)
        self.diffs.remove(diff_view)
        diff_view.destroy()

    def close_window(self) -> None:
        """Close only after resolving any active pane edits in every tab."""
        for diff_view in self.diffs:
            if not diff_view.confirm_close():
                return
        self.root.destroy()

    def _close_tab_shortcut(self, _event: tk.Event[tk.Misc]) -> str:
        """Close the active tab and suppress duplicate platform handling."""
        self.close_active()
        return "break"

    def _quit_shortcut(self, _event: tk.Event[tk.Misc]) -> str:
        """Close the app and suppress duplicate platform handling."""
        self.close_window()
        return "break"

    def toggle_merged_view(self) -> None:
        """Show or hide the generated center pane across every comparison tab."""
        enabled = self.merged_view_enabled.get()
        for diff_view in self.diffs:
            diff_view.set_merged_visible(enabled)

    def apply_theme(self, _event: tk.Event[tk.Misc] | None = None) -> None:
        """Apply the selected theme and text size across all open comparisons."""
        theme = THEMES[self.theme_name.get()]
        self.root.configure(background=theme.background)
        for diff_view in self.diffs:
            diff_view.apply_theme(theme, self.font_size.get())

    def update_tab_label(self, diff_view: DiffView) -> None:
        """Refresh one tab label and the active window title."""
        self.notebook.tab(diff_view, text=diff_view.label)
        if self.active_diff() is diff_view:
            self._show_active_diff()

    def _on_tab_changed(self, _event: tk.Event[tk.Misc]) -> None:
        self._show_active_diff()

    def _show_active_diff(self) -> None:
        diff_view = self.active_diff()
        self.root.title(APP_NAME if diff_view is None else f"{diff_view.label} — {APP_NAME}")

    def _start_tab_drag(self, event: tk.Event[tk.Misc]) -> None:
        """Start reordering only when the mouse press originated on a tab."""
        try:
            self.dragged_tab_index = self.notebook.index(f"@{event.x},{event.y}")
        except tk.TclError:
            self.dragged_tab_index = None

    def _drag_tab(self, event: tk.Event[tk.Misc]) -> None:
        """Move the tab when the pointer crosses another tab."""
        if self.dragged_tab_index is None:
            return
        try:
            target_index = self.notebook.index(f"@{event.x},{event.y}")
        except tk.TclError:
            return
        if target_index != self.dragged_tab_index:
            tab_id = self.notebook.tabs()[self.dragged_tab_index]
            self.notebook.insert(target_index, tab_id)
            self.dragged_tab_index = target_index

    def _finish_tab_drag(self, _event: tk.Event[tk.Misc]) -> None:
        """Clear transient tab-drag state when the pointer is released."""
        self.dragged_tab_index = None

    def _activate_window(self) -> None:
        """Request foreground focus after Tk finishes constructing the window."""
        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()

    def _set_window_icon(self) -> None:
        """Load an optional PNG icon without preventing the app from starting."""
        icon_path = Path(__file__).parent / "assets" / "icon.png"
        if not icon_path.is_file():
            return
        try:
            self.app_icon = tk.PhotoImage(master=self.root, file=icon_path)
            self.root.iconphoto(True, self.app_icon)
        except (OSError, tk.TclError) as error:
            self.root.after_idle(lambda: self.status.config(text=f"Could not load app icon: {error}"))


def launch(initial_left: Path | None, initial_right: Path | None) -> None:
    """Create and run the desktop diff checker."""
    root = TkinterDnD.Tk() if TkinterDnD is not None else tk.Tk()
    DiffCheckerApp(root, initial_left, initial_right)
    root.mainloop()
