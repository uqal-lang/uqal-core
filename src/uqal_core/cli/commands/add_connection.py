"""
CLI commands for connection management.
"""

from __future__ import annotations

from typing import Any

import click

from uqal_core.config.config_manager import ConfigManager, set_config_path
from uqal_core.config.connection_schema import ConnectionField, ConnectionSchema
from uqal_core.module_loader import ModuleLoader
from uqal_core.registry.module_registry import ModuleRegistry


def _load_schema(module_name: str) -> type[ConnectionSchema] | None:
    """
    Tries to load the ConnectionSchema for a given module name.
    Returns None if the module is not found or has no schema.
    """
    try:
        registry = ModuleRegistry()
        loader = ModuleLoader(registry=registry)
        loader.load([module_name])
        module = registry.get_module(module_name)
        return module.get_connection_schema()
    except Exception:
        return None


def _prompt_for_fields(
    schema: type[ConnectionSchema],
    provided: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """
    Interactively prompts for all schema fields that were not already
    provided via flags. Returns (config_values, secret_values).
    """
    all_values = dict(provided)
    config_values: dict[str, Any] = {}
    secret_values: dict[str, Any] = {}

    for field_def in schema.all_fields():
        # Already provided via flag - use that value
        if field_def.name in all_values and all_values[field_def.name] is not None:
            value = all_values[field_def.name]
        else:
            # Check if required given current values
            required = field_def.is_required_given(all_values)
            prompt_text = field_def.name
            if field_def.description:
                prompt_text += f" ({field_def.description})"
            if field_def.default is not None:
                prompt_text += f" [{field_def.default}]"
            if not required:
                prompt_text += " (optional, Enter to skip)"

            if field_def.secret:
                raw = click.prompt(
                    prompt_text,
                    default="" if not required else None,
                    hide_input=True,
                    confirmation_prompt=required,
                    show_default=False,
                )
            else:
                raw = click.prompt(
                    prompt_text,
                    default=(
                        str(field_def.default)
                        if field_def.default is not None
                        else ("" if not required else None)
                    ),
                    show_default=False,
                )

            if not raw and not required:
                continue

            value = field_def.cast(raw) if raw else field_def.default

        if value is None:
            continue

        if field_def.secret:
            secret_values[field_def.name] = str(value)
        else:
            config_values[field_def.name] = value

    return config_values, secret_values


def _apply_schema_to_connection(
    manager: ConfigManager,
    name: str,
    module_type: str,
    modules: list[str],
    provided_flags: dict[str, Any],
    provided_secrets: dict[str, str],
    interactive: bool,
) -> None:
    """
    Core logic shared by add-connection and update-connection.
    Loads schema, prompts if needed, saves config + secrets.
    """
    schema = _load_schema(module_type) if modules else None

    config_values: dict[str, Any] = {}
    secret_values: dict[str, str] = dict(provided_secrets)

    if schema is not None:
        if interactive:
            click.echo(
                click.style(
                    f"\nConfiguring connection '{name}' "
                    f"using schema from '{module_type}':",
                    fg="cyan",
                )
            )
            prompted_config, prompted_secrets = _prompt_for_fields(
                schema, provided_flags
            )
            config_values.update(prompted_config)
            secret_values.update(prompted_secrets)
        else:
            # Flag-only mode: use provided values directly
            for field_def in schema.config_fields():
                if field_def.name in provided_flags:
                    config_values[field_def.name] = provided_flags[field_def.name]
            # Secrets come from --secret flags only in non-interactive mode

        # Validate
        all_values = {**config_values, **secret_values}
        errors = schema.validate(all_values)
        if errors:
            for err in errors:
                click.echo(click.style(f"Validation error: {err}", fg="red"))
            raise SystemExit(1)
    else:
        # No schema available - use raw provided flags
        config_values = {
            k: v for k, v in provided_flags.items()
            if v is not None
        }

    # Save to config
    manager.add_connection(
        connection_name=name,
        module_type=module_type,
        modules=modules,
        host=config_values.pop("host", None),
        port=config_values.pop("port", None),
        database=config_values.pop("database", None),
    )

    # Save any remaining config values as options
    if config_values:
        config = manager.load_config()
        config["connections"][name].update(config_values)
        manager.save_config(config)

    # Save secrets
    for key, value in secret_values.items():
        manager.add_secret(name, key, value)


@click.command("add-connection")
@click.argument("name")
@click.argument("module_type")
@click.option("--host", default=None)
@click.option("--port", default=None, type=int)
@click.option("--database", "--db", default=None)
@click.option("--module", "-m", multiple=True,
              help="Module(s) to load for this connection.")
@click.option("--secret", multiple=True, type=(str, str),
              metavar="KEY VALUE",
              help="Secret stored in .env.")
@click.option("--no-interactive", is_flag=True, default=False,
              help="Skip interactive prompts, use flags only.")
def add_connection(
    name, module_type, host, port, database,
    module, secret, no_interactive
) -> None:
    """
    Register a new database connection.

    If the module has a connection schema, you will be prompted
    for any missing fields interactively. Use --no-interactive
    to skip prompts and rely on flags only (useful for scripting).

    Examples:

        uqal add-connection db1 standard.postgresql

        uqal add-connection db1 standard.postgresql --host localhost --port 5432 --no-interactive

        uqal add-connection db1 standard.postgresql --secret password geheim --no-interactive
    """
    manager = ConfigManager()
    modules = list(module) or [module_type]

    provided_flags = {
        "host": host, "port": port, "database": database
    }
    provided_secrets = dict(secret)
    interactive = not no_interactive

    _apply_schema_to_connection(
        manager=manager,
        name=name,
        module_type=module_type,
        modules=modules,
        provided_flags=provided_flags,
        provided_secrets=provided_secrets,
        interactive=interactive,
    )

    click.echo(
        click.style(f"\nConnection '{name}' saved to ", fg="green")
        + str(manager.connection_config_path())
    )
    if provided_secrets or interactive:
        click.echo(
            click.style("Secrets saved to ", fg="green")
            + str(manager.env_path())
        )
        click.echo(
            click.style(
                "Remember: add .env to your .gitignore!",
                fg="yellow",
            )
        )


@click.command("update-connection")
@click.argument("name")
@click.option("--module-type", default=None)
@click.option("--host", default=None)
@click.option("--port", default=None, type=int)
@click.option("--database", "--db", default=None)
@click.option("--module", "-m", multiple=True)
@click.option("--add-module", multiple=True)
@click.option("--remove-module", multiple=True)
@click.option("--secret", multiple=True, type=(str, str), metavar="KEY VALUE")
@click.option("--no-interactive", is_flag=True, default=False)
def update_connection(
    name, module_type, host, port, database,
    module, add_module, remove_module, secret, no_interactive
) -> None:
    """
    Update an existing connection - only changed fields are modified.

    Examples:

        uqal update-connection db1 --host new-host

        uqal update-connection db1 --add-module community.postgis

        uqal update-connection db1 --secret password new_pass
    """
    manager = ConfigManager()
    connections = manager.list_connections()

    if name not in connections:
        click.echo(
            click.style(f"Error: connection '{name}' not found.", fg="red")
        )
        raise SystemExit(1)

    existing = connections[name]

    # Resolve module list
    final_modules = None
    if module:
        final_modules = list(module)
    elif add_module or remove_module:
        existing_modules = existing.get("modules", [])
        final_modules = [m for m in existing_modules if m not in remove_module]
        for m in add_module:
            if m not in final_modules:
                final_modules.append(m)

    manager.update_connection(
        connection_name=name,
        module_type=module_type,
        modules=final_modules,
        host=host,
        port=port,
        database=database,
    )

    for key, value in secret:
        manager.add_secret(name, key, value)

    click.echo(click.style(f"Connection '{name}' updated.", fg="green"))


@click.command("remove-connection")
@click.argument("name")
@click.option("--secrets", is_flag=True, default=False,
              help="Also remove secrets from .env.")
def remove_connection(name: str, secrets: bool) -> None:
    """Remove a registered connection."""
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
            click.style(f"Removed {count} secret(s) from .env.", fg="green")
        )


