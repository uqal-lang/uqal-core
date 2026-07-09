"""
CLI command: uqal list-modules

Lists all modules currently available to the ModuleLoader, grouped
by discovery source (entry points vs. built-in/community).
"""

from __future__ import annotations

import click

from uqal_core.module_loader import ModuleLoader
from uqal_core.registry.module_registry import ModuleRegistry


@click.command("list-modules")
def list_modules() -> None:
    """
    List all UQAL modules currently available (installed via uv or
    added via add-module).
    """
    registry = ModuleRegistry()
    loader = ModuleLoader(registry=registry)
    available = loader.list_available()

    if not available:
        click.echo("No modules found.")
        click.echo(
            "Install a module with 'uv add uqal-<name>' or add one "
            "manually with 'uqal add-module <path>'."
        )
        return

    click.echo(f"Available modules ({len(available)}):")
    for name in available:
        click.echo(f"  - {name}")