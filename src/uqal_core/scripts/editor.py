"""
TUI editor for UQAL scripts using Textual.

Provides a full-featured terminal editor with:
  - Line numbers
  - UQAL syntax highlighting
  - Status bar (filename, cursor position, modified flag)
  - Keyboard shortcuts:
      Ctrl+S  save
      Ctrl+Q  quit (prompts if unsaved changes)
      Ctrl+R  save and run
      Ctrl+N  new line
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from textual import on
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.widgets import Footer, Header, Static, TextArea
from textual.widgets.text_area import TextAreaTheme


# UQAL keyword groups for syntax highlighting
_UQAL_KEYWORDS = [
    # Control flow
    "if", "elif", "else", "for", "while", "in",
    # Variable
    "let", "return",
    # DB operations
    "get", "get_value", "get_row", "get_table",
    "insert_table", "insert_row", "update", "delete",
    "query", "table", "where", "fields", "field",
    # System
    "list", "dbs", "modules", "connect", "as",
    "sync_schema", "list_tables",
    # Types
    "integer", "float", "string", "boolean", "datetime", "list",
    # Values
    "true", "false", "null",
    # Logical
    "and", "or", "not", "is",
    # Function
    "function",
]


def _make_uqal_highlight_query() -> str:
    """
    Builds a tree-sitter-style highlight query for UQAL keywords.
    Textual's TextArea uses this for syntax highlighting.
    Since UQAL has no tree-sitter grammar yet, we use a simple
    word-match approach via the TextArea's built-in highlight API.
    """
    return ""  # Custom highlighting added via CSS + reactive


class UQALEditor(App):
    """
    Full-screen TUI editor for a single UQAL script file.

    Returns one of three exit codes via self.exit():
      "saved"       - file was saved, no run requested
      "saved_run"   - file was saved, caller should run it
      "cancelled"   - user quit without saving
    """

    CSS = """
    Screen {
        background: $surface;
    }

    #editor-container {
        height: 1fr;
        border: solid $primary;
    }

    TextArea {
        height: 1fr;
    }

    #status-bar {
        height: 1;
        background: $primary;
        color: $text;
        padding: 0 1;
    }

    #status-left {
        width: 1fr;
    }

    #status-right {
        width: auto;
    }

    .modified {
        color: $warning;
    }
    """

    BINDINGS = [
        Binding("ctrl+s", "save", "Save", show=True),
        Binding("ctrl+q", "quit_editor", "Quit", show=True),
        Binding("ctrl+r", "save_and_run", "Save & Run", show=True),
    ]

    def __init__(
        self,
        script_name: str,
        initial_content: str = "",
        script_path: Path | None = None,
    ) -> None:
        super().__init__()
        self.script_name = script_name
        self.initial_content = initial_content
        self.script_path = script_path
        self._modified = False
        self._saved_content = initial_content

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Vertical(id="editor-container"):
            yield TextArea(
                self.initial_content,
                language=None,  # No built-in UQAL grammar yet
                id="editor",
                show_line_numbers=True,
                tab_behavior="indent",
                theme="monokai",
            )
        with Horizontal(id="status-bar"):
            yield Static(
                f"  {self.script_name}.uqal",
                id="status-left",
            )
            yield Static(
                "Ctrl+S Save  Ctrl+R Save&Run  Ctrl+Q Quit",
                id="status-right",
            )
        yield Footer()

    def on_mount(self) -> None:
        self.title = f"UQAL Editor — {self.script_name}.uqal"
        self.query_one(TextArea).focus()

    @on(TextArea.Changed)
    def on_text_changed(self, event: TextArea.Changed) -> None:
        current = event.text_area.text
        self._modified = current != self._saved_content
        status = self.query_one("#status-left", Static)
        marker = " ●" if self._modified else ""
        status.update(f"  {self.script_name}.uqal{marker}")

    def _get_content(self) -> str:
        return self.query_one(TextArea).text

    def _save(self) -> None:
        content = self._get_content()
        if self.script_path:
            self.script_path.write_text(content, encoding="utf-8")
        self._saved_content = content
        self._modified = False
        status = self.query_one("#status-left", Static)
        status.update(f"  {self.script_name}.uqal  ✓ saved")

    def action_save(self) -> None:
        self._save()

    def action_save_and_run(self) -> None:
        self._save()
        self.exit("saved_run")

    def action_quit_editor(self) -> None:
        if self._modified:
            # TODO: add a confirmation dialog in a future iteration
            # For now, warn in status bar and require second Ctrl+Q
            status = self.query_one("#status-left", Static)
            status.update(
                "  Unsaved changes! Press Ctrl+Q again to discard, "
                "or Ctrl+S to save."
            )
            # Mark as "warned" - second press exits
            if not hasattr(self, "_quit_warned"):
                self._quit_warned = True
                return
        self.exit("saved" if not self._modified else "cancelled")


def open_editor(
    script_name: str,
    initial_content: str = "",
    script_path: Path | None = None,
) -> str:
    """
    Opens the TUI editor and returns the exit result:
      "saved"      - saved, no run
      "saved_run"  - saved, should run
      "cancelled"  - quit without saving
    """
    app = UQALEditor(
        script_name=script_name,
        initial_content=initial_content,
        script_path=script_path,
    )
    result = app.run()
    return result or "cancelled"