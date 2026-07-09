"""
Module registry.

Tracks all loaded modules and the schema store each module maintains
per connection. The core queries this registry during type checking,
grammar building, and query planning.
"""

from __future__ import annotations

from uqal_core.module_interface import CapabilityManifest, UQALModule
from uqal_core.schema.schema_store import SchemaStore


class ModuleRegistry:
    """
    Central lookup table for everything module-related.

    Keeps three separate mappings:
      - module name -> module instance
      - connection name -> module instance (so the planner can find
        the right module for a given "db1.orders.get()" call)
      - connection name -> SchemaStore (cached metadata per connection)
    """

    def __init__(self) -> None:
        self._modules: dict[str, UQALModule] = {}
        self._connection_modules: dict[str, UQALModule] = {}
        self._schema_stores: dict[str, SchemaStore] = {}

    def register_module(self, module: UQALModule) -> None:
        """
        Registers a loaded module instance by its manifest name.
        Called by the module loader after dependency resolution and
        grammar extension registration.
        """
        name = module.get_manifest().name
        if name in self._modules:
            raise ValueError(
                f"Module '{name}' is already registered. "
                f"Each module name must be unique across the entire "
                f"module search path."
            )
        self._modules[name] = module

    def bind_module_to_connection(
        self, connection_name: str, module_name: str
    ) -> None:
        """
        Associates a connection (e.g. "db1") with a loaded module
        (e.g. "postgresql"). Called during the "connect" setup command
        after the module has already been registered.
        """
        if module_name not in self._modules:
            raise KeyError(
                f"Cannot bind connection '{connection_name}' to module "
                f"'{module_name}': module is not loaded. "
                f"Loaded modules: {sorted(self._modules.keys())}."
            )
        self._connection_modules[connection_name] = self._modules[module_name]

    def get_module_for_connection(self, connection_name: str) -> UQALModule:
        if connection_name not in self._connection_modules:
            raise KeyError(
                f"No module is bound to connection '{connection_name}'. "
                f"Known bindings: {sorted(self._connection_modules.keys())}."
            )
        return self._connection_modules[connection_name]
    
    def has_module_for_connection(self, connection_name: str) -> bool:
        return connection_name in self._connection_modules

    def get_module(self, module_name: str) -> UQALModule:
        if module_name not in self._modules:
            raise KeyError(
                f"Module '{module_name}' is not loaded. "
                f"Loaded modules: {sorted(self._modules.keys())}."
            )
        return self._modules[module_name]

    def store_schema(self, connection_name: str, schema: SchemaStore) -> None:
        self._schema_stores[connection_name] = schema

    def get_schema(self, connection_name: str) -> SchemaStore:
        if connection_name not in self._schema_stores:
            raise KeyError(
                f"No schema stored for connection '{connection_name}'. "
                f"Run 'db1.sync_schema' first to populate the schema "
                f"cache for this connection."
            )
        return self._schema_stores[connection_name]

    def has_schema(self, connection_name: str) -> bool:
        return connection_name in self._schema_stores

    def list_modules(self) -> list[str]:
        return sorted(self._modules.keys())

    def get_all_capabilities(self) -> dict[str, CapabilityManifest]:
        """
        Returns a combined view of what all loaded modules can do.
        Used by the grammar builder and the type checker.
        """
        return {
            name: module.get_capabilities()
            for name, module in self._modules.items()
        }

    def __repr__(self) -> str:
        return (
            f"ModuleRegistry("
            f"modules={self.list_modules()}, "
            f"connections={sorted(self._connection_modules.keys())})"
        )