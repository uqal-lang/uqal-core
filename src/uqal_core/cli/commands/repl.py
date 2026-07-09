"""
CLI command: uqal start

Interactive REPL with:
  - Command history (arrow keys up/down)
  - Tab completion (connections, tables, keywords, CLI commands)
  - Auto-suggest from history (grey text)
  - Multi-line mode (>> / << normal, >>-d / << debug)
  - Output format: set output table/json/csv or | table/json/csv
  - All CLI commands available directly
  - Ctrl+C cancels input or aborts running query
"""

from __future__ import annotations

import signal
import threading
from pathlib import Path
from typing import Any

import click
from click.testing import CliRunner as _CliRunner
from prompt_toolkit import PromptSession
from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
from prompt_toolkit.completion import WordCompleter
from prompt_toolkit.history import FileHistory

from uqal_core.config.loader import load_connections_into_engine
from uqal_core.engine import Engine

BANNER = """
╔══════════════════════════════════════════════╗
║   UQAL - Universal Query Language            ║
║                                              ║
║   exit / quit    Exit the REPL               ║
║   >>             Start multi-line input      ║
║   >>-d           Start multi-line debug mode ║
║   <<             Execute multi-line block    ║
║   Ctrl+C         Cancel current input        ║
║   Tab            Auto-complete               ║
║   ↑ / ↓          Command history             ║
║   help           Show available commands     ║
╚══════════════════════════════════════════════╝
"""

HELP_TEXT = """
REPL commands:
  exit / quit            Exit the REPL
  help                   Show this help
  load <module>          Load a module

Output format:
  set output table       Default table view
  set output json        JSON output
  set output csv         CSV output
  <query> | table        One-time format override
  <query> | json         One-time format override
  <query> | csv          One-time format override

Multi-line mode:
  >>                     Start block (only output statements shown)
  >>-d                   Start block in debug mode (all steps shown)
  <<                     Execute block
  Ctrl+C                 Cancel input or abort running query

Output in blocks:
  output x               Show variable x
  output x, y, z         Show multiple variables

CLI commands (all work directly in REPL):
  list-modules           Show available modules
  list-connections       Show registered connections
  add-connection         Register a new connection
  update-connection      Update a connection
  remove-connection      Remove a connection
  test-connection        Test if a connection is reachable
  add-module             Add a community module
  script list/run/edit   Manage scripts
  cache status/clear     Manage schema cache
  run "<script>"         Run inline UQAL script

UQAL examples:
  testdb.list_tables
  testdb.users.get_table(where active = true, fields id, name)
  testdb.users.get_table(fields id, name) | json
  testdb.orders.get_value(where id = 1, field amount)
  testdb.sql("SELECT * FROM orders LIMIT 5")
  list dbs
  list modules

  >>
  let price1 = testdb.products.get_value(where id = 1, field price)
  let price2 = testdb.products.get_value(where id = 2, field price)
  let total = price1 + price2
  output total
  

  >>-d
  let a = testdb.orders.get_value(where id = 1, field amount)
  let b = a + 100
  
"""

_BLOCKED_IN_REPL = {"start"}

_CLI_COMMANDS = {
    "add-connection", "update-connection", "remove-connection",
    "list-connections", "test-connection", "set-config-path",
    "add-module", "list-modules", "run", "script", "cache",
}

_VALID_FORMATS = {"table", "json", "csv"}

_CANCEL_EVENT = threading.Event()


def _parse_pipe(line: str) -> tuple[str, str]:
    """
    Splits 'query | format' into (query, format).
    Returns (line, "") if no pipe or unknown format.
    """
    if " | " in line:
        parts = line.rsplit(" | ", 1)
        fmt = parts[1].strip().lower()
        if fmt in _VALID_FORMATS:
            return parts[0].strip(), fmt
    return line, ""


def _build_completer(engine: Engine) -> WordCompleter:
    words = [
        # REPL commands
        "exit", "quit", "help", "load",
        "set output table", "set output json", "set output csv",
        # CLI commands
        "list-connections", "list-modules", "add-connection",
        "update-connection", "remove-connection", "test-connection",
        "add-module", "script", "cache", "run",
        # UQAL keywords
        "let", "if", "elif", "else", "for", "while", "in",
        "return", "function", "output",
        "get", "get_value", "get_row", "get_table",
        "insert_table", "insert_row", "update", "delete",
        "query", "table", "where", "fields", "field",
        "list", "dbs", "modules", "connect", "as",
        "sync_schema", "list_tables",
        "true", "false", "null",
        "and", "or", "not", "is",
        "integer", "float", "string", "boolean", "datetime",
    ]

    try:
        connections = engine.list_connections()
        for conn in connections:
            words.extend([
                conn,
                f"{conn}.list_tables",
                f"{conn}.list_tables(live = true)",
                f"{conn}.sync_schema",
                f"{conn}.sql(",
                f"{conn}.mongo(",
                f"{conn}.query:",
            ])
            try:
                schema = engine._module_registry.get_schema(conn)
                for table in schema.list_tables():
                    words.extend([
                        f"{conn}.{table}",
                        f"{conn}.{table}.get(",
                        f"{conn}.{table}.get_value(",
                        f"{conn}.{table}.get_row(",
                        f"{conn}.{table}.get_table(",
                        f"{conn}.{table}.insert_row(",
                        f"{conn}.{table}.update(",
                        f"{conn}.{table}.delete(",
                    ])
            except KeyError:
                pass
    except Exception:
        pass

    return WordCompleter(
        words,
        ignore_case=True,
        sentence=True,
    )


