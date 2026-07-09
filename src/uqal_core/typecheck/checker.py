"""
Type checker.

Walks the AST before execution and validates:
  1. Variable references - are variables defined before use?
  2. Connection references - is the connection registered?
  3. Field references - does the field exist in the schema?
  4. Type compatibility - are operations valid for the involved types?
  5. Module capabilities - are module-specific commands available?

Returns a list of TypeCheckError instances. An empty list means
the script is safe to pass to the planner and executor.

Design principle: the checker never raises exceptions - it collects
ALL errors in one pass so the user sees everything at once, not just
the first problem.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from uqal_core.ast.nodes import (
    BinaryOp,
    BoolLiteral,
    Compare,
    ConnectCommand,
    CoreTypeRef,
    DbConnectionCall,
    DbGenericCall,
    DbQueryBlock,
    DbTableCall,
    DbWriteCall,
    FieldParam,
    FieldsParam,
    FloatLiteral,
    ForStatement,
    IfStatement,
    IntegerLiteral,
    IsNotNull,
    IsNull,
    LetStatement,
    ListDbsCommand,
    ListModulesCommand,
    LogicalAnd,
    LogicalNot,
    LogicalOr,
    ModuleTypeRef,
    NameParam,
    Negate,
    NullLiteral,
    PlainField,
    PrefixedField,
    Program,
    QueryAlias,
    QueryReturn,
    SchemaDefinition,
    StringLiteral,
    SyncSchemaCommand,
    VariableRef,
    WhereParam,
    WhileStatement,
)
from uqal_core.registry.connection_registry import ConnectionRegistry
from uqal_core.registry.module_registry import ModuleRegistry
from uqal_core.types import CoreType, is_core_type_name


@dataclass
class TypeCheckError:
    """A single type check error with a human-readable message."""
    message: str
    node: Any = None

    def __str__(self) -> str:
        return self.message


@dataclass
class Scope:
    """
    Tracks variable types during type checking.

    Each let statement adds a variable to the scope. Nested blocks
    (if/for/while) get a child scope so inner variables don't leak
    into outer scope.
    """
    _vars: dict[str, str] = field(default_factory=dict)
    _parent: "Scope | None" = None

    def define(self, name: str, type_name: str) -> None:
        self._vars[name] = type_name

    def lookup(self, name: str) -> str | None:
        if name in self._vars:
            return self._vars[name]
        if self._parent is not None:
            return self._parent.lookup(name)
        return None

    def child(self) -> "Scope":
        return Scope(_parent=self)


class TypeChecker:
    """
    Walks the AST and collects type errors.

    Usage:
        checker = TypeChecker(module_registry, connection_registry)
        errors = checker.check(program)
        if errors:
            for err in errors:
                print(err)
    """

    def __init__(
        self,
        module_registry: ModuleRegistry,
        connection_registry: ConnectionRegistry,
    ) -> None:
        self._modules = module_registry
        self._connections = connection_registry
        self._errors: list[TypeCheckError] = []

    def check(self, program: Program) -> list[TypeCheckError]:
        """
        Main entry point. Returns all type errors found in the program.
        """
        self._errors = []
        scope = Scope()
        self._check_statements(program.statements, scope)
        return self._errors

    # ---- Error helpers ----

    def _error(self, message: str, node: Any = None) -> None:
        self._errors.append(TypeCheckError(message=message, node=node))

    # ---- Statement dispatch ----

    def _check_statements(
        self, statements: list, scope: Scope
    ) -> None:
        for stmt in statements:
            self._check_statement(stmt, scope)

    def _check_statement(self, stmt: Any, scope: Scope) -> None:
        if isinstance(stmt, LetStatement):
            self._check_let(stmt, scope)
        elif isinstance(stmt, IfStatement):
            self._check_if(stmt, scope)
        elif isinstance(stmt, ForStatement):
            self._check_for(stmt, scope)
        elif isinstance(stmt, WhileStatement):
            self._check_while(stmt, scope)
        elif isinstance(stmt, DbTableCall):
            self._check_db_table_call(stmt, scope)
        elif isinstance(stmt, DbWriteCall):
            self._check_db_write_call(stmt, scope)
        elif isinstance(stmt, DbConnectionCall):
            self._check_connection_ref(stmt.connection, stmt)
        elif isinstance(stmt, DbQueryBlock):
            self._check_query_block(stmt, scope)
        elif isinstance(stmt, ConnectCommand):
            pass
        elif isinstance(stmt, SyncSchemaCommand):
            self._check_connection_ref(stmt.connection, stmt)
        elif isinstance(stmt, (ListDbsCommand, ListModulesCommand)):
            pass

    # ---- Let ----

    def _check_let(self, stmt: LetStatement, scope: Scope) -> None:
        inferred = self._infer_type(stmt.value, scope)
        scope.define(stmt.name, inferred)

    # ---- Control flow ----

    def _check_if(self, stmt: IfStatement, scope: Scope) -> None:
        self._check_condition(stmt.condition, scope)
        self._check_statements(stmt.then_block, scope.child())
        for cond, block in stmt.elif_clauses:
            self._check_condition(cond, scope)
            self._check_statements(block, scope.child())
        if stmt.else_block:
            self._check_statements(stmt.else_block, scope.child())

    def _check_for(self, stmt: ForStatement, scope: Scope) -> None:
        self._infer_type(stmt.iterable, scope)
        child = scope.child()
        child.define(stmt.variable, "row")
        self._check_statements(stmt.body, child)

    def _check_while(self, stmt: WhileStatement, scope: Scope) -> None:
        self._check_condition(stmt.condition, scope)
        self._check_statements(stmt.body, scope.child())

    # ---- DB calls ----

    def _check_db_table_call(
        self, stmt: DbTableCall, scope: Scope
    ) -> None:
        self._check_connection_ref(stmt.connection, stmt)
        self._check_table_ref(stmt.connection, stmt.table, stmt)
        self._check_params(stmt.params, scope, stmt.connection, stmt.table)

    def _check_db_write_call(
        self, stmt: DbWriteCall, scope: Scope
    ) -> None:
        self._check_connection_ref(stmt.connection, stmt)
        if stmt.command != "insert_table":
            self._check_table_ref(stmt.connection, stmt.table, stmt)
        if isinstance(stmt.payload, SchemaDefinition):
            self._check_schema_def(stmt.payload, stmt)

    def _check_query_block(
        self, block: DbQueryBlock, scope: Scope
    ) -> None:
        self._check_connection_ref(block.connection, block)
        alias_scope = scope.child()
        for alias in block.aliases:
            self._check_table_ref(block.connection, alias.table, alias)
            if alias.condition:
                self._check_condition(alias.condition, alias_scope)
            alias_scope.define(alias.alias, "table_ref")

    # ---- Connection and table reference checks ----

    def _check_connection_ref(
        self, connection_name: str, node: Any
    ) -> None:
        if not connection_name:
            return
        if not self._connections.has(connection_name):
            self._error(
                f"Connection '{connection_name}' is not registered. "
                f"Known connections: "
                f"{self._connections.list_connections()}. "
                f"Use 'uqal add-connection' to register it first.",
                node,
            )

    def _check_table_ref(
        self, connection_name: str, table_name: str, node: Any
    ) -> None:
        if not self._connections.has(connection_name):
            return

        # Use registry schema store, not module's internal store
        try:
            schema = self._modules.get_schema(connection_name)
        except KeyError:
            return  # No schema loaded yet - skip check

        if not schema.has_table(table_name):
            self._error(
                f"Table '{table_name}' does not exist in connection "
                f"'{connection_name}'. "
                f"Known tables: {schema.list_tables()}. "
                f"Run '{connection_name}.sync_schema' to refresh.",
                node,
            )

    def _check_params(
        self,
        params: list,
        scope: Scope,
        connection: str,
        table: str,
    ) -> None:
        for param in params:
            if isinstance(param, WhereParam):
                self._check_condition(param.condition, scope)
            elif isinstance(param, FieldParam):
                self._check_field_ref(connection, table, param.name, param)
            elif isinstance(param, FieldsParam):
                for name in param.names:
                    self._check_field_ref(connection, table, name, param)
            elif isinstance(param, NameParam):
                self._infer_type(param.value, scope)

    def _check_field_ref(
        self,
        connection: str,
        table: str,
        field_name: str,
        node: Any,
    ) -> None:
        if not self._connections.has(connection):
            return

        try:
            schema = self._modules.get_schema(connection)
        except KeyError:
            return

        if not schema.has_table(table):
            return

        table_def = schema.get_table(table)

        # Flexible collections (no $jsonSchema) allow any field
        if table_def.native_metadata.get("flexible"):
            return

        if not table_def.has_field(field_name):
            # Check if it's a dot-notation access on a flexible field
            # e.g. address.city where address is flexible=True
            base_field = field_name.split(".")[0]
            base = table_def.get_field(base_field)
            if base and base.flexible:
                return  # Sub-field of flexible object - allowed

            self._error(
                f"Field '{field_name}' does not exist in table "
                f"'{table}' on connection '{connection}'. "
                f"Known fields: "
                f"{[f.name for f in table_def.fields]}.",
                node,
            )

    def _check_schema_def(
        self, schema: SchemaDefinition, node: Any
    ) -> None:
        for field_def in schema.fields:
            type_ref = field_def.type_ref
            if isinstance(type_ref, ModuleTypeRef):
                module_name = type_ref.module_name
                type_name = type_ref.type_name
                try:
                    module = self._modules.get_module(module_name)
                    caps = module.get_capabilities()
                    if type_name not in caps.provided_types:
                        self._error(
                            f"Module '{module_name}' does not provide "
                            f"type '{type_name}'. "
                            f"Available types: {caps.provided_types}.",
                            node,
                        )
                except KeyError:
                    self._error(
                        f"Module '{module_name}' is not loaded. "
                        f"Loaded modules: {self._modules.list_modules()}.",
                        node,
                    )

    # ---- Condition checks ----

    def _is_field_ref(self, node: Any) -> bool:
        """
        Returns True if this node is a bare name that should be
        treated as a field reference in a where context, not a
        variable reference.

        A bare field reference is a VariableRef with a single string
        part - e.g. "id", "status", "age". These are unambiguously
        field names in a where clause context, not scope variables.
        """
        return (
            isinstance(node, VariableRef)
            and len(node.parts) == 1
            and isinstance(node.parts[0], str)
        )

    def _infer_type_in_where(self, node: Any, scope: Scope) -> str:
        """
        Like _infer_type but treats bare names as field references
        (type unknown) instead of checking them against the scope.

        This prevents false "variable undefined" errors for field
        names used in where clauses like "where id = 5".
        """
        if self._is_field_ref(node):
            return "unknown"
        return self._infer_type(node, scope)

    def _check_condition(self, condition: Any, scope: Scope) -> None:
        if isinstance(condition, (LogicalAnd, LogicalOr)):
            self._check_condition(condition.left, scope)
            self._check_condition(condition.right, scope)
        elif isinstance(condition, LogicalNot):
            self._check_condition(condition.operand, scope)
        elif isinstance(condition, Compare):
            # Use where-aware type inference so bare names are treated
            # as field references, not undefined variables
            left_type = self._infer_type_in_where(condition.left, scope)
            right_type = self._infer_type_in_where(condition.right, scope)
            if (
                left_type != "unknown"
                and right_type != "unknown"
                and left_type != right_type
            ):
                self._error(
                    f"Type mismatch in comparison: "
                    f"left is '{left_type}', right is '{right_type}'.",
                    condition,
                )
        elif isinstance(condition, (IsNull, IsNotNull)):
            self._infer_type_in_where(condition.operand, scope)

    # ---- Type inference ----

    def _infer_type(self, node: Any, scope: Scope) -> str:
        """
        Infers the type of an expression node.
        Returns a string type name or "unknown" if undetermined.
        "unknown" is not an error - it means we cannot statically
        determine the type (e.g. result of a DB call).
        """
        if isinstance(node, IntegerLiteral):
            return CoreType.INTEGER.value
        if isinstance(node, FloatLiteral):
            return CoreType.FLOAT.value
        if isinstance(node, StringLiteral):
            return CoreType.STRING.value
        if isinstance(node, BoolLiteral):
            return CoreType.BOOLEAN.value
        if isinstance(node, NullLiteral):
            return "null"
        if isinstance(node, BinaryOp):
            return self._infer_binary_op(node, scope)
        if isinstance(node, Negate):
            inner = self._infer_type(node.operand, scope)
            if inner not in (
                CoreType.INTEGER.value,
                CoreType.FLOAT.value,
                "unknown",
            ):
                self._error(
                    f"Unary minus cannot be applied to type '{inner}'.",
                    node,
                )
            return inner
        if isinstance(node, VariableRef):
            return self._infer_variable_ref(node, scope)
        if isinstance(node, (DbTableCall, DbGenericCall, DbQueryBlock)):
            return "unknown"
        return "unknown"

    def _infer_binary_op(
        self, node: BinaryOp, scope: Scope
    ) -> str:
        left = self._infer_type(node.left, scope)
        right = self._infer_type(node.right, scope)

        if left == "unknown" or right == "unknown":
            return "unknown"

        numeric = {CoreType.INTEGER.value, CoreType.FLOAT.value}

        if node.operator in ("+", "-", "*", "/"):
            if left in numeric and right in numeric:
                if CoreType.FLOAT.value in (left, right):
                    return CoreType.FLOAT.value
                return CoreType.INTEGER.value
            if (
                node.operator == "+"
                and left == CoreType.STRING.value
                and right == CoreType.STRING.value
            ):
                return CoreType.STRING.value
            self._error(
                f"Operator '{node.operator}' cannot be applied to "
                f"types '{left}' and '{right}'.",
                node,
            )
            return "unknown"

        return "unknown"

    def _infer_variable_ref(
        self, node: VariableRef, scope: Scope
    ) -> str:
        if not node.parts:
            return "unknown"

        base_name = node.parts[0]
        if not isinstance(base_name, str):
            return "unknown"

        known_type = scope.lookup(base_name)
        if known_type is None:
            self._error(
                f"Variable '{base_name}' is used before it is defined. "
                f"Make sure it is assigned with "
                f"'let {base_name} = ...' before this point.",
                node,
            )
            return "unknown"

        return known_type