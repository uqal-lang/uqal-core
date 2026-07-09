"""Tests for OutputStatement execution and get_value scalar unwrapping."""
import pytest
from pathlib import Path
from lark import Lark
from unittest.mock import MagicMock
from uqal_core.ast.transformer import UQALTransformer
from uqal_core.ast.nodes import (
    DbTableCall,
    FieldParam,
    OutputField,
    OutputStatement,
    Program,
)
from uqal_core.execution.executor import Executor, ExecutionContext
from uqal_core.execution.result_set import ResultSet
from uqal_core.planner.query_planner import ExecutionPlan, QueryPlanner, Step, StepKind
from uqal_core.registry.connection_registry import (
    ConnectionConfig,
    ConnectionRegistry,
)
from uqal_core.registry.module_registry import ModuleRegistry
from uqal_core.module_loader import ModuleLoader

pytestmark = pytest.mark.unit

_PROJECT_ROOT = Path(__file__).parent.parent.parent
_GRAMMAR = (_PROJECT_ROOT / "src/uqal_core/parser/base_grammar.lark").read_text()
_IMPORT_PATHS = [str(_PROJECT_ROOT / "src/uqal_core/parser")]


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


# ---- OutputStatement: parsed via full pipeline ----

def test_output_result_is_dict(parse, empty_executor):
    results = run(empty_executor, parse, "let x = 42 output x")
    assert isinstance(results[-1].result, dict)


def test_output_contains_variable(parse, empty_executor):
    results = run(empty_executor, parse, "let x = 42 output x")
    assert results[-1].result["x"] == 42


def test_output_string_variable(parse, empty_executor):
    results = run(empty_executor, parse, 'let name = "Alice" output name')
    assert results[-1].result["name"] == "Alice"


def test_output_multiple_variables(parse, empty_executor):
    results = run(empty_executor, parse, "let a = 10 let b = 20 output a, b")
    out = results[-1].result
    assert out["a"] == 10
    assert out["b"] == 20


def test_output_computed_variable(parse, empty_executor):
    results = run(empty_executor, parse, "let x = 3 let y = x + 7 output y")
    assert results[-1].result["y"] == 10


def test_output_bool_variable(parse, empty_executor):
    results = run(empty_executor, parse, "let flag = true output flag")
    assert results[-1].result["flag"] is True


def test_output_undefined_variable_is_none(parse, empty_executor):
    results = run(empty_executor, parse, "output missing_var")
    assert results[-1].result["missing_var"] is None


def test_output_step_is_marked_is_output(parse, empty_executor):
    results = run(empty_executor, parse, "let x = 1 output x")
    assert results[-1].is_output is True


def test_non_output_step_is_not_is_output(parse, empty_executor):
    results = run(empty_executor, parse, "let x = 1 output x")
    assert results[0].is_output is False


def test_output_status_is_success(parse, empty_executor):
    results = run(empty_executor, parse, "let x = 99 output x")
    assert results[-1].status == "success"


# ---- OutputStatement: direct node construction ----

def test_output_via_direct_node():
    """OutputStatement handler returns a dict of field_name → value."""
    executor = Executor(ModuleRegistry(), ConnectionRegistry())

    node = OutputStatement(fields=[
        OutputField(name="price"),
        OutputField(name="tax"),
    ])
    ctx = ExecutionContext()
    ctx.set("price", 9.99)
    ctx.set("tax", 1.50)

    step = Step(index=0, kind=StepKind.CORE_COMPUTE, node=node)
    result = executor._execute_core_compute(step, ctx)

    assert result == {"price": 9.99, "tax": 1.50}


def test_output_direct_node_missing_var_returns_none():
    executor = Executor(ModuleRegistry(), ConnectionRegistry())

    node = OutputStatement(fields=[OutputField(name="ghost")])
    ctx = ExecutionContext()
    step = Step(index=0, kind=StepKind.CORE_COMPUTE, node=node)
    result = executor._execute_core_compute(step, ctx)

    assert result["ghost"] is None


