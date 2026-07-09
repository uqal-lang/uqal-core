"""
Connection registry.

Stores all database connections configured via the "connect" setup
command (see language specification, chapter 11.2). The core queries
this registry whenever it needs to know which module handles a given
connection name (e.g. "db1").

Connection parameters are split into two levels:
  - Standard fields (host, port, database) that the core itself can
    read and use for error messages / introspection.
  - A free "options" dict for everything module-specific (auth tokens,
    SSL certificates, driver flags, etc.) that only the module reads.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ConnectionConfig:
    """
    Everything the core needs to know about one configured connection.

    module_names lists the modules active for this specific connection
    instance - important because two connections of the same type may
    have different modules loaded (e.g. one PostgreSQL instance with
    PostGIS, another without, see specification chapter 11.2).

    options is intentionally untyped: the core never interprets it.
    Only the module that owns this connection reads from options, via
    its own build_connection() implementation.
    """

    connection_name: str
    module_type: str
    module_names: list[str] = field(default_factory=list)

    # Standard fields the core itself understands
    host: str | None = None
    port: int | None = None
    database: str | None = None

    # Everything module-specific goes here:
    # auth tokens, SSL certs, driver flags, managed identity, etc.
    options: dict = field(default_factory=dict)

    # Populated by the module after build_connection() succeeds.
    # The core passes this back to the module in execute() calls
    # but never inspects its contents.
    native_connection: object | None = None


class ConnectionRegistry:
    """
    Holds all configured connections for the current session.
    """

    def __init__(self) -> None:
        self._connections: dict[str, ConnectionConfig] = {}

    def register(self, config: ConnectionConfig) -> None:
        if config.connection_name in self._connections:
            raise ValueError(
                f"Connection '{config.connection_name}' is already "
                f"registered. Use a different name or remove the "
                f"existing registration first."
            )
        self._connections[config.connection_name] = config

    def get(self, connection_name: str) -> ConnectionConfig:
        if connection_name not in self._connections:
            raise KeyError(
                f"Connection '{connection_name}' is not registered. "
                f"Known connections: {sorted(self._connections.keys())}. "
                f"Use the 'connect' setup command to register it first."
            )
        return self._connections[connection_name]

    def update_native_connection(
        self, connection_name: str, native_connection: object
    ) -> None:
        """
        Stores the native connection object returned by the module's
        build_connection() call back into the config, so the registry
        is the single source of truth for all connection state.
        """
        config = self.get(connection_name)
        config.native_connection = native_connection

    def has(self, connection_name: str) -> bool:
        return connection_name in self._connections

    def list_connections(self) -> list[str]:
        return sorted(self._connections.keys())

    def __repr__(self) -> str:
        return f"ConnectionRegistry(connections={self.list_connections()})"