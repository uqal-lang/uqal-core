"""Tests for Neo4jTranslator: _build_condition, _expr_to_cypher, _map_operator."""
import pytest
from uqal_core.ast.nodes import (
    BoolLiteral,
    Compare,
    FloatLiteral,
    IntegerLiteral,
    IsNotNull,
    IsNull,
    LogicalAnd,
    LogicalNot,
    LogicalOr,
    NullLiteral,
    StringLiteral,
    VariableRef,
)
from uqal_core.modules.standard.neo4j.translator import Neo4jTranslator

pytestmark = pytest.mark.unit


@pytest.fixture
def translator():
    return Neo4jTranslator()


# ---- _build_condition: Compare ----

def test_build_condition_compare_bool_true(translator):
    condition = Compare(
        left=VariableRef(parts=["active"]),
        operator="=",
        right=BoolLiteral(value=True),
    )
    cypher, params = translator._build_condition(condition, "n", {})
    assert "n.active" in cypher
    assert "true" in cypher
    assert "=" in cypher


def test_build_condition_compare_bool_false(translator):
    condition = Compare(
        left=VariableRef(parts=["active"]),
        operator="=",
        right=BoolLiteral(value=False),
    )
    cypher, _ = translator._build_condition(condition, "n", {})
    assert "false" in cypher


def test_build_condition_compare_not_equal_maps_operator(translator):
    condition = Compare(
        left=VariableRef(parts=["status"]),
        operator="!=",
        right=StringLiteral(value="closed"),
    )
    cypher, _ = translator._build_condition(condition, "n", {})
    assert "<>" in cypher
    assert "!=" not in cypher


def test_build_condition_compare_integer_parameterized(translator):
    condition = Compare(
        left=VariableRef(parts=["age"]),
        operator=">=",
        right=IntegerLiteral(value=18),
    )
    cypher, params = translator._build_condition(condition, "n", {})
    assert ">=" in cypher
    assert "n.age" in cypher
    assert 18 in params.values()


def test_build_condition_compare_uses_dollar_param(translator):
    condition = Compare(
        left=VariableRef(parts=["id"]),
        operator="=",
        right=IntegerLiteral(value=42),
    )
    cypher, params = translator._build_condition(condition, "n", {})
    assert any(cypher.endswith(f"${k}") or f"${k}" in cypher for k in params)


def test_build_condition_compare_string_parameterized(translator):
    condition = Compare(
        left=VariableRef(parts=["name"]),
        operator="=",
        right=StringLiteral(value="Alice"),
    )
    _, params = translator._build_condition(condition, "n", {})
    assert "Alice" in params.values()


# ---- _build_condition: LogicalAnd ----

def test_build_condition_and_combines_with_keyword(translator):
    left = Compare(
        left=VariableRef(parts=["a"]),
        operator="=",
        right=IntegerLiteral(value=1),
    )
    right = Compare(
        left=VariableRef(parts=["b"]),
        operator="=",
        right=IntegerLiteral(value=2),
    )
    cypher, params = translator._build_condition(
        LogicalAnd(left=left, right=right), "n", {}
    )
    assert "AND" in cypher
    assert "(" in cypher
    assert len(params) >= 1


def test_build_condition_and_wraps_in_parens(translator):
    left = Compare(
        left=VariableRef(parts=["x"]), operator="=", right=BoolLiteral(value=True)
    )
    right = Compare(
        left=VariableRef(parts=["y"]), operator="=", right=BoolLiteral(value=False)
    )
    cypher, _ = translator._build_condition(
        LogicalAnd(left=left, right=right), "n", {}
    )
    assert cypher.startswith("(")
    assert cypher.endswith(")")


# ---- _build_condition: LogicalOr ----

def test_build_condition_or_combines_with_keyword(translator):
    left = Compare(
        left=VariableRef(parts=["x"]), operator="=", right=IntegerLiteral(value=1)
    )
    right = Compare(
        left=VariableRef(parts=["y"]), operator="=", right=IntegerLiteral(value=2)
    )
    cypher, _ = translator._build_condition(
        LogicalOr(left=left, right=right), "n", {}
    )
    assert "OR" in cypher


