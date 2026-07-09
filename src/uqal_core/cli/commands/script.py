"""
CLI command group: uqal script

Manages UQAL script files in .uqal/scripts/.
"""

from __future__ import annotations

import click

from uqal_core.scripts.script_manager import ScriptManager
from uqal_core.scripts.editor import open_editor
from uqal_core.config.loader import load_connections_into_engine
from uqal_core.engine import Engine


@click.group("script")
def script_group() -> None:
    """
    Manage and run UQAL scripts.

    Scripts are .uqal files stored in .uqal/scripts/ and can be
    run by name without specifying the full path or extension.

    Examples:

        uqal script edit my_report
        uqal script run my_report
        uqal script list
    """
    pass


@script_group.command("edit")
@click.argument("name")
def script_edit(name: str) -> None:
    """
    Open a script in the TUI editor.

    Creates the script if it does not exist yet.
    Use Ctrl+S to save, Ctrl+R to save and run, Ctrl+Q to quit.

    Example:

        uqal script edit my_report
    """
    manager = ScriptManager()
    initial = ""

    if manager.exists(name):
        initial = manager.read(name)
    else:
        click.echo(
            click.style(f"Creating new script '{name}'...", fg="cyan")
        )
        initial = f"// Script: {name}\n// Created by UQAL editor\n\n"

    script_path = manager.script_path(name)

    result = open_editor(
        script_name=name,
        initial_content=initial,
        script_path=script_path,
    )

    if result == "saved":
        click.echo(click.style(f"Script '{name}' saved.", fg="green"))

    elif result == "saved_run":
        click.echo(click.style(f"Script '{name}' saved.", fg="green"))
        _run_script(name, manager)

    elif result == "cancelled":
        click.echo(click.style("No changes saved.", fg="yellow"))


@script_group.command("run")
@click.argument("name")
@click.option(
    "--module", "-m",
    multiple=True,
    help="Additional module(s) to load before running.",
)
def script_run(name: str, module: tuple[str, ...]) -> None:
    """
    Run a saved UQAL script by name.

    Example:

        uqal script run my_report
        uqal script run my_report --module standard.postgresql
    """
    manager = ScriptManager()
    _run_script(name, manager, extra_modules=list(module))


@script_group.command("list")
def script_list() -> None:
    """
    List all available scripts in .uqal/scripts/.

    Includes scripts created via 'uqal script edit' and any .uqal
    files placed manually in the directory.

    Example:

        uqal script list
    """
    manager = ScriptManager()
    scripts = manager.list_scripts()

    if not scripts:
        click.echo("No scripts found.")
        click.echo(
            f"Create one with: uqal script edit <name>\n"
            f"Or place a .uqal file in: {manager.scripts_dir()}"
        )
        return

    click.echo(f"Available scripts ({len(scripts)}):\n")
    for name in scripts:
        path = manager.script_path(name)
        size = path.stat().st_size
        modified = path.stat().st_mtime
        import datetime
        dt = datetime.datetime.fromtimestamp(modified).strftime(
            "%Y-%m-%d %H:%M"
        )
        click.echo(
            f"  {click.style(name, fg='cyan', bold=True)}"
            f"  {dt}  {size} bytes"
        )
    click.echo()
    click.echo(f"Scripts directory: {manager.scripts_dir()}")


@script_group.command("delete")
@click.argument("name")
@click.option(
    "--yes", "-y",
    is_flag=True,
    default=False,
    help="Skip confirmation prompt.",
)
def script_delete(name: str, yes: bool) -> None:
    """
    Delete a script.

    Example:

        uqal script delete my_report
        uqal script delete my_report --yes
    """
    manager = ScriptManager()

    if not manager.exists(name):
        click.echo(
            click.style(f"Script '{name}' not found.", fg="red")
        )
        raise SystemExit(1)

    if not yes:
        click.confirm(
            f"Delete script '{name}'?",
            abort=True,
        )

    manager.delete(name)
    click.echo(click.style(f"Script '{name}' deleted.", fg="green"))


@script_group.command("rename")
@click.argument("old_name")
@click.argument("new_name")
def script_rename(old_name: str, new_name: str) -> None:
    """
    Rename a script.

    Example:

        uqal script rename my_report final_report
    """
    manager = ScriptManager()

    try:
        manager.rename(old_name, new_name)
        click.echo(
            click.style(
                f"Script '{old_name}' renamed to '{new_name}'.",
                fg="green",
            )
        )
    except FileNotFoundError as e:
        click.echo(click.style(str(e), fg="red"))
        raise SystemExit(1)
    except FileExistsError as e:
        click.echo(click.style(str(e), fg="red"))
        raise SystemExit(1)


@script_group.command("show")
@click.argument("name")
def script_show(name: str) -> None:
    """
    Print the contents of a script to the terminal.

    Example:

        uqal script show my_report
    """
    manager = ScriptManager()

    try:
        content = manager.read(name)
    except FileNotFoundError as e:
        click.echo(click.style(str(e), fg="red"))
        raise SystemExit(1)

    click.echo(
        click.style(f"=== {name}.uqal ===", fg="cyan", bold=True)
    )
    click.echo(content)


# ---- Internal helper ----

def _run_script(
    name: str,
    manager: ScriptManager,
    extra_modules: list[str] | None = None,
) -> None:
    try:
        content = manager.read(name)
    except FileNotFoundError as e:
        click.echo(click.style(str(e), fg="red"))
        raise SystemExit(1)

    engine = Engine()
    load_connections_into_engine(engine)

    if extra_modules:
        try:
            engine.load_modules(extra_modules)
        except Exception as exc:
            click.echo(
                click.style(f"Error loading modules: {exc}", fg="red")
            )
            raise SystemExit(1)

    click.echo(
        click.style(f"Running script '{name}'...", fg="cyan")
    )
    result = engine.run_script(content)

    for step in result.steps:
        if step["status"] == "success":
            click.echo(
                click.style(f"[step {step['step']}] ok", fg="green")
                + f"  {step.get('result', '')}"
            )
        else:
            click.echo(
                click.style(
                    f"[step {step['step']}] failed: {step.get('error', '')}",
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