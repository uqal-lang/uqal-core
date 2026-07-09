"""
PostgreSQL type mapping.

Maps UQAL core base types to PostgreSQL native types and declares
all postgresql.* module-specific types.
"""

from __future__ import annotations

from uqal_core.types import CoreType

# Core base types → PostgreSQL native types
CORE_TO_NATIVE: dict[str, str] = {
    CoreType.INTEGER.value:  "INTEGER",
    CoreType.FLOAT.value:    "DOUBLE PRECISION",
    CoreType.STRING.value:   "VARCHAR(255)",
    CoreType.BOOLEAN.value:  "BOOLEAN",
    CoreType.DATETIME.value: "TIMESTAMP",
    CoreType.LIST.value:     "JSONB",
}

# PostgreSQL-specific types exposed as postgresql.<name>
# Format: type_name → SQL type string (may include format string
# placeholders for parameterized types like varchar(n))
MODULE_TYPES: dict[str, str] = {
    "text":         "TEXT",
    "varchar":      "VARCHAR({0})",       # postgresql.varchar(200)
    "serial":       "SERIAL",
    "bigserial":    "BIGSERIAL",
    "uuid":         "UUID",
    "jsonb":        "JSONB",
    "json":         "JSON",
    "numeric":      "NUMERIC({0}, {1})",  # postgresql.numeric(10, 2)
    "timestamp_tz": "TIMESTAMP WITH TIME ZONE",
    "date":         "DATE",
    "time":         "TIME",
    "bytea":        "BYTEA",
    "inet":         "INET",
    "cidr":         "CIDR",
    "array":        "{0}[]",              # postgresql.array(integer)
}


def resolve_type(type_name: str, param=None) -> str:
    """
    Resolves a type name (core or module-specific) to a PostgreSQL
    SQL type string.

    Examples:
        resolve_type("integer")          → "INTEGER"
        resolve_type("varchar", 200)     → "VARCHAR(200)"
        resolve_type("numeric", (10, 2)) → "NUMERIC(10, 2)"
        resolve_type("array", "integer") → "INTEGER[]"
    """
    # Core base type
    if type_name in CORE_TO_NATIVE:
        return CORE_TO_NATIVE[type_name]

    # Module-specific type
    if type_name in MODULE_TYPES:
        template = MODULE_TYPES[type_name]
        if param is None:
            return template
        if isinstance(param, tuple):
            return template.format(*param)
        return template.format(param)

    return type_name.upper()