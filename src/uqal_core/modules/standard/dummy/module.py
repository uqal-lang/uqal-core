"""
Dummy module for development and testing.

Implements the full UQALModule interface with no real database
backend. Used to verify that the ModuleLoader, validation pipeline,
and CLI commands work end-to-end without requiring a live database
connection.

Not intended for production use.
"""

from __future__ import annotations

from typing import Any

from uqal_core.execution.result_set import ResultSet
from uqal_core.module_interface import (
    CapabilityManifest,
    ModuleManifest,
    UQALModule,
)
from uqal_core.schema.schema_store import SchemaStore, TableDefinition, core_type_field
from uqal_core.modules.standard.dummy.connection_schema import DummyConnectionSchema
from uqal_core.types import CoreType


class DummyModule(UQALModule):
    """
    Minimal but fully valid UQALModule implementation.

    Every method either returns a sensible empty/default value or a
    small hardcoded example, so the module passes all validation
    checks without touching any real infrastructure.
    """

    def __init__(self) -> None:
        self._schema_store = self._build_initial_schema()

    # ---- 1. Identity / grammar ----

    def get_manifest(self) -> ModuleManifest:
        return ModuleManifest(
            name="standard.dummy",
            version="0.1.0",
            requires=[],
        )

    def get_grammar_extension(self) -> str:
        # No grammar extensions - dummy stays within base language only.
        return ""

    def get_capabilities(self) -> CapabilityManifest:
        return CapabilityManifest(
            module_name="standard.dummy",
            table_commands={},
            expression_extensions={},
            provided_types=[],
        )

    def get_type_mapping(self) -> dict[str, Any]:
        # Maps every core base type to a simple string label.
        # A real module would map to native DB types (e.g. "INTEGER",
        # "VARCHAR(255)"). The dummy uses human-readable labels so the
        # mapping is easy to verify in tests.
        return {
            CoreType.INTEGER.value: "DUMMY_INT",
            CoreType.FLOAT.value: "DUMMY_FLOAT",
            CoreType.STRING.value: "DUMMY_STRING",
            CoreType.BOOLEAN.value: "DUMMY_BOOL",
            CoreType.DATETIME.value: "DUMMY_DATETIME",
            CoreType.LIST.value: "DUMMY_LIST",
        }

    # ---- 2. Connection ----

    def build_connection(self, config: Any) -> Any:
        # No real connection needed - return a sentinel so the
        # registry has something non-None to store.
        return {"dummy_connection": True}
    
    def get_connection_schema(self) -> type[ConnectionSchema]:
        return DummyConnectionSchema

    # ---- 3. Data / schema ----

    def translate(self, ast_subtree: Any) -> Any:
        # Returns the subtree unchanged - the dummy has no real query
        # language to translate into.
        return {"dummy_query": repr(ast_subtree)}

    def execute(self, native_query: Any, connection: Any) -> ResultSet:
        # Always returns one hardcoded row so iteration tests work.
        return ResultSet(
            rows=[{"id": 1, "value": "dummy_result"}],
            source_module="standard.dummy",
        )

    def get_schema_store(self) -> SchemaStore:
        return self._schema_store

    def sync_schema_from_source(self, connection: Any) -> SchemaStore:
        # No real source to sync from - rebuild the initial schema
        # and return it as if it had just been read from a database.
        self._schema_store = self._build_initial_schema()
        return self._schema_store

    def create_view(
        self,
        view_name: str,
        aliases: list,  # noqa: ARG002
        returns: Any,   # noqa: ARG002
        connection: Any,  # noqa: ARG002
    ) -> str:
        # Dummy has no real database - just acknowledge the view name.
        return view_name

    # ---- Internal helpers ----

    def _build_initial_schema(self) -> SchemaStore:
        """
        Builds a small hardcoded schema with one example table so
        schema-related tests have something to work with.
        """
        store = SchemaStore()
        store.add_table(
            TableDefinition(
                name="dummy_table",
                fields=[
                    core_type_field("id", CoreType.INTEGER, primary_key=True),
                    core_type_field("value", CoreType.STRING, required=True),
                ],
            )
        )
        return store