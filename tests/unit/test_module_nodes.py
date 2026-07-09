"""Tests for module_nodes registry: register_node_handler, get_node_handler."""
import pytest
from uqal_core.ast.module_nodes import get_node_handler, register_node_handler

pytestmark = pytest.mark.unit

_UNIQUE_PREFIX = "test_module_nodes_"


def test_register_handler_can_be_retrieved():
    def handler(children):
        return "result"

    rule = f"{_UNIQUE_PREFIX}basic"
    register_node_handler(rule, handler)
    assert get_node_handler(rule) is handler


def test_registered_handler_is_callable():
    def handler(children):
        return children

    rule = f"{_UNIQUE_PREFIX}callable"
    register_node_handler(rule, handler)
    retrieved = get_node_handler(rule)
    assert callable(retrieved)


def test_handler_executes_correctly():
    def handler(children):
        return ["handled"] + children

    rule = f"{_UNIQUE_PREFIX}exec"
    register_node_handler(rule, handler)
    retrieved = get_node_handler(rule)
    assert retrieved(["a", "b"]) == ["handled", "a", "b"]


def test_get_node_handler_returns_none_for_unknown():
    result = get_node_handler(f"{_UNIQUE_PREFIX}does_not_exist_xyz")
    assert result is None


def test_get_node_handler_returns_none_for_empty_string():
    result = get_node_handler("")
    assert result is None


def test_register_overwrites_existing_handler():
    rule = f"{_UNIQUE_PREFIX}overwrite"

    def first_handler(children):
        return "first"

    def second_handler(children):
        return "second"

    register_node_handler(rule, first_handler)
    register_node_handler(rule, second_handler)
    retrieved = get_node_handler(rule)
    assert retrieved is second_handler


def test_different_rules_have_independent_handlers():
    rule_a = f"{_UNIQUE_PREFIX}rule_a"
    rule_b = f"{_UNIQUE_PREFIX}rule_b"

    def handler_a(children):
        return "a"

    def handler_b(children):
        return "b"

    register_node_handler(rule_a, handler_a)
    register_node_handler(rule_b, handler_b)

    assert get_node_handler(rule_a) is handler_a
    assert get_node_handler(rule_b) is handler_b


def test_lambda_handler_works():
    rule = f"{_UNIQUE_PREFIX}lambda"
    register_node_handler(rule, lambda children: sum(children))
    handler = get_node_handler(rule)
    assert handler([1, 2, 3]) == 6
