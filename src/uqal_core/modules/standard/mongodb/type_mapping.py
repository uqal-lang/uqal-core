"""
MongoDB type mapping.
"""

from __future__ import annotations

from uqal_core.types import CoreType

CORE_TO_BSON: dict[str, str] = {
    CoreType.INTEGER.value:  "int",
    CoreType.FLOAT.value:    "double",
    CoreType.STRING.value:   "string",
    CoreType.BOOLEAN.value:  "bool",
    CoreType.DATETIME.value: "date",
    CoreType.LIST.value:     "array",
}

BSON_TO_CORE: dict[str, str] = {
    "int":      CoreType.INTEGER.value,
    "long":     CoreType.INTEGER.value,
    "double":   CoreType.FLOAT.value,
    "decimal":  CoreType.FLOAT.value,
    "string":   CoreType.STRING.value,
    "bool":     CoreType.BOOLEAN.value,
    "date":     CoreType.DATETIME.value,
    "array":    CoreType.LIST.value,
    "object":   CoreType.LIST.value,
    "objectId": CoreType.STRING.value,
    "binData":  CoreType.STRING.value,
    "null":     CoreType.STRING.value,
}

PYTHON_TO_CORE: dict[str, str] = {
    "int":      CoreType.INTEGER.value,
    "float":    CoreType.FLOAT.value,
    "str":      CoreType.STRING.value,
    "bool":     CoreType.BOOLEAN.value,
    "datetime": CoreType.DATETIME.value,
    "list":     CoreType.LIST.value,
    "dict":     CoreType.LIST.value,
}

MODULE_TYPES: dict[str, str] = {
    "objectid":   "objectId",
    "timestamp":  "timestamp",
    "binary":     "binData",
    "decimal128": "decimal",
    "object":     "object",
}


def python_type_to_core(value: object) -> str:
    type_name = type(value).__name__
    return PYTHON_TO_CORE.get(type_name, CoreType.STRING.value)


def bson_type_to_core(bson_type: str) -> str:
    return BSON_TO_CORE.get(bson_type, CoreType.STRING.value)