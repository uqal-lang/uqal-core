"""
Neo4j type mapping.

Neo4j uses property types internally but returns Python native types
via the driver. We map those to UQAL core types.
"""

from __future__ import annotations

from uqal_core.types import CoreType

# Neo4j property type → UQAL core type
NEO4J_TO_CORE: dict[str, str] = {
    "Long":          CoreType.INTEGER.value,
    "Integer":       CoreType.INTEGER.value,
    "Double":        CoreType.FLOAT.value,
    "Float":         CoreType.FLOAT.value,
    "String":        CoreType.STRING.value,
    "Boolean":       CoreType.BOOLEAN.value,
    "Date":          CoreType.DATETIME.value,
    "DateTime":      CoreType.DATETIME.value,
    "LocalDateTime": CoreType.DATETIME.value,
    "LocalTime":     CoreType.DATETIME.value,
    "Duration":      CoreType.STRING.value,
    "Point":         CoreType.STRING.value,
    "List":          CoreType.LIST.value,
}

# UQAL core type → Neo4j property type
CORE_TO_NEO4J: dict[str, str] = {
    CoreType.INTEGER.value:  "Long",
    CoreType.FLOAT.value:    "Double",
    CoreType.STRING.value:   "String",
    CoreType.BOOLEAN.value:  "Boolean",
    CoreType.DATETIME.value: "DateTime",
    CoreType.LIST.value:     "List",
}

# Python type → UQAL core type (for property sampling)
PYTHON_TO_CORE: dict[str, str] = {
    "int":   CoreType.INTEGER.value,
    "float": CoreType.FLOAT.value,
    "str":   CoreType.STRING.value,
    "bool":  CoreType.BOOLEAN.value,
    "list":  CoreType.LIST.value,
    "dict":  CoreType.LIST.value,
}

# Module-specific types
MODULE_TYPES: dict[str, str] = {
    "node":         "node",
    "relationship": "relationship",
    "path":         "path",
    "point":        "point",
}


def python_type_to_core(value: object) -> str:
    """Infers UQAL core type from a Python value."""
    type_name = type(value).__name__
    # Handle Neo4j driver types
    if hasattr(value, "__class__"):
        class_name = value.__class__.__name__
        if "Date" in class_name or "Time" in class_name:
            return CoreType.DATETIME.value
        if "Integer" in class_name or "Long" in class_name:
            return CoreType.INTEGER.value
        if "Float" in class_name or "Double" in class_name:
            return CoreType.FLOAT.value
    return PYTHON_TO_CORE.get(type_name, CoreType.STRING.value)