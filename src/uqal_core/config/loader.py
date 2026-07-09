"""
Config loader.

Reads uqal_config.json and .env and loads all configured connections
and modules into a running Engine instance.

Schema loading strategy:
  1. No cache exists → trigger sync_schema automatically on first use
  2. Cache exists but TTL expired (default 24h) → trigger auto sync
  3. Cache fresh → load from disk, no DB contact needed
"""

from __future__ import annotations

from uqal_core.config.config_manager import ConfigManager
from uqal_core.cache.cache_manager import CacheManager


def load_connections_into_engine(
    engine: "Engine",
    auto_sync: bool = True,
) -> list[str]:
    """
    Reads all connections from uqal_config.json and registers them
    in the engine.

    auto_sync=True: automatically runs sync_schema if cache is
    missing or expired. Set to False to skip DB contact entirely
    (useful in tests or offline mode).
    """
    from uqal_core.engine import Engine
    assert isinstance(engine, Engine)

    config_manager = ConfigManager()
    cache_manager = CacheManager()
    connections = config_manager.list_connections()
    loaded = []

    for name, cfg in connections.items():
        module_type = cfg.get("module_type", "")
        modules = cfg.get("modules", [])
        host = cfg.get("host")
        port = cfg.get("port")
        database = cfg.get("database")
        ttl_hours = cfg.get("cache_ttl_hours", 24)

        # Step 1: load modules
        if modules:
            try:
                engine.load_modules(modules)
            except Exception as exc:
                # Module already loaded is not an error
                if "already registered" not in str(exc):
                    print(
                        f"Warning: could not load modules {modules} "
                        f"for connection '{name}': {exc}"
                    )

        # Step 2: collect secrets and register connection
        secrets = config_manager.get_secrets(name)
        try:
            engine.connect(
                connection_name=name,
                module_type=module_type,
                host=host,
                port=port,
                database=database,
                **secrets,
            )
        except Exception as exc:
            print(
                f"Warning: could not register connection '{name}': {exc}"
            )
            continue

        # Step 3: bind primary module to connection
        primary_module_name = modules[0] if modules else module_type
        try:
            engine._module_registry.bind_module_to_connection(
                name, primary_module_name
            )
        except Exception as exc:
            print(
                f"Warning: could not bind module "
                f"'{primary_module_name}' to '{name}': {exc}"
            )
            continue

        # Step 4: load schema (cache or auto-sync)
        cache_expired = cache_manager.is_expired(name)
        cached = cache_manager.load(name)

        if cached and not cache_expired:
            # Cache is fresh - load from disk, no DB contact
            engine._module_registry.store_schema(name, cached)

        elif auto_sync:
            # Cache missing or expired - sync from DB
            reason = "no cache" if cached is None else "cache expired"
            print(
                f"Info: syncing schema for '{name}' ({reason})..."
            )
            try:
                _sync_schema(
                    engine, name, primary_module_name,
                    cache_manager, module_type, ttl_hours
                )
            except Exception as exc:
                print(
                    f"Warning: auto sync failed for '{name}': {exc}. "
                    f"Run 'uqal run \"testdb.sync_schema\"' manually."
                )
                # If we have stale cache, use it rather than nothing
                if cached:
                    engine._module_registry.store_schema(name, cached)

        else:
            # Offline mode - use stale cache if available
            if cached:
                engine._module_registry.store_schema(name, cached)

        loaded.append(name)

    return loaded


def _sync_schema(
    engine: "Engine",
    connection_name: str,
    module_name: str,
    cache_manager: CacheManager,
    module_type: str,
    ttl_hours: int,
) -> None:
    """
    Performs a live schema sync for one connection and saves to disk.
    """
    from uqal_core.execution.executor import ExecutionContext
    config = engine._connection_registry.get(connection_name)
    module = engine._module_registry.get_module(module_name)

    # Build native connection if not already done
    if config.native_connection is None:
        native_conn = module.build_connection(config)
        engine._connection_registry.update_native_connection(
            connection_name, native_conn
        )
        config = engine._connection_registry.get(connection_name)

    # Sync schema from live DB
    schema = module.sync_schema_from_source(config.native_connection)

    # Store in memory
    engine._module_registry.store_schema(connection_name, schema)

    # Persist to disk
    cache_manager.save(
        connection_name=connection_name,
        schema=schema,
        module_type=module_type,
        ttl_hours=ttl_hours,
    )