@click.command("list-connections")
def list_connections() -> None:
    """List all registered connections."""
    manager = ConfigManager()
    connections = manager.list_connections()

    if not connections:
        click.echo("No connections registered.")
        click.echo("Add one with: uqal add-connection <name> <module_type>")
        return

    click.echo(f"Registered connections ({len(connections)}):\n")
    for name, cfg in connections.items():
        click.echo(click.style(f"  {name}", fg="cyan", bold=True))
        click.echo(f"    type:     {cfg.get('module_type', '?')}")
        if cfg.get("host"):
            click.echo(f"    host:     {cfg['host']}")
        if cfg.get("port"):
            click.echo(f"    port:     {cfg['port']}")
        if cfg.get("database"):
            click.echo(f"    database: {cfg['database']}")
        if cfg.get("modules"):
            click.echo(f"    modules:  {', '.join(cfg['modules'])}")
        secrets = manager.get_secrets(name)
        if secrets:
            click.echo(
                f"    secrets:  "
                + click.style(f"{len(secrets)} configured (hidden)", fg="yellow")
            )
        click.echo()


@click.command("set-config-path")
@click.argument("path")
def set_config_path_cmd(path: str) -> None:
    """Override the default config directory."""
    set_config_path(path)
    click.echo(click.style("Config path set to: ", fg="green") + str(path))


