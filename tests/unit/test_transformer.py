"""Tests for uqal_core.ast.transformer"""
import pytest
from pathlib import Path
from lark import Lark
from uqal_core.ast.transformer import UQALTransformer
from uqal_core.ast.nodes import (
    BinaryOp,
    BoolLiteral,
    Compare,
    ConnectCommand,
    DbConnectionCall,
    DbQueryBlock,
    DbTableCall,
    DbWriteCall,
    FieldParam,
    FieldsParam,
    ForStatement,
    IfStatement,
    IntegerLiteral,
    LetStatement,
    ListDbsCommand,
    ListModulesCommand,
    LogicalAnd,
    Program,
    SchemaDefinition,
    StringLiteral,
    VariableRef,
    WhereParam,
    WhileStatement,
)

pytestmark = pytest.mark.unit

_PROJECT_ROOT = Path(__file__).parent.parent.parent
_GRAMMAR = (_PROJECT_ROOT / "src/uqal_core/parser/base_grammar.lark").read_text()
_IMPORT_PATHS = [str(_PROJECT_ROOT / "src/uqal_core/parser")]


@pytest.fixture(scope="module")
def parse():
    parser = Lark(_GRAMMAR, parser="earley", import_paths=_IMPORT_PATHS)
    transformer = UQALTransformer()

    def _parse(script: str) -> Program:
        tree = parser.parse(script)
        return transformer.transform(tree)

    return _parse


def test_let_integer(parse):
    p = parse("let a = 5")
    stmt = p.statements[0]
    assert isinstance(stmt, LetStatement)
    assert stmt.name == "a"
    assert isinstance(stmt.value, IntegerLiteral)
    assert stmt.value.value == 5


def test_let_string(parse):
    p = parse('let b = "hello"')
    stmt = p.statements[0]
    assert isinstance(stmt.value, StringLiteral)
    assert stmt.value.value == "hello"


def test_let_bool(parse):
    p = parse("let c = true")
    assert isinstance(p.statements[0].value, BoolLiteral)
    assert p.statements[0].value.value is True


def test_binary_op(parse):
    p = parse("let result = a + b")
    op = p.statements[0].value
    assert isinstance(op, BinaryOp)
    assert op.operator == "+"


def test_db_table_call(parse):
    p = parse("db1.orders.get_value(where id = 5, field amount)")
    stmt = p.statements[0]
    assert isinstance(stmt, DbTableCall)
    assert stmt.connection == "db1"
    assert stmt.table == "orders"
    assert stmt.command == "get_value"


def test_db_table_call_params(parse):
    p = parse("db1.orders.get_value(where id = 5, field amount)")
    stmt = p.statements[0]
    where = next(x for x in stmt.params if isinstance(x, WhereParam))
    field = next(x for x in stmt.params if isinstance(x, FieldParam))
    assert isinstance(where.condition, Compare)
    assert field.name == "amount"


def test_db_write_call(parse):
    p = parse('db1.users.insert_table({"id": integer(primary_key: true), "name": string})')
    stmt = p.statements[0]
    assert isinstance(stmt, DbWriteCall)
    assert stmt.command == "insert_table"
    assert isinstance(stmt.payload, SchemaDefinition)
    assert len(stmt.payload.fields) == 2


def test_db_connection_call(parse):
    p = parse("db1.list_tables")
    stmt = p.statements[0]
    assert isinstance(stmt, DbConnectionCall)
    assert stmt.connection == "db1"
    assert stmt.command == "list_tables"


def test_list_dbs(parse):
    p = parse("list dbs")
    assert isinstance(p.statements[0], ListDbsCommand)


def test_list_modules(parse):
    p = parse("list modules")
    assert isinstance(p.statements[0], ListModulesCommand)


def test_connect_command(parse):
    p = parse('connect db1 as postgresql(host = "localhost")')
    stmt = p.statements[0]
    assert isinstance(stmt, ConnectCommand)
    assert stmt.connection_name == "db1"
    assert stmt.module_type == "postgresql"


def test_if_statement(parse):
    p = parse("if age > 18 : let a = 5")
    stmt = p.statements[0]
    assert isinstance(stmt, IfStatement)
    assert isinstance(stmt.condition, Compare)
    assert len(stmt.then_block) == 1


def test_for_statement(parse):
    p = parse("for row in orders : let x = row")
    stmt = p.statements[0]
    assert isinstance(stmt, ForStatement)
    assert stmt.variable == "row"


def test_while_statement(parse):
    p = parse("while active = true : let x = 1")
    stmt = p.statements[0]
    assert isinstance(stmt, WhileStatement)


def test_query_block(parse):
    p = parse(
        'let result = db1.query: '
        'let o = table orders where status = "open" '
        'return o.id, o.name'
    )
    stmt = p.statements[0]
    assert isinstance(stmt, LetStatement)
    assert isinstance(stmt.value, DbQueryBlock)
    assert stmt.value.connection == "db1"
    assert len(stmt.value.aliases) == 1
