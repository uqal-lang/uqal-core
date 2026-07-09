"""
Core base types.

These are the types that EVERY module must support (see language
specification, chapter 9 "Type system").

Module-specific types (e.g. postgresql.varchar, postgis.geo) are NOT
defined here - they live inside the respective module and only
reference these base types in their own type_mapping.py.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


class CoreType(Enum):
    """
    The fixed base types of the language.

    The value (e.g. "integer") is exactly the keyword used in the
    script - e.g. in:

        db1.users.insert_table({
            "id": integer, primary_key: true,
            "name": string,
        })
    """

    INTEGER = "integer"
    FLOAT = "float"
    STRING = "string"
    BOOLEAN = "boolean"
    DATETIME = "datetime"
    LIST = "list"


@dataclass(frozen=True)
class TypeInfo:
    """
    Metadata for a core base type.

    python_type is used by the type checker to verify whether a
    concrete Python value (e.g. the result of a computation like
    a + b) matches the expected core type.
    """

    core_type: CoreType
    python_type: type
    description: str


CORE_TYPE_REGISTRY: dict[CoreType, TypeInfo] = {
    CoreType.INTEGER: TypeInfo(
        core_type=CoreType.INTEGER,
        python_type=int,
        description="Whole number",
    ),
    CoreType.FLOAT: TypeInfo(
        core_type=CoreType.FLOAT,
        python_type=float,
        description="Floating point number",
    ),
    CoreType.STRING: TypeInfo(
        core_type=CoreType.STRING,
        python_type=str,
        description="Text value",
    ),
    CoreType.BOOLEAN: TypeInfo(
        core_type=CoreType.BOOLEAN,
        python_type=bool,
        description="Boolean value",
    ),
    CoreType.DATETIME: TypeInfo(
        core_type=CoreType.DATETIME,
        python_type=str,
        description="Timestamp",
    ),
    CoreType.LIST: TypeInfo(
        core_type=CoreType.LIST,
        python_type=list,
        description="List of values",
    ),
}


def is_core_type_name(name: str) -> bool:
    """
    Checks whether a word used in a script (e.g. "integer") is a
    valid core base type.
    """
    return any(t.value == name for t in CoreType)


def get_core_type(name: str) -> CoreType:
    """
    Converts a string from the parsed script into the matching
    CoreType enum member.

    Raises ValueError if the name is not a valid base type - this is
    intentional: the caller (type checker) should handle this error
    explicitly instead of silently receiving None.
    """
    for t in CoreType:
        if t.value == name:
            return t
    raise ValueError(
        f"'{name}' is not a core base type. "
        f"Valid base types: {[t.value for t in CoreType]}. "
        f"If this is meant to be a module-specific type, it must be "
        f"prefixed with the module name (e.g. 'postgis.geo')."
    )


def python_value_matches(core_type: CoreType, value: Any) -> bool:
    """
    Checks whether a concrete Python value matches the given core type.

    Important for type checking computations between values from
    different databases (see specification chapter 5), e.g. to detect
    before execution that "Cedric" + 5 is invalid.
    """
    expected_python_type = CORE_TYPE_REGISTRY[core_type].python_type

    # bool is a subclass of int in Python - without this special case,
    # True would incorrectly pass as a valid INTEGER value.
    if core_type == CoreType.INTEGER and isinstance(value, bool):
        return False

    return isinstance(value, expected_python_type)