def test_build_condition_or_wraps_in_parens(translator):
    left = Compare(
        left=VariableRef(parts=["a"]), operator="=", right=BoolLiteral(value=True)
    )
    right = Compare(
        left=VariableRef(parts=["b"]), operator="=", right=BoolLiteral(value=True)
    )
    cypher, _ = translator._build_condition(
        LogicalOr(left=left, right=right), "n", {}
    )
    assert cypher.startswith("(")
    assert cypher.endswith(")")


# ---- _build_condition: IsNull / IsNotNull ----

def test_build_condition_is_null(translator):
    condition = IsNull(operand=VariableRef(parts=["age"]))
    cypher, _ = translator._build_condition(condition, "n", {})
    assert "IS NULL" in cypher
    assert "n.age" in cypher


def test_build_condition_is_not_null(translator):
    condition = IsNotNull(operand=VariableRef(parts=["name"]))
    cypher, _ = translator._build_condition(condition, "n", {})
    assert "IS NOT NULL" in cypher
    assert "n.name" in cypher


def test_build_condition_is_null_returns_empty_params(translator):
    condition = IsNull(operand=VariableRef(parts=["deleted_at"]))
    _, params = translator._build_condition(condition, "n", {})
    assert params == {}


# ---- _build_condition: LogicalNot ----

def test_build_condition_not(translator):
    inner = Compare(
        left=VariableRef(parts=["active"]),
        operator="=",
        right=BoolLiteral(value=True),
    )
    cypher, _ = translator._build_condition(LogicalNot(operand=inner), "n", {})
    assert "NOT" in cypher


# ---- _expr_to_cypher: literals ----

def test_expr_integer_literal_uses_param(translator):
    params = {}
    result = translator._expr_to_cypher(IntegerLiteral(value=42), "n", params)
    assert result.startswith("$")
    assert 42 in params.values()


def test_expr_float_literal_uses_param(translator):
    params = {}
    result = translator._expr_to_cypher(FloatLiteral(value=3.14), "n", params)
    assert result.startswith("$")
    assert 3.14 in params.values()


def test_expr_string_literal_uses_param(translator):
    params = {}
    result = translator._expr_to_cypher(StringLiteral(value="hello"), "n", params)
    assert result.startswith("$")
    assert "hello" in params.values()


def test_expr_bool_true_inline(translator):
    result = translator._expr_to_cypher(BoolLiteral(value=True), "n", {})
    assert result == "true"


def test_expr_bool_false_inline(translator):
    result = translator._expr_to_cypher(BoolLiteral(value=False), "n", {})
    assert result == "false"


def test_expr_null_literal_inline(translator):
    result = translator._expr_to_cypher(NullLiteral(), "n", {})
    assert result == "null"


# ---- _expr_to_cypher: VariableRef ----

def test_expr_variable_ref_single_part(translator):
    result = translator._expr_to_cypher(VariableRef(parts=["field"]), "myalias", {})
    assert result == "myalias.field"


def test_expr_variable_ref_two_parts(translator):
    result = translator._expr_to_cypher(VariableRef(parts=["alias", "prop"]), "n", {})
    assert result == "alias.prop"


def test_expr_variable_ref_uses_alias(translator):
    result = translator._expr_to_cypher(VariableRef(parts=["status"]), "order", {})
    assert result == "order.status"


def test_expr_integer_increments_param_key(translator):
    params = {"p0": 10}
    result = translator._expr_to_cypher(IntegerLiteral(value=20), "n", params)
    assert result == "$p1"
    assert params["p1"] == 20


# ---- _map_operator ----

def test_map_operator_eq(translator):
    assert translator._map_operator("=") == "="


def test_map_operator_double_eq(translator):
    assert translator._map_operator("==") == "="


def test_map_operator_not_eq(translator):
    assert translator._map_operator("!=") == "<>"


def test_map_operator_gt(translator):
    assert translator._map_operator(">") == ">"


def test_map_operator_lt(translator):
    assert translator._map_operator("<") == "<"


def test_map_operator_gte(translator):
    assert translator._map_operator(">=") == ">="


def test_map_operator_lte(translator):
    assert translator._map_operator("<=") == "<="


def test_map_operator_unknown_passthrough(translator):
    assert translator._map_operator("CONTAINS") == "CONTAINS"
