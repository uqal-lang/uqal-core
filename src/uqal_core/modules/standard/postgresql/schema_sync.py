"""
PostgreSQL schema discovery via information_schema.

Reads table structures, column definitions, primary keys, and
foreign key relationships from the PostgreSQL system catalog.
"""

from __future__ import annotations

from uqal_core.schema.schema_store import (
    FieldDefinition,
    RelationshipDefinition,
    SchemaStore,
    TableDefinition,
)
from uqal_core.modules.standard.postgresql.type_mapping import (
    CORE_TO_NATIVE,
)

# Maps PostgreSQL native types to UQAL core type names
_PG_TO_CORE: dict[str, str] = {
    "integer":            "integer",
    "bigint":             "integer",
    "smallint":           "integer",
    "serial":             "integer",
    "bigserial":          "integer",
    "double precision":   "float",
    "real":               "float",
    "numeric":            "float",
    "decimal":            "float",
    "character varying":  "string",
    "varchar":            "string",
    "text":               "string",
    "char":               "string",
    "boolean":            "boolean",
    "timestamp":          "datetime",
    "timestamp without time zone": "datetime",
    "timestamp with time zone":    "datetime",
    "date":               "datetime",
    "jsonb":              "list",
    "json":               "list",
    "array":              "list",
    "uuid":               "string",
    "bytea":              "string",
    "inet":               "string",
    "cidr":               "string",
}


def _map_pg_type(pg_type: str) -> str:
    """Maps a PostgreSQL data type to a UQAL core type name."""
    return _PG_TO_CORE.get(pg_type.lower(), "string")


def discover_tables(connection) -> list[tuple[str, str]]:
    """Returns all user tables and views in the public schema."""
    cursor = connection.cursor()
    cursor.execute("""
        SELECT table_name, table_type
        FROM information_schema.tables
        WHERE table_schema = 'public'
        AND table_type IN ('BASE TABLE', 'VIEW')
        ORDER BY table_name
    """)
    tables = [(row[0], row[1]) for row in cursor.fetchall()]
    cursor.close()
    return tables


def discover_columns(
    connection, table_name: str
) -> list[FieldDefinition]:
    """Returns all columns of a table as FieldDefinition objects."""
    cursor = connection.cursor()

    # Get columns
    cursor.execute("""
        SELECT
            column_name,
            data_type,
            is_nullable,
            column_default,
            character_maximum_length
        FROM information_schema.columns
        WHERE table_schema = 'public'
        AND table_name = %s
        ORDER BY ordinal_position
    """, (table_name,))
    columns = cursor.fetchall()

    # Get primary keys
    cursor.execute("""
        SELECT kcu.column_name
        FROM information_schema.table_constraints tc
        JOIN information_schema.key_column_usage kcu
          ON tc.constraint_name = kcu.constraint_name
          AND tc.table_schema = kcu.table_schema
        WHERE tc.constraint_type = 'PRIMARY KEY'
        AND tc.table_schema = 'public'
        AND tc.table_name = %s
    """, (table_name,))
    primary_keys = {row[0] for row in cursor.fetchall()}
    cursor.close()

    fields = []
    for col_name, data_type, is_nullable, default, max_length in columns:
        core_type = _map_pg_type(data_type)

        # Use more specific type for varchar with known length
        if data_type == "character varying" and max_length:
            native_type = f"postgresql.varchar"
        else:
            native_type = core_type

        fields.append(FieldDefinition(
            name=col_name,
            type=core_type,
            primary_key=col_name in primary_keys,
            required=is_nullable == "NO" and default is None,
            default_value=default,
        ))

    return fields


def discover_relationships(
    connection, table_name: str
) -> list[RelationshipDefinition]:
    """Returns all foreign key relationships of a table."""
    cursor = connection.cursor()
    cursor.execute("""
        SELECT
            kcu.column_name,
            ccu.table_name AS target_table,
            ccu.column_name AS target_column
        FROM information_schema.table_constraints tc
        JOIN information_schema.key_column_usage kcu
          ON tc.constraint_name = kcu.constraint_name
          AND tc.table_schema = kcu.table_schema
        JOIN information_schema.constraint_column_usage ccu
          ON tc.constraint_name = ccu.constraint_name
        WHERE tc.constraint_type = 'FOREIGN KEY'
        AND tc.table_schema = 'public'
        AND tc.table_name = %s
    """, (table_name,))
    rows = cursor.fetchall()
    cursor.close()

    return [
        RelationshipDefinition(
            name=f"fk_{col}",
            target_table=target_table,
            native_description=f"{col} -> {target_table}.{target_col}",
        )
        for col, target_table, target_col in rows
    ]


def sync_full_schema(connection) -> SchemaStore:
    store = SchemaStore()
    tables = discover_tables(connection)

    for table_name, table_type in tables:
        fields = discover_columns(connection, table_name)
        relationships = (
            discover_relationships(connection, table_name)
            if table_type == "BASE TABLE"
            else []  # Views haben keine FK-Constraints
        )

        store.add_table(TableDefinition(
            name=table_name,
            fields=fields,
            relationships=relationships,
            native_metadata={
                "schema":     "public",
                "table_type": table_type,        # "BASE TABLE" oder "VIEW"
                "is_view":    table_type == "VIEW",
            },
        ))

    return store