"""
PostgreSQL query complexity calculator.
"""

from __future__ import annotations

from typing import Any

from uqal_core.ast.nodes import (
    DbGenericCall,
    DbQueryBlock,
    DbTableCall,
    DbWriteCall,
    FieldParam,
    FieldsParam,
    LogicalAnd,
    LogicalOr,
    LogicalNot,
    Compare,
    WhereParam,
)


def calculate(ast_node: Any) -> float:
    """
    Calculates query complexity for cache scoring.
    Only called when cache mode is AUTO.
    """
    if isinstance(ast_node, DbTableCall):
        return _table_call_complexity(ast_node)
    if isinstance(ast_node, DbQueryBlock):
        return _query_block_complexity(ast_node)
    if isinstance(ast_node, DbWriteCall):
        return _write_complexity(ast_node)
    if isinstance(ast_node, DbGenericCall):
        return 2.0
    # Native SQL - unknown complexity
    return 5.0


def _table_call_complexity(node: DbTableCall) -> float:
    complexity = 0.0
    for param in node.params:
        if isinstance(param, FieldsParam):
            complexity += len(param.names) * 0.5
        elif isinstance(param, FieldParam):
            complexity += 0.5
        elif isinstance(param, WhereParam):
            complexity += _condition_complexity(param.condition)
    return max(complexity, 1.0)


def _query_block_complexity(node: DbQueryBlock) -> float:
    # Each JOIN is expensive
    join_cost = len(node.aliases) * 3.0
    field_cost = len(node.returns.fields) * 0.5
    where_cost = sum(
        _condition_complexity(a.condition)
        for a in node.aliases
        if a.condition
    )
    return max(join_cost + field_cost + where_cost, 3.0)


def _write_complexity(node: DbWriteCall) -> float:
    return {
        "insert_row":   2.0,
        "update":       2.5,
        "delete":       2.0,
        "insert_table": 1.0,
    }.get(node.command, 2.0)


def _condition_complexity(condition: Any) -> float:
    if isinstance(condition, (LogicalAnd, LogicalOr)):
        return (
            1.0
            + _condition_complexity(condition.left)
            + _condition_complexity(condition.right)
        )
    if isinstance(condition, LogicalNot):
        return 0.5 + _condition_complexity(condition.operand)
    if isinstance(condition, Compare):
        return 1.0
    return 0.5