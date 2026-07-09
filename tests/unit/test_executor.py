"""Tests for uqal_core.execution.executor"""
import pytest
from pathlib import Path
from lark import Lark
from uqal_core.ast.transformer import UQALTransformer
from uqal_core.ast.nodes import Program
from uqal_core.planner.query_planner import QueryPlanner
from uqal_core.execution.executor import Executor, ExecutionContext
from uqal_core.execution.result_set import ResultSet
from uqal_core.registry.connection_registry import (
    ConnectionConfig,
    ConnectionRegistry,
)
from uqal_core.registry.module_registry import ModuleRegistry
from uqal_core.module_loader import ModuleLoader

pytestmark = pytest.mark.unit

_GRAMMAR = (
    Path(__file__).parent.parent.parent
    / "src" / "uqal_core" / "parser" / "base_grammar.lark"
).read_text()
_IMPORT_PATHS = [str(
    Path(__file__).parent.parent.parent
    / "src" / "uqal_core" / "parser"
)]


@pytest.fixture(scope="module")
def parse():
    parser = Lark(_GRAMMAR, parser="earley", import_paths=_IMPORT_PATHS)
    transformer = UQALTransformer()

    def _parse(script: str) -> Program:
        return transformer.transform(parser.parse(script))

    return _parse


@pytest.fixture
def empty_executor():
    return Executor(ModuleRegistry(), ConnectionRegistry())


@pytest.fixture
def executor_with_dummy():
    module_registry = ModuleRegistry()
    loader = ModuleLoader(registry=module_registry)
    loader.load(["standard.dummy"])

    conn_registry = ConnectionRegistry()
    conn_registry.register(ConnectionConfig(
        connection_name="db1",
        module_type="dummy",
        module_names=["standard.dummy"],
    ))
    module_registry.bind_module_to_connection("db1", "standard.dummy")

    return Executor(module_registry, conn_registry)


def run(executor, parse, script) -> list:
    plan = QueryPlanner().plan(parse(script))
    return executor.execute(plan)


# ---- ExecutionContext ----

def test_context_set_and_get():
    ctx = ExecutionContext()
    ctx.set("a", 42)
    assert ctx.get("a") == 42


def test_context_child_inherits_parent():
    ctx = ExecutionContext()
    ctx.set("a", 42)
    child = ctx.child()
    assert child.get("a") == 42


def test_context_child_does_not_leak():
    ctx = ExecutionContext()
    child = ctx.child()
    child.set("x", 99)
    assert not ctx.has("x")


def test_context_undefined_raises():
    ctx = ExecutionContext()
    with pytest.raises(NameError, match="not defined"):
        ctx.get("undefined")


# ---- Literal expressions ----

def test_let_integer(parse, empty_executor):
    results = run(empty_executor, parse, "let a = 5")
    assert results[0].status == "success"
    assert results[0].result == 5


def test_let_string(parse, empty_executor):
    results = run(empty_executor, parse, 'let a = "hello"')
    assert results[0].status == "success"
    assert results[0].result == "hello"


def test_let_bool(parse, empty_executor):
    results = run(empty_executor, parse, "let a = true")
    assert results[0].result is True


def test_let_null(parse, empty_executor):
    results = run(empty_executor, parse, "let a = null")
    assert results[0].result is None


# ---- Arithmetic ----

def test_addition(parse, empty_executor):
    results = run(empty_executor, parse, "let a = 2 + 3")
    assert results[0].result == 5


def test_multiplication_priority(parse, empty_executor):
    results = run(empty_executor, parse, "let a = 2 + 3 * 4")
    assert results[0].result == 14


def test_subtraction(parse, empty_executor):
    results = run(empty_executor, parse, "let a = 10 - 3")
    assert results[0].result == 7


def test_division(parse, empty_executor):
    results = run(empty_executor, parse, "let a = 10 / 2")
    assert results[0].result == 5.0


def test_string_concatenation(parse, empty_executor):
    results = run(empty_executor, parse, 'let a = "hello" + " world"')
    assert results[0].result == "hello world"


# ---- Variable references ----

def test_variable_reference(parse, empty_executor):
    results = run(empty_executor, parse, "let a = 5 let b = a + 1")
    assert results[1].result == 6


def test_cross_variable_arithmetic(parse, empty_executor):
    results = run(empty_executor, parse,
                  "let a = 10 let b = 3 let c = a + b")
    assert results[2].result == 13


# ---- System commands ----

def test_list_dbs(parse, empty_executor):
    results = run(empty_executor, parse, "list dbs")
    assert results[0].status == "success"
    assert isinstance(results[0].result, list)


def test_list_modules_with_dummy(parse, executor_with_dummy):
    results = run(executor_with_dummy, parse, "list modules")
    assert results[0].status == "success"
    assert "standard.dummy" in results[0].result


# ---- DB query with dummy module ----

def test_db_query_returns_result_set(parse, executor_with_dummy):
    results = run(
        executor_with_dummy, parse,
        "let a = db1.dummy_table.get_table(where id = 5)"
    )
    assert results[0].status == "success"
    assert isinstance(results[0].result, ResultSet)


# ---- Partial failure ----

def test_partial_failure_continues(parse, empty_executor):
    # Second statement references undefined variable
    results = run(
        empty_executor, parse,
        "let a = 5 let b = undefined_var + 1"
    )
    assert results[0].status == "success"
    assert results[1].status == "failed"
    assert len(results) == 2


# ---- Control flow ----

def test_if_true_branch(parse, empty_executor):
    results = run(
        empty_executor, parse,
        "let x = 1 if x > 0 : let y = 99"
    )
    assert results[0].status == "success"


def test_while_loop_limited(parse, empty_executor):
    # Simple while that would be infinite - hits max_iterations
    results = run(
        empty_executor, parse,
        "let x = 1 while x > 0 : let z = x + 1"
    )
    # Should fail with max iterations error
    assert any(r.status == "failed" for r in results)