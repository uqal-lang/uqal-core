# src/uqal_core/ast/module_nodes.py
"""
Registry for module-specific AST node handlers.

Modules register their grammar rule handlers here so the core
transformer can dispatch to them without knowing their names.

Usage in a module's __init__.py or module.py:
    from uqal_core.ast.module_nodes import register_node_handler
    register_node_handler("neo4j_rel_traversal", _handle_rel)
"""

from __future__ import annotations
from typing import Callable, Any

_MODULE_NODE_REGISTRY: dict[str, Callable] = {}


def register_node_handler(
    rule_name: str,
    handler: Callable[[list], Any],
) -> None:
    """
    Registers a handler for a module-specific grammar rule.

    The handler receives the children list and returns an AST node.
    Called automatically when the module is loaded.
    """
    _MODULE_NODE_REGISTRY[rule_name] = handler


def get_node_handler(rule_name: str) -> Callable | None:
    return _MODULE_NODE_REGISTRY.get(rule_name)