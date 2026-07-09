"""
CLI command: uqal run <script>

Runs a UQAL script passed as a string argument or from a file.
"""

from __future__ import annotations

from pathlib import Path

import click

from uqal_core.engine import Engine
from uqal_core.config.loader import load_connections_into_engine


@click.command("run")
@click.argument("script", required=False)
@click.option(
    "--file", "-f",
    type=click.Path(exists=True, dir_okay=False),
    default=None,
    help="Path to a .uqal script file to execute.",
)
@click.option(
    "--module", "-m",
    multiple=True,
    help="Module(s) to load before running.",
)
@click.option(
    "--output", "-o",
    type=click.Choice(["table", "json", "csv"], case_sensitive=False),
    default="table",
    help="Output format for ResultSet results (default: table).",
)
def run(
    script: str | None,
    file: str | None,
    module: tuple[str, ...],
    output: str,
) -> None:
    """
    Run a UQAL script.

    Pass the script directly as an argument or use --file to read
    from a .uqal file. Connections from uqal_config.json are loaded
    automatically.

    Examples:

        uqal run "let a = 5"

        uqal run --file my_script.uqal

        uqal run --output json "testdb.users.get_table(fields id, name)"

        uqal run --module standard.dummy "list modules"
    """
    if not script and not file:
        click.echo(
            click.style(
                "Error: provide a script as an argument or use --file.",
                fg="red",
            )
        )
        raise SystemExit(1)

    engine = Engine()

    loaded = load_connections_into_engine(engine)
    if loaded:
        click.echo(
            click.style(
                f"Connections loaded: {', '.join(loaded)}",
                fg="green",
            )
        )

    if module:
        try:
            engine.load_modules(list(module))
        except Exception as exc:
            click.echo(
                click.style(f"Error loading modules: {exc}", fg="red")
            )
            raise SystemExit(1)

    if file:
        script = Path(file).read_text(encoding="utf-8")

    result = engine.run_script(script)

    for step in result.steps:
        if step["status"] == "success":
            value = step.get("result")
            _print_step_result(value, step["step"], output)
        else:
            click.echo(
                click.style(
                    f"[step {step['step']}] failed: "
                    f"{step.get('error', '')}",
                    fg="red",
                )
            )

    if result.is_success():
        click.echo(click.style("Done.", fg="green"))
    else:
        click.echo(
            click.style(
                f"{len(result.failed_steps())} step(s) failed.",
                fg="red",
            )
        )
        raise SystemExit(1)


def _print_step_result(
    value: Any,
    step_num: int,
    output_format: str,
) -> None:
    """Prints a step result in the requested format."""
    from uqal_core.execution.result_set import ResultSet
    from typing import Any

    if value is None or value == "":
        click.echo(click.style(f"[step {step_num}] ok", fg="green"))
        return

    if isinstance(value, ResultSet):
        click.echo(
            click.style(f"[step {step_num}] ok", fg="green")
        )
        if output_format == "json":
            click.echo(value.to_json())
        elif output_format == "csv":
            click.echo(value.to_csv())
        else:
            click.echo(str(value))
    else:
        click.echo(
            click.style(f"[step {step_num}] ok", fg="green")
            + f"  {value}"
        )