"""Tests for create_view grammar, transformer, and planner."""
import pytest
from pathlib import Path
from lark import Lark
from uqal_core.ast.transformer import UQALTransformer
from uqal_core.ast.nodes import (
    AliasedPrefixedField,
    CreateViewStatement,
    PlainField,
    PrefixedField,
    Program,
    QueryReturn,
    ViewAlias,
)
from uqal_core.planner.query_planner import QueryPlanner, StepKind

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


# ---- Grammar + Transformer ----

def test_grammar_parses_create_view(parse):
    p = parse("testdb.create_view order_summary: let o = table orders return o.id")
    assert len(p.statements) == 1
    assert isinstance(p.statements[0], CreateViewStatement)


def test_create_view_statement_connection(parse):
    p = parse("testdb.create_view my_view: let o = table orders return o.id")
    stmt = p.statements[0]
    assert stmt.connection == "testdb"


def test_create_view_statement_view_name(parse):
    p = parse("testdb.create_view my_view: let o = table orders return o.id")
    stmt = p.statements[0]
    assert stmt.view_name == "my_view"


def test_view_alias_without_where(parse):
    p = parse("testdb.create_view simple_view: let o = table orders return o.id")
    stmt = p.statements[0]
    assert len(stmt.aliases) == 1
    alias = stmt.aliases[0]
    assert isinstance(alias, ViewAlias)
    assert alias.alias == "o"
    assert alias.table == "orders"
    assert alias.condition is None


def test_view_alias_with_where(parse):
    p = parse('testdb.create_view active_orders: let o = table orders where status = "open" return o.id')
    stmt = p.statements[0]
    alias = stmt.aliases[0]
    assert isinstance(alias, ViewAlias)
    assert alias.table == "orders"
    assert alias.condition is not None


def test_multiple_aliases(parse):
    p = parse(
        "testdb.create_view user_orders: "
        "let o = table orders "
        "let u = table users "
        "return o.id, u.name"
    )
    stmt = p.statements[0]
    assert len(stmt.aliases) == 2
    assert stmt.aliases[0].table == "orders"
    assert stmt.aliases[1].table == "users"


def test_multiple_alias_names(parse):
    p = parse(
        "testdb.create_view user_orders: "
        "let o = table orders "
        "let u = table users "
        "return o.id, u.name"
    )
    stmt = p.statements[0]
    assert stmt.aliases[0].alias == "o"
    assert stmt.aliases[1].alias == "u"


def test_aliased_prefixed_field_with_as(parse):
    p = parse("testdb.create_view amounts: let o = table orders return o.amount AS total")
    stmt = p.statements[0]
    fields = stmt.returns.fields
    assert len(fields) == 1
    field = fields[0]
    assert isinstance(field, AliasedPrefixedField)
    assert field.prefix == "o"
    assert field.name == "amount"
    assert field.alias == "total"


def test_aliased_prefixed_field_lowercase_as(parse):
    p = parse("testdb.create_view v: let o = table orders return o.name as label")
    stmt = p.statements[0]
    field = stmt.returns.fields[0]
    assert isinstance(field, AliasedPrefixedField)
    assert field.alias == "label"


def test_mixed_return_fields(parse):
    p = parse("testdb.create_view v: let o = table orders return o.id, o.amount AS total")
    stmt = p.statements[0]
    fields = stmt.returns.fields
    assert len(fields) == 2
    assert isinstance(fields[0], PrefixedField)
    assert isinstance(fields[1], AliasedPrefixedField)
    assert fields[1].alias == "total"


def test_return_contains_query_return(parse):
    p = parse("testdb.create_view v: let o = table orders return o.id")
    stmt = p.statements[0]
    assert isinstance(stmt.returns, QueryReturn)


# ---- Planner: DDL step ----

def test_planner_creates_ddl_step(parse):
    p = parse("testdb.create_view order_summary: let o = table orders return o.id")
    plan = QueryPlanner().plan(p)
    assert len(plan.steps) == 1
    assert plan.steps[0].kind == StepKind.DDL


def test_planner_ddl_step_has_correct_connection(parse):
    p = parse("myconn.create_view v: let t = table data return t.id")
    plan = QueryPlanner().plan(p)
    assert plan.steps[0].connection == "myconn"


def test_planner_ddl_step_metadata_kind(parse):
    p = parse("testdb.create_view order_summary: let o = table orders return o.id")
    plan = QueryPlanner().plan(p)
    assert plan.steps[0].metadata.get("kind") == "create_view"


def test_planner_ddl_step_metadata_view_name(parse):
    p = parse("testdb.create_view order_summary: let o = table orders return o.id")
    plan = QueryPlanner().plan(p)
    assert plan.steps[0].metadata.get("view_name") == "order_summary"


def test_planner_ddl_step_node_is_create_view(parse):
    p = parse("testdb.create_view v: let o = table orders return o.id")
    plan = QueryPlanner().plan(p)
    assert isinstance(plan.steps[0].node, CreateViewStatement)


# ---- Auto-alias for duplicate field names (_build_view_projection) ----

def test_auto_alias_for_duplicate_field_names():
    """_build_view_projection auto-aliases duplicate field names with table prefix."""
    from uqal_core.modules.standard.mongodb.module import MongoDBModule

    module = MongoDBModule()
    aliases = [
        ViewAlias(alias="o", table="orders"),
        ViewAlias(alias="u", table="users"),
    ]
    returns = QueryReturn(fields=[
        PrefixedField(prefix="o", name="id"),
        PrefixedField(prefix="u", name="id"),
    ])
    projection = module._build_view_projection(returns, aliases, primary_alias="o")

    assert "id" in projection
    assert projection["id"] == "$id"
    assert "users_id" in projection
    assert projection["users_id"] == "$u.id"


def test_build_view_projection_suppresses_id(parse):
    """Projection always suppresses MongoDB _id."""
    from uqal_core.modules.standard.mongodb.module import MongoDBModule

    module = MongoDBModule()
    aliases = [ViewAlias(alias="o", table="orders")]
    returns = QueryReturn(fields=[PrefixedField(prefix="o", name="amount")])
    projection = module._build_view_projection(returns, aliases, primary_alias="o")

    assert projection.get("_id") == 0


def test_aliased_prefixed_field_uses_explicit_alias():
    """AliasedPrefixedField (AS keyword) keeps the explicit alias, no auto-rename."""
    from uqal_core.modules.standard.mongodb.module import MongoDBModule

    module = MongoDBModule()
    aliases = [ViewAlias(alias="o", table="orders")]
    returns = QueryReturn(fields=[
        AliasedPrefixedField(prefix="o", name="amount", alias="total"),
    ])
    projection = module._build_view_projection(returns, aliases, primary_alias="o")

    assert "total" in projection
    assert projection["total"] == "$amount"