@click.command("test-connection")
@click.argument("name")
def test_connection(name: str) -> None:
    """
    Test if a registered connection can be reached.

    Checks:
      1. Connection is registered in uqal_config.json
      2. Module is loaded and available
      3. build_connection() succeeds (login + reachability)

    Example:

        uqal test-connection db1
    """
    manager = ConfigManager()
    connections = manager.list_connections()

    if name not in connections:
        click.echo(
            click.style(f"Error: connection '{name}' not found.", fg="red")
        )
        raise SystemExit(1)

    cfg = connections[name]
    module_type = cfg.get("module_type", "")
    modules = cfg.get("modules", [])

    click.echo(f"Testing connection '{name}' ({module_type})...")

    # Step 1: load modules
    click.echo("  [1/3] Loading modules... ", nl=False)
    try:
        from uqal_core.module_loader import ModuleLoader
        from uqal_core.registry.module_registry import ModuleRegistry
        registry = ModuleRegistry()
        loader = ModuleLoader(registry=registry)
        loader.load(modules)
        click.echo(click.style("ok", fg="green"))
    except Exception as exc:
        click.echo(click.style(f"failed\n        {exc}", fg="red"))
        raise SystemExit(1)

    # Step 2: build connection config
    click.echo("  [2/3] Building connection config... ", nl=False)
    try:
        from uqal_core.registry.connection_registry import ConnectionConfig
        secrets = manager.get_secrets(name)
        config = ConnectionConfig(
            connection_name=name,
            module_type=module_type,
            module_names=modules,
            host=cfg.get("host"),
            port=cfg.get("port"),
            database=cfg.get("database"),
            options=secrets,
        )
        click.echo(click.style("ok", fg="green"))
    except Exception as exc:
        click.echo(click.style(f"failed\n        {exc}", fg="red"))
        raise SystemExit(1)

    # Step 3: try to build native connection
    click.echo("  [3/3] Connecting to database... ", nl=False)
    try:
        module = registry.get_module(
            modules[0] if modules else module_type
        )
        native_conn = module.build_connection(config)
        if native_conn is not None:
            click.echo(click.style("ok", fg="green"))
        else:
            click.echo(
                click.style(
                    "ok (no native connection returned)",
                    fg="yellow",
                )
            )
    except Exception as exc:
        click.echo(click.style(f"failed\n        {exc}", fg="red"))
        raise SystemExit(1)

    click.echo(
        click.style(f"\nConnection '{name}' is reachable.", fg="green")
    )