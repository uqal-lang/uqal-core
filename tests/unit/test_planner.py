"""Tests for uqal_core.planner.query_planner"""
import pytest
from pathlib import Path
from lark import Lark
from uqal_core.ast.transformer import UQALTransformer
from uqal_core.ast.nodes import Program
from uqal_core.planner.query_planner import (
    ExecutionPlan,
    QueryPlanner,
    StepKind,
)

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
def planner():
    return QueryPlanner()


# ---- Basic step kinds ----

def test_let_literal_is_core_compute(parse, planner):
    plan = planner.plan(parse("let a = 5"))
    assert len(plan.steps) == 1
    assert plan.steps[0].kind == StepKind.CORE_COMPUTE
    assert plan.steps[0].result_var == "a"


def test_let_db_call_is_db_query(parse, planner):
    plan = planner.plan(parse(
        "let a = db1.orders.get_value(where id = 5, field amount)"
    ))
    assert len(plan.steps) == 1
    assert plan.steps[0].kind == StepKind.DB_QUERY
    assert plan.steps[0].connection == "db1"
    assert plan.steps[0].result_var == "a"


def test_standalone_db_call_is_db_query(parse, planner):
    plan = planner.plan(parse(
        "db1.orders.get_value(where id = 5, field amount)"
    ))
    assert len(plan.steps) == 1
    assert plan.steps[0].kind == StepKind.DB_QUERY
    assert plan.steps[0].connection == "db1"
    assert plan.steps[0].result_var is None


def test_list_dbs_is_system(parse, planner):
    plan = planner.plan(parse("list dbs"))
    assert plan.steps[0].kind == StepKind.SYSTEM


def test_list_modules_is_system(parse, planner):
    plan = planner.plan(parse("list modules"))
    assert plan.steps[0].kind == StepKind.SYSTEM


def test_sync_schema_is_setup(parse, planner):
    plan = planner.plan(parse("db1.sync_schema"))
    assert plan.steps[0].kind == StepKind.SETUP


def test_connect_is_setup(parse, planner):
    plan = planner.plan(parse(
        'connect db1 as postgresql(host = "localhost")'
    ))
    assert plan.steps[0].kind == StepKind.SETUP


def test_connection_meta_is_meta(parse, planner):
    plan = planner.plan(parse("db1.list_tables"))
    assert plan.steps[0].kind == StepKind.META
    assert plan.steps[0].connection == "db1"


# ---- Multiple steps ----

def test_two_lets_produce_two_steps(parse, planner):
    plan = planner.plan(parse("let a = 5 let b = 10"))
    assert len(plan.steps) == 2


def test_cross_db_computation_has_three_steps(parse, planner):
    plan = planner.plan(parse(
        "let a = db1.orders.get_value(where id = 5, field amount) "
        "let b = db2.stats.get_value(where id = 5, field value) "
        "let result = a + b"
    ))
    assert len(plan.steps) == 3
    assert plan.steps[0].kind == StepKind.DB_QUERY
    assert plan.steps[1].kind == StepKind.DB_QUERY
    assert plan.steps[2].kind == StepKind.CORE_COMPUTE


def test_cross_db_result_depends_on_both(parse, planner):
    plan = planner.plan(parse(
        "let a = db1.orders.get_value(where id = 5, field amount) "
        "let b = db2.stats.get_value(where id = 5, field value) "
        "let result = a + b"
    ))
    result_step = plan.steps[2]
    assert 0 in result_step.depends_on
    assert 1 in result_step.depends_on


def test_same_connection_steps_are_independent(parse, planner):
    plan = planner.plan(parse(
        "let a = db1.orders.get_value(where id = 5, field amount) "
        "let b = db1.users.get_value(where id = 5, field name)"
    ))
    assert plan.steps[0].connection == "db1"
    assert plan.steps[1].connection == "db1"
    assert plan.steps[1].depends_on == []


# ---- Query block ----

def test_query_block_is_single_db_step(parse, planner):
    plan = planner.plan(parse(
        'let result = db1.query: '
        'let o = table orders where status = "open" '
        'return o.id, o.name'
    ))
    assert len(plan.steps) == 1
    assert plan.steps[0].kind == StepKind.DB_QUERY
    assert plan.steps[0].metadata.get("block") is True
    assert plan.steps[0].connection == "db1"


# ---- Control flow ----

def test_if_produces_control_flow_step(parse, planner):
    plan = planner.plan(parse("if age > 18 : let a = 5"))
    assert any(s.kind == StepKind.CONTROL_FLOW for s in plan.steps)


def test_for_loop_produces_control_flow_step(parse, planner):
    plan = planner.plan(parse("for row in orders : let x = row"))
    assert any(s.kind == StepKind.CONTROL_FLOW for s in plan.steps)


# ---- ExecutionPlan helpers ----

def test_plan_db_steps_filter(parse, planner):
    plan = planner.plan(parse(
        "let a = db1.orders.get_value(where id = 5, field amount) "
        "let b = 5"
    ))
    assert len(plan.db_steps()) == 1
    assert len(plan.core_steps()) == 1


def test_cross_db_detection(parse, planner):
    plan = planner.plan(parse(
        "let a = db1.orders.get_value(where id = 5, field amount) "
        "let b = db2.stats.get_value(where id = 5, field value)"
    ))
    assert plan.steps[0].is_cross_db(plan.steps[1])


def test_same_db_not_cross_db(parse, planner):
    plan = planner.plan(parse(
        "let a = db1.orders.get_value(where id = 5, field amount) "
        "let b = db1.users.get_value(where id = 5, field name)"
    ))
    assert not plan.steps[0].is_cross_db(plan.steps[1])