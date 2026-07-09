"""
Registry for extension module condition SQL builders.

Extension modules register a callable here for each AST node type
they add. The PostgreSQL translator (and any other SQL-generating
module) checks this registry in _build_condition when it encounters
an unknown node type.

Usage in an extension module's __init__.py:
    from uqal_core.ast.condition_registry import register_condition_builder
    from .nodes import STWithinNode

    register_condition_builder(
        STWithinNode,
        lambda node: (f"ST_Within({node.column}, %s)", (node.polygon,))
    )
"""

from __future__ import annotations

from typing import Any, Callable

_CONDITION_REGISTRY: dict[type, Callable] = {}


def register_condition_builder(
    node_type: type,
    builder: Callable[[Any], tuple[str, tuple]],
) -> None:
    """
    Registers a SQL builder for an extension condition node type.

    The builder receives the node and returns (sql_fragment, params_tuple).
    params_tuple must use %s placeholders (psycopg2 format).
    """
    _CONDITION_REGISTRY[node_type] = builder


def get_condition_builder(
    node_type: type,
) -> Callable[[Any], tuple[str, tuple]] | None:
    return _CONDITION_REGISTRY.get(node_type)
