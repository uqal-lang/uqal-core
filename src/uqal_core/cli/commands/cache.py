"""
CLI commands for cache management.

  uqal cache status   - show sync status per connection
  uqal cache clear    - clear cached schemas
"""

from __future__ import annotations

import click

from uqal_core.cache.cache_manager import CacheManager
from uqal_core.config.config_manager import ConfigManager


@click.group("cache")
def cache_group() -> None:
    """Manage schema cache."""
    pass


@cache_group.command("status")
def cache_status() -> None:
    """
    Show schema cache status for all connections.

    Example:
        uqal cache status
    """
    cache_manager = CacheManager()
    config_manager = ConfigManager()
    connections = config_manager.list_connections()

    if not connections:
        click.echo("No connections registered.")
        return

    cached_info = {
        c["connection"]: c
        for c in cache_manager.list_cached()
    }

    click.echo("Schema cache status:\n")
    for name in connections:
        if name in cached_info:
            info = cached_info[name]
            synced = info["synced_at"][:19].replace("T", " ")
            expired = info["expired"]
            status = (
                click.style("✗ expired", fg="yellow")
                if expired
                else click.style("✓ fresh", fg="green")
            )
            ttl = info["ttl_hours"]
            click.echo(
                f"  {click.style(name, fg='cyan', bold=True)}"
                f"  {status}"
                f"  synced: {synced}"
                f"  ttl: {ttl}h"
            )
        else:
            click.echo(
                f"  {click.style(name, fg='cyan', bold=True)}"
                f"  {click.style('✗ no cache', fg='red')}"
                f"  run: uqal run \"{name}.sync_schema\""
            )
    click.echo()


@cache_group.command("clear")
@click.option(
    "--connection", "-c",
    default=None,
    help="Clear only this connection's cache.",
)
@click.option("--yes", "-y", is_flag=True, default=False)
def cache_clear(connection: str | None, yes: bool) -> None:
    """
    Clear cached schemas.

    Examples:
        uqal cache clear
        uqal cache clear --connection testdb
    """
    target = f"connection '{connection}'" if connection else "all connections"
    if not yes:
        click.confirm(f"Clear schema cache for {target}?", abort=True)

    cache_manager = CacheManager()
    cache_manager.clear(connection)
    click.echo(click.style("Cache cleared.", fg="green"))

@click.command("remove-connection")
@click.argument("name")
@click.option(
    "--secrets",
    is_flag=True,
    default=False,
    help="Also remove secrets from .env.",
)
@click.option(
    "--keep-cache",
    is_flag=True,
    default=False,
    help="Keep the schema cache file (.uqal/schemas/<name>.json).",
)
def remove_connection(name: str, secrets: bool, keep_cache: bool) -> None:
    """
    Remove a registered connection.

    By default also removes the schema cache. Use --keep-cache to
    preserve it.

    Examples:

        uqal remove-connection testdb
        uqal remove-connection testdb --secrets
        uqal remove-connection testdb --keep-cache
    """
    manager = ConfigManager()

    if not manager.remove_connection(name):
        click.echo(
            click.style(f"Error: connection '{name}' not found.", fg="red")
        )
        raise SystemExit(1)

    click.echo(click.style(f"Connection '{name}' removed.", fg="green"))

    if secrets:
        count = manager.remove_secrets(name)
        click.echo(
            click.style(
                f"Removed {count} secret(s) from .env.", fg="green"
            )
        )

    if not keep_cache:
        from uqal_core.cache.cache_manager import CacheManager
        cache = CacheManager()
        cache.clear(name)
        click.echo(
            click.style(
                f"Schema cache for '{name}' cleared.", fg="green"
            )
        )

@cache_group.command("drop-schema")
@click.argument("connection")
@click.option("--yes", "-y", is_flag=True, default=False)
def cache_drop_schema(connection: str, yes: bool) -> None:
    """
    Delete the cached schema for a connection.

    The schema will be re-synced automatically on next access,
    or you can trigger it manually with:
        uqal run "<connection>.sync_schema"

    Example:
        uqal cache drop-schema testdb
    """
    if not yes:
        click.confirm(
            f"Delete cached schema for '{connection}'?",
            abort=True,
        )

    cache_manager = CacheManager()
    path = cache_manager._schema_path(connection)

    if not path.exists():
        click.echo(
            click.style(
                f"No cached schema found for '{connection}'.",
                fg="yellow",
            )
        )
        return

    cache_manager.clear(connection)
    click.echo(
        click.style(
            f"Schema cache for '{connection}' deleted.",
            fg="green",
        )
    )
    click.echo(
        f"Run 'uqal run \"{connection}.sync_schema\"' to re-sync."
    )