def test_output_direct_node_multiple_fields():
    executor = Executor(ModuleRegistry(), ConnectionRegistry())

    node = OutputStatement(fields=[
        OutputField(name="a"),
        OutputField(name="b"),
        OutputField(name="c"),
    ])
    ctx = ExecutionContext()
    ctx.set("a", 1)
    ctx.set("b", 2)
    ctx.set("c", 3)

    step = Step(index=0, kind=StepKind.CORE_COMPUTE, node=node)
    result = executor._execute_core_compute(step, ctx)

    assert result == {"a": 1, "b": 2, "c": 3}


# ---- get_value: auto-unwraps scalar from ResultSet ----

def test_get_value_unwraps_scalar():
    """Executor auto-unwraps get_value result from ResultSet to scalar."""
    mock_module = MagicMock()
    mock_module.translate.return_value = {"command": "find_one", "collection": "orders"}
    mock_module.execute.return_value = ResultSet.single_value(42, "amount", "test")

    mock_modules = MagicMock()
    mock_modules.get_module_for_connection.return_value = mock_module

    mock_conn_config = MagicMock()
    mock_conn_config.native_connection = MagicMock()
    mock_connections = MagicMock()
    mock_connections.get.return_value = mock_conn_config

    executor = Executor(mock_modules, mock_connections)

    node = DbTableCall(
        connection="testdb",
        table="orders",
        command="get_value",
        params=[FieldParam(name="amount")],
    )
    step = Step(index=0, kind=StepKind.DB_QUERY, node=node, connection="testdb")
    ctx = ExecutionContext()

    result = executor._execute_db_query(step, ctx)

    assert result == 42
    assert not isinstance(result, ResultSet)


def test_get_value_unwraps_string_scalar():
    mock_module = MagicMock()
    mock_module.translate.return_value = {}
    mock_module.execute.return_value = ResultSet.single_value("active", "status", "test")

    mock_modules = MagicMock()
    mock_modules.get_module_for_connection.return_value = mock_module

    mock_conn_config = MagicMock()
    mock_conn_config.native_connection = MagicMock()
    mock_connections = MagicMock()
    mock_connections.get.return_value = mock_conn_config

    executor = Executor(mock_modules, mock_connections)

    node = DbTableCall(
        connection="testdb",
        table="orders",
        command="get_value",
        params=[FieldParam(name="status")],
    )
    step = Step(index=0, kind=StepKind.DB_QUERY, node=node, connection="testdb")
    result = executor._execute_db_query(step, ExecutionContext())

    assert result == "active"


def test_get_value_returns_none_for_empty_result():
    mock_module = MagicMock()
    mock_module.translate.return_value = {}
    mock_module.execute.return_value = ResultSet(rows=[], source_module="test")

    mock_modules = MagicMock()
    mock_modules.get_module_for_connection.return_value = mock_module

    mock_conn_config = MagicMock()
    mock_conn_config.native_connection = MagicMock()
    mock_connections = MagicMock()
    mock_connections.get.return_value = mock_conn_config

    executor = Executor(mock_modules, mock_connections)

    node = DbTableCall(
        connection="testdb",
        table="orders",
        command="get_value",
        params=[FieldParam(name="amount")],
    )
    step = Step(index=0, kind=StepKind.DB_QUERY, node=node, connection="testdb")
    result = executor._execute_db_query(step, ExecutionContext())

    assert result is None


def test_get_table_does_not_unwrap():
    """get_table keeps the ResultSet intact (no scalar unwrapping)."""
    rs = ResultSet(rows=[{"id": 1}, {"id": 2}], source_module="test")

    mock_module = MagicMock()
    mock_module.translate.return_value = {}
    mock_module.execute.return_value = rs

    mock_modules = MagicMock()
    mock_modules.get_module_for_connection.return_value = mock_module

    mock_conn_config = MagicMock()
    mock_conn_config.native_connection = MagicMock()
    mock_connections = MagicMock()
    mock_connections.get.return_value = mock_conn_config

    executor = Executor(mock_modules, mock_connections)

    node = DbTableCall(
        connection="testdb",
        table="orders",
        command="get_table",
        params=[],
    )
    step = Step(index=0, kind=StepKind.DB_QUERY, node=node, connection="testdb")
    result = executor._execute_db_query(step, ExecutionContext())

    assert isinstance(result, ResultSet)
    assert len(result) == 2