class QueryRunner:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine
        self._result: Any = None
        self._error: str | None = None
        self._thread: threading.Thread | None = None

    def run(self, script: str) -> Any:
        _CANCEL_EVENT.clear()
        self._result = None
        self._error = None

        self._thread = threading.Thread(
            target=self._execute,
            args=(script,),
            daemon=True,
        )
        self._thread.start()

        while self._thread.is_alive():
            self._thread.join(timeout=0.1)
            if _CANCEL_EVENT.is_set():
                raise KeyboardInterrupt("Query cancelled by user.")

        if self._error:
            raise RuntimeError(self._error)
        return self._result

    def _execute(self, script: str) -> None:
        try:
            self._result = self._engine.run_script(script)
        except Exception as exc:
            self._error = str(exc)


@click.command("start")
@click.option("--module", "-m", multiple=True)
@click.option(
    "--output", "-o",
    type=click.Choice(["table", "json", "csv"], case_sensitive=False),
    default="table",
    help="Default output format for this session.",
)
def start(module: tuple[str, ...], output: str) -> None:
    """
    Start the interactive UQAL REPL.

    Features: command history (↑/↓), tab completion, multi-line
    mode (>> / <<), debug mode (>>-d / <<), output format control.

    Examples:
        uqal start
        uqal start --output json
        uqal start --module standard.dummy
    """
    click.echo(BANNER)

    engine = Engine()

    loaded_connections = load_connections_into_engine(engine)
    if loaded_connections:
        click.echo(
            click.style(
                f"Connections loaded: {', '.join(loaded_connections)}",
                fg="green",
            )
        )

    if module:
        try:
            engine.load_modules(list(module))
            click.echo(
                click.style(
                    f"Modules loaded: {', '.join(module)}",
                    fg="green",
                )
            )
        except Exception as exc:
            click.echo(click.style(f"Warning: {exc}", fg="yellow"))

    runner = QueryRunner(engine)
    repl_cli_runner = _CliRunner()

    history_path = Path(".uqal") / "repl_history"
    history_path.parent.mkdir(parents=True, exist_ok=True)

    session: PromptSession = PromptSession(
        history=FileHistory(str(history_path)),
        auto_suggest=AutoSuggestFromHistory(),
        completer=_build_completer(engine),
        complete_while_typing=False,
    )

    original_sigint = signal.getsignal(signal.SIGINT)

    def _sigint_handler(sig, frame):
        _CANCEL_EVENT.set()

    signal.signal(signal.SIGINT, _sigint_handler)

    multiline_buffer: list[str] = []
    multiline_mode = False
    multiline_debug = False
    output_format = output  # session-wide default

    try:
        while True:
            try:
                prompt = "... " if multiline_mode else "uqal > "

                try:
                    line = session.prompt(prompt)
                except KeyboardInterrupt:
                    if multiline_mode:
                        multiline_buffer.clear()
                        multiline_mode = False
                        multiline_debug = False
                        click.echo(
                            click.style(
                                "\nMulti-line input cancelled.",
                                fg="yellow",
                            )
                        )
                    else:
                        click.echo(
                            click.style(
                                "\nInput cancelled. "
                                "Type 'exit' to quit.",
                                fg="yellow",
                            )
                        )
                    continue
                except EOFError:
                    click.echo("\nBye.")
                    break

                line = line.strip()

                if not line:
                    continue

                # ---- Exit ----
                if line in ("exit", "quit"):
                    click.echo("Bye.")
                    break

                # ---- Help ----
                if line == "help":
                    click.echo(HELP_TEXT)
                    continue

                # ---- Set output format ----
                if line.startswith("set output "):
                    fmt = line[11:].strip().lower()
                    if fmt in _VALID_FORMATS:
                        output_format = fmt
                        click.echo(
                            click.style(
                                f"Output format set to '{fmt}'.",
                                fg="green",
                            )
                        )
                    else:
                        click.echo(
                            click.style(
                                f"Unknown format '{fmt}'. "
                                f"Use: table, json, csv",
                                fg="red",
                            )
                        )
                    continue

                # ---- Load module shortcut ----
                if line.startswith("load "):
                    module_name = line[5:].strip()
                    try:
                        engine.load_modules([module_name])
                        click.echo(
                            click.style(
                                f"Loaded: {module_name}", fg="green"
                            )
                        )
                    except Exception as exc:
                        click.echo(
                            click.style(f"Error: {exc}", fg="red")
                        )
                    continue

                # ---- Multi-line mode ----
                if line in (">>", ">>-d"):
                    if multiline_mode:
                        click.echo(
                            click.style(
                                "Already in multi-line mode. "
                                "Use << to execute or Ctrl+C to cancel.",
                                fg="yellow",
                            )
                        )
                        continue

                    multiline_debug = line == ">>-d"
                    multiline_mode = True
                    multiline_buffer.clear()
                    mode_label = "debug " if multiline_debug else ""
                    click.echo(
                        click.style(
                            f"Multi-line {mode_label}mode"
                            f" — type << to execute, "
                            f"Ctrl+C to cancel.",
                            fg="cyan",
                        )
                    )
                    continue

                if line == "<<":
                    if not multiline_mode:
                        click.echo(
                            click.style(
                                "Not in multi-line mode. "
                                "Use >> to start.",
                                fg="yellow",
                            )
                        )
                        continue

                    multiline_mode = False
                    script = "\n".join(multiline_buffer)
                    multiline_buffer.clear()
                    current_debug = multiline_debug
                    multiline_debug = False

                    if not script.strip():
                        click.echo(
                            click.style(
                                "Empty block, nothing to run.",
                                fg="yellow",
                            )
                        )
                        continue

                    _execute_and_print(
                        runner,
                        script,
                        debug=current_debug,
                        single_line=False,
                        output_format=output_format,
                    )
                    continue

                if multiline_mode:
                    multiline_buffer.append(line)
                    continue

                # ---- CLI command forwarding ----
                first_word = line.split()[0] if line.split() else ""

                if first_word in _BLOCKED_IN_REPL:
                    click.echo(
                        click.style(
                            f"'{first_word}' cannot be used inside "
                            f"the REPL.",
                            fg="yellow",
                        )
                    )
                    continue

                if first_word in _CLI_COMMANDS:
                    from uqal_core.cli.main import cli
                    args = line.split()
                    result = repl_cli_runner.invoke(
                        cli, args, catch_exceptions=True
                    )
                    click.echo(result.output, nl=False)
                    if result.exit_code != 0 and result.exception:
                        click.echo(
                            click.style(
                                f"Command failed "
                                f"(exit {result.exit_code})",
                                fg="red",
                            )
                        )
                    elif result.exit_code == 0 and first_word in {
                        "add-connection",
                        "remove-connection",
                        "update-connection",
                    }:
                        # Reload connections + rebuild completer
                        newly_loaded = load_connections_into_engine(engine)
                        if newly_loaded:
                            click.echo(
                                click.style(
                                    f"Connections reloaded: "
                                    f"{', '.join(newly_loaded)}",
                                    fg="green",
                                )
                            )
                        session.completer = _build_completer(engine)
                    continue

                # ---- Single-line UQAL statement ----
                # Parse pipe format override
                script_line, pipe_format = _parse_pipe(line)
                effective_format = (
                    pipe_format if pipe_format else output_format
                )

                _execute_and_print(
                    runner,
                    script_line,
                    debug=False,
                    single_line=True,
                    output_format=effective_format,
                )

            except (EOFError, KeyboardInterrupt):
                click.echo("\nBye.")
                break

    finally:
        signal.signal(signal.SIGINT, original_sigint)


def _execute_and_print(
    runner: QueryRunner,
    script: str,
    debug: bool = False,
    single_line: bool = True,
    output_format: str = "table",
) -> None:
    """
    Executes a script and prints results according to mode:
      single_line=True:  always print (user typed one line)
      debug=True:        print every step result
      block mode:        only print output statements
    """
    try:
        result = runner.run(script)

        for step in result.steps:
            if step["status"] == "failed":
                click.echo(
                    click.style(
                        f"Error: {step.get('error', 'unknown')}",
                        fg="red",
                    )
                )
                continue

            value = step.get("result")
            is_output = step.get("is_output", False)

            if debug:
                if value is not None and value != "":
                    _print_value(value, output_format)

            elif single_line:
                if value is not None and value != "":
                    _print_value(value, output_format)

            else:
                # Block mode: only output statements
                if is_output and isinstance(value, dict):
                    for name, val in value.items():
                        click.echo(
                            click.style(f"{name}: ", fg="cyan"),
                            nl=False,
                        )
                        _print_value(val, output_format)

    except KeyboardInterrupt:
        click.echo(click.style("\nQuery cancelled.", fg="yellow"))
    except Exception as exc:
        click.echo(click.style(f"Error: {exc}", fg="red"))


def _print_value(value: Any, output_format: str = "table") -> None:
    """Prints a value in the requested format."""
    from uqal_core.execution.result_set import ResultSet

    if isinstance(value, ResultSet):
        if output_format == "json":
            click.echo(value.to_json())
        elif output_format == "csv":
            click.echo(value.to_csv())
        else:
            # table (default)
            click.echo(click.style("→ ", fg="green"))
            click.echo(str(value))
    else:
        click.echo(click.style("→ ", fg="green") + str(value))