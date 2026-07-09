"""
Unified schema format.

EVERY module must store its tables/collections/node structures in
exactly this format (see language specification, chapter 14.6).

The core itself never knows the native format of a specific database -
it only ever sees this structure. The module is responsible for
translating from its native format (e.g. Postgres information_schema,
Mongo collection sampling, Neo4j node labels) into this format.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from uqal_core.types import CoreType


@dataclass
class FieldDefinition:
    """
    A single field/column of a table.

    type is either:
      - the raw value of a CoreType (e.g. "integer"), or
      - a module-specific type with namespace prefix (e.g. "postgis.geo")

    The core itself does not interpret type semantically - that is
    done by the type checker based on the currently loaded modules.
    """

    name: str
    type: str
    primary_key: bool = False
    required: bool = False
    default_value: Any = None
    flexible: bool = False


@dataclass
class RelationshipDefinition:
    """
    A relationship between two tables/structures within the SAME
    connection.

    Maps both classic foreign key relationships (relational DBs) and
    graph edges (Neo4j) onto the same format, so the core never needs
    to distinguish between the two.
    """

    name: str
    target_table: str
    # For relational DBs e.g. "user_id -> id"
    # For graph DBs e.g. the relationship type ("FOLLOWS", "PLACED_BY")
    native_description: str


@dataclass
class TableDefinition:
    """
    A table, collection, or node label - depending on the module.

    native_metadata is intentionally a free dict: modules may store
    additional, module-specific information there (e.g. the exact
    tablespace for PostgreSQL, indexes for Neo4j) without the core
    needing to know or understand that structure. The core never
    reads from it - it is pure passthrough for the module itself.
    """

    name: str
    fields: list[FieldDefinition] = field(default_factory=list)
    relationships: list[RelationshipDefinition] = field(default_factory=list)
    native_metadata: dict = field(default_factory=dict)

    def get_field(self, field_name: str) -> FieldDefinition | None:
        for f in self.fields:
            if f.name == field_name:
                return f
        return None

    def has_field(self, field_name: str) -> bool:
        return self.get_field(field_name) is not None


@dataclass
class SchemaStore:
    """
    Holds the complete known schema of ONE connection.

    Populated by:
      - UQALModule.sync_schema_from_source() -> reads the real, live
        database (setup command "db1.sync_schema")
      - manual insert_table calls within the script itself

    Read by:
      - "db1.list_tables" / "db1.list_tables(live=true)"
      - "db1.<table>.schema"
      - the type checker, to validate field references in the script
    """

    tables: dict[str, TableDefinition] = field(default_factory=dict)

    def get_table(self, name: str) -> TableDefinition:
        if name not in self.tables:
            raise KeyError(
                f"Table '{name}' is not known in this connection's "
                f"schema. Known tables: {sorted(self.tables.keys())}. "
                f"If the table was created recently, 'sync_schema' "
                f"might help refresh the stored metadata."
            )
        return self.tables[name]

    def list_tables(self) -> list[str]:
        return sorted(self.tables.keys())

    def add_table(self, table_def: TableDefinition) -> None:
        self.tables[table_def.name] = table_def

    def has_table(self, name: str) -> bool:
        return name in self.tables


def core_type_field(name: str, core_type: CoreType, **kwargs) -> FieldDefinition:
    """
    Small convenience helper for modules: creates a FieldDefinition
    directly from a CoreType instead of a raw string, to avoid typos
    when writing a module.

    Example:
        core_type_field("id", CoreType.INTEGER, primary_key=True)
    """
    return FieldDefinition(name=name, type=core_type.value, **kwargs)