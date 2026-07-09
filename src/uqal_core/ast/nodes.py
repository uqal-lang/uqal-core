"""
AST node definitions.

One dataclass per meaningful grammar rule. The transformer
(transformer.py) converts the raw lark parse tree into these
typed Python objects.

Nodes are grouped into five categories:
  - Literals        (IntegerLiteral, StringLiteral, ...)
  - Expressions     (BinaryOp, VariableRef)
  - Conditions      (Compare, LogicalAnd, LogicalOr, ...)
  - Statements      (LetStatement, IfStatement, ...)
  - DB Operations   (DbTableCall, DbQueryBlock, ...)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


# ============================================================
# Base
# ============================================================

@dataclass
class Node:
    """Base class for all AST nodes."""
    pass


# ============================================================
# Literals
# ============================================================

@dataclass
class IntegerLiteral(Node):
    value: int


@dataclass
class FloatLiteral(Node):
    value: float


@dataclass
class StringLiteral(Node):
    value: str


@dataclass
class BoolLiteral(Node):
    value: bool


@dataclass
class NullLiteral(Node):
    pass


# ============================================================
# Expressions
# ============================================================

@dataclass
class BinaryOp(Node):
    """Arithmetic operation: a + b, a * b, etc."""
    left: Node
    operator: str
    right: Node


@dataclass
class Negate(Node):
    """Unary minus: -5, -a"""
    operand: Node


@dataclass
class VariableRef(Node):
    """
    Variable or field access: a, a.field, a.row(0), a.row(0).value("x")
    Parts holds the dot-separated path as a list of strings/accessors.
    """
    parts: list[str | RowIndex | RowValue | FieldValue]


@dataclass
class RowIndex(Node):
    """a.row(0)"""
    index: int


@dataclass
class RowValue(Node):
    """a.row(0).value("field")"""
    index: int
    field_name: str


@dataclass
class FieldValue(Node):
    """a.value("field")"""
    field_name: str


# ============================================================
# Conditions
# ============================================================

@dataclass
class Compare(Node):
    """age > 18, status = "open", user_id == a.id"""
    left: Node
    operator: str
    right: Node


@dataclass
class IsNull(Node):
    """id is null"""
    operand: Node


@dataclass
class IsNotNull(Node):
    """id is not null"""
    operand: Node


@dataclass
class LogicalAnd(Node):
    """age > 18 and active = true"""
    left: Node
    right: Node


@dataclass
class LogicalOr(Node):
    """age > 18 or admin = true"""
    left: Node
    right: Node


@dataclass
class LogicalNot(Node):
    """not active = true"""
    operand: Node


# ============================================================
# Type expressions
# ============================================================

@dataclass
class CoreTypeRef(Node):
    """integer, string, boolean, ..."""
    name: str


@dataclass
class ModuleTypeRef(Node):
    """postgis.geo, postgresql.varchar(200)"""
    module_name: str
    type_name: str
    param: str | int | None = None


@dataclass
class FieldDefinition(Node):
    """A single field in an insert_table schema."""
    name: str
    type_ref: CoreTypeRef | ModuleTypeRef
    primary_key: bool = False
    required: bool = False


@dataclass
class SchemaDefinition(Node):
    """The full schema passed to insert_table."""
    fields: list[FieldDefinition]


# ============================================================
# Parameters
# ============================================================

@dataclass
class WhereParam(Node):
    condition: Node


@dataclass
class FieldsParam(Node):
    """fields id, amount, name"""
    names: list[str]


@dataclass
class FieldParam(Node):
    """field amount"""
    name: str


@dataclass
class LiveParam(Node):
    """live = true"""
    value: bool


@dataclass
class NameParam(Node):
    """key = value"""
    name: str
    value: Node


# ============================================================
# DB Operations
# ============================================================

@dataclass
class DbGenericCall(Node):
    """db1.(table orders, where status = "open", get id, amount)"""
    connection: str
    params: list[Node]


@dataclass
class DbTableCall(Node):
    """db1.orders.get_value(where id = 5, field amount)"""
    connection: str
    table: str
    command: str
    params: list[Node]


@dataclass
class DbWriteCall(Node):
    """db1.users.insert_table({...})"""
    connection: str
    table: str
    command: str
    # For insert_table: SchemaDefinition
    # For insert_row/update/delete: list of params
    payload: SchemaDefinition | list[Node]


@dataclass
class DbConnectionCall(Node):
    """db1.list_tables, db1.list_tables(live=true), db1.sync_schema"""
    connection: str
    command: str
    params: list[Node] = field(default_factory=list)


@dataclass
class QueryAlias(Node):
    """let o = table orders where status = "open" (inside db.query:)"""
    alias: str
    table: str
    condition: Node | None = None


@dataclass
class QueryReturn(Node):
    """return o.id, u.name"""
    fields: list[PrefixedField | PlainField]


@dataclass
class PrefixedField(Node):
    """o.id"""
    prefix: str
    name: str


@dataclass
class PlainField(Node):
    """id"""
    name: str


@dataclass
class DbQueryBlock(Node):
    """
    let result = db1.query:
        let o = table orders where status = "open"
        let u = table user where user_id == o.id
        return o.id, u.name
    """
    connection: str
    aliases: list[QueryAlias]
    returns: QueryReturn


# ============================================================
# Statements
# ============================================================

@dataclass
class LetStatement(Node):
    name: str
    value: Node


@dataclass
class IfStatement(Node):
    condition: Node
    then_block: list[Node]
    elif_clauses: list[tuple[Node, list[Node]]] = field(default_factory=list)
    else_block: list[Node] | None = None


@dataclass
class ForStatement(Node):
    variable: str
    iterable: Node
    body: list[Node]


@dataclass
class WhileStatement(Node):
    condition: Node
    body: list[Node]


# ============================================================
# Setup and System commands
# ============================================================

@dataclass
class ConnectCommand(Node):
    """connect db1 as postgresql(host = "localhost", port = 5432)"""
    connection_name: str
    module_type: str
    params: list[NameParam]


@dataclass
class SyncSchemaCommand(Node):
    """db1.sync_schema"""
    connection: str


@dataclass
class ListDbsCommand(Node):
    pass


@dataclass
class ListModulesCommand(Node):
    pass


# ============================================================
# Program root
# ============================================================

@dataclass
class Program(Node):
    """The root node - a complete UQAL script."""
    statements: list[Node]

# ============================================================
# Output statements
# ============================================================
@dataclass
class OutputField(Node):
    """A single variable name in an output statement."""
    name: str


@dataclass
class OutputStatement(Node):
    """output price1, price2, total"""
    fields: list[OutputField]

# ============================================================
# Create view statements
# ============================================================

@dataclass
class ViewAlias(Node):
    """let o = table orders where status = 'open'"""
    alias: str
    table: str
    condition: Any | None = None


@dataclass
class CreateViewStatement(Node):
    """
    testdb.create_view order_overview:
        let o = table orders
        let u = table users where u.id = o.user_id
        return o.id, o.status, u.name
    """
    connection: str
    view_name: str
    aliases: list[ViewAlias]
    returns: QueryReturn

@dataclass
class AliasedPrefixedField(Node):
    """e.name AS employee_name"""
    prefix: str
    name: str
    alias: str

@dataclass
class RelationshipTraversal(Node):
    """
    Graph relationship traversal condition.
    u PLACED o  or  o CONTAINS[quantity, unit_price] p

    Used only in Neo4j query blocks — the core transformer
    catches this via __default__() and returns the raw node,
    the Neo4j translator handles it specifically.
    """
    source_alias: str
    relationship_type: str
    target_alias: str
    properties: list[str] = field(default_factory=list)