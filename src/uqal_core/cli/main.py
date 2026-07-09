"""
UQAL command-line interface entry point.
"""

from __future__ import annotations

import click

from uqal_core.cli.commands.add_connection import (
    add_connection,
    remove_connection,
    list_connections,
    update_connection,
    set_config_path_cmd,
    test_connection,
)
from uqal_core.cli.commands.add_module import add_module
from uqal_core.cli.commands.list_modules import list_modules
from uqal_core.cli.commands.run import run
from uqal_core.cli.commands.repl import start
from uqal_core.cli.commands.script import script_group
from uqal_core.cli.commands.cache import cache_group


@click.group()
def cli() -> None:
    """
    UQAL - Universal Query Abstraction Language

    A modular, database-agnostic query language with a plugin
    architecture.
    """
    pass


cli.add_command(add_module)
cli.add_command(list_modules)
cli.add_command(run)
cli.add_command(start)
cli.add_command(add_connection)
cli.add_command(remove_connection)
cli.add_command(list_connections)
cli.add_command(update_connection)
cli.add_command(set_config_path_cmd, name="set-config-path")
cli.add_command(script_group)
cli.add_command(test_connection, name="test-connection")
cli.add_command(cache_group)


if __name__ == "__main__":
    cli()