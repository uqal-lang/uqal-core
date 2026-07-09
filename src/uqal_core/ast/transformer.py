"""
AST Transformer.

Converts the raw lark parse tree into typed AST nodes (see nodes.py).

lark's Transformer class works by defining one method per grammar
rule name. When lark visits a tree node, it calls the matching method
with the node's already-transformed children as arguments. This means
the transformation is bottom-up: leaf nodes are transformed first,
then their parents, all the way up to the root.

Module-specific grammar rules (e.g. postgresql_sql, mongodb_mongo)
are handled generically by __default__() - no module-specific code
in the core transformer.
"""

from __future__ import annotations

from lark import Token, Transformer, Tree, v_args

from uqal_core.ast.nodes import (
    AliasedPrefixedField,
    BinaryOp,
    BoolLiteral,
    Compare,
    ConnectCommand,
    CoreTypeRef,
    CreateViewStatement,
    DbConnectionCall,
    DbGenericCall,
    DbQueryBlock,
    DbTableCall,
    DbWriteCall,
    FieldDefinition,
    FieldParam,
    FieldValue,
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
    LiveParam,
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
    RowIndex,
    RowValue,
    SchemaDefinition,
    StringLiteral,
    SyncSchemaCommand,
    VariableRef,
    ViewAlias,
    WhereParam,
    WhileStatement,
    OutputStatement,
    OutputField,
)


@v_args(inline=True)
class UQALTransformer(Transformer):
    """
    Transforms a lark parse tree into a typed AST.

    @v_args(inline=True) unpacks the children list into individual
    positional arguments for each method, making the signatures
    cleaner (no need to index into a children list manually).

    Module-specific rules (postgresql_sql, mongodb_mongo, etc.) are
    caught by __default__() and converted to DbConnectionCall with
    command="native_sql" - no module knowledge in the core.
    """

    # ============================================================
    # Catch-all for module-specific grammar rules
    # ============================================================

    def __default__(self, data, children, meta):
        from lark import Token
        """
        Handles module-specific grammar rules generically.

        Convention: any rule that produces a single ESCAPED_STRING
        token is treated as a native query command (e.g. sql("..."),
        mongo("..."), cypher("...")).

        This means modules can add grammar rules without touching
        the core transformer.
        """
        from uqal_core.ast.module_nodes import get_node_handler

        # Native query: single ESCAPED_STRING
        if len(children) == 1 and isinstance(children[0], Token):
            query = str(children[0])[1:-1]
            return DbConnectionCall(
                connection="",
                command="native_sql",
                params=[NameParam(
                    name="query",
                    value=StringLiteral(value=query),
                )],
            )

        # Module-registered node handler
        handler = get_node_handler(data)
        if handler:
            return handler(children)

        # Passthrough
        if len(children) == 1:
            return children[0]

        return children if children else None

    # ============================================================
    # Program root
    # ============================================================

    def start(self, *statements) -> Program:
        return Program(statements=list(statements))

    def statement(self, child) -> object:
        return child

    # ============================================================
    # Literals
    # ============================================================

    def integer_lit(self, token: Token) -> IntegerLiteral:
        return IntegerLiteral(value=int(token))

    def float_lit(self, token: Token) -> FloatLiteral:
        return FloatLiteral(value=float(token))

    def string_lit(self, token: Token) -> StringLiteral:
        return StringLiteral(value=str(token)[1:-1])

    def bool_lit(self, token: Token) -> BoolLiteral:
        return BoolLiteral(value=str(token) == "true")

    def null_lit(self) -> NullLiteral:
        return NullLiteral()

    # ============================================================
    # Expressions
    # ============================================================

    def expression(self, child) -> object:
        return child

    def addition(self, *args) -> object:
        result = args[0]
        i = 1
        while i < len(args):
            op = str(args[i])
            right = args[i + 1]
            result = BinaryOp(left=result, operator=op, right=right)
            i += 2
        return result

    def multiplication(self, *args) -> object:
        result = args[0]
        i = 1
        while i < len(args):
            op = str(args[i])
            right = args[i + 1]
            result = BinaryOp(left=result, operator=op, right=right)
            i += 2
        return result

    def atom(self, child) -> object:
        return child

    def negate(self, operand) -> Negate:
        return Negate(operand=operand)

    def variable_ref(self, *args) -> VariableRef:
        parts: list = [str(args[0])]
        parts.extend(args[1:])
        return VariableRef(parts=parts)

    def field_attr(self, token: Token) -> str:
        return str(token)

    def row_index(self, index: Token) -> RowIndex:
        return RowIndex(index=int(index))

    def row_value(self, index: Token, field_name: Token) -> RowValue:
        return RowValue(index=int(index), field_name=str(field_name)[1:-1])

    def direct_value(self, field_name: Token) -> FieldValue:
        return FieldValue(field_name=str(field_name)[1:-1])

    # ============================================================
    # Conditions
    # ============================================================

    def condition(self, child) -> object:
        return child

    def or_condition(self, *args) -> object:
        result = args[0]
        for right in args[1:]:
            result = LogicalOr(left=result, right=right)
        return result

    def and_condition(self, *args) -> object:
        result = args[0]
        for right in args[1:]:
            result = LogicalAnd(left=result, right=right)
        return result

    def not_condition(self, child) -> object:
        return child

    def negate_condition(self, operand) -> LogicalNot:
        return LogicalNot(operand=operand)

    def compare(self, left, operator: Token, right) -> Compare:
        return Compare(left=left, operator=str(operator), right=right)

    def is_null(self, operand) -> IsNull:
        return IsNull(operand=operand)

    def is_not_null(self, operand) -> IsNotNull:
        return IsNotNull(operand=operand)

    def comparison(self, child) -> object:
        return child

    # ============================================================
    # Types
    # ============================================================

    def type_expr(self, child) -> object:
        return child

    def core_type(self, token: Token) -> CoreTypeRef:
        return CoreTypeRef(name=str(token))

    def module_type(self, *args) -> ModuleTypeRef:
        module_name = str(args[0])
        type_name = str(args[1])
        param = None
        if len(args) > 2:
            raw = args[2]
            if hasattr(raw, "children"):
                raw = raw.children[0]
            try:
                param = int(raw)
            except (ValueError, TypeError):
                param = str(raw)[1:-1]
        return ModuleTypeRef(
            module_name=module_name,
            type_name=type_name,
            param=param,
        )

    def schema_def(self, *fields) -> SchemaDefinition:
        return SchemaDefinition(fields=list(fields))

    def field_def(self, name: Token, type_ref, *options) -> FieldDefinition:
        primary_key = False
        required = False
        for opt in options:
            if hasattr(opt, "children"):
                for child in opt.children:
                    if hasattr(child, "children") and len(child.children) >= 2:
                        key = str(child.children[0])
                        val = str(child.children[1]) == "true"
                        if key == "primary_key":
                            primary_key = val
                        elif key == "required":
                            required = val
        return FieldDefinition(
            name=str(name)[1:-1],
            type_ref=type_ref,
            primary_key=primary_key,
            required=required,
        )

    # ============================================================
    # Parameters
    # ============================================================

    def param_list(self, *params) -> list:
        return list(params)

    def param(self, child) -> object:
        return child

    def where_param(self, condition) -> WhereParam:
        return WhereParam(condition=condition)

    def fields_param(self, *names) -> FieldsParam:
        return FieldsParam(names=[str(n) for n in names])

    def field_param(self, name: Token) -> FieldParam:
        return FieldParam(name=str(name))

    def live_param(self, value: Token) -> LiveParam:
        return LiveParam(value=str(value) == "true")

    def name_param(self, name: Token, value) -> NameParam:
        return NameParam(name=str(name), value=value)

    # ============================================================
    # DB calls
    # ============================================================

    def db_call_stmt(self, child) -> object:
        return child

    def db_call(self, child) -> object:
        return child

    def db_generic_call(self, connection: Token, params) -> DbGenericCall:
        return DbGenericCall(
            connection=str(connection),
            params=params if isinstance(params, list) else [params],
        )

    def db_table_call(
        self, connection: Token, table: Token, command: tuple
    ) -> DbTableCall:
        cmd_name, params = command
        return DbTableCall(
            connection=str(connection),
            table=str(table),
            command=cmd_name,
            params=params,
        )

    def db_table_command(self, *args) -> tuple:
        cmd_name = str(args[0])
        params = args[1] if len(args) > 1 and isinstance(args[1], list) else []
        return (cmd_name, params)

    def read_command(self, token: Token) -> str:
        return str(token)

    # ---- Write commands ----

    def write_command(self, child) -> tuple:
        return child

    def insert_table_cmd(self, schema: SchemaDefinition) -> tuple:
        return ("insert_table", schema)

    def insert_row_cmd(self, params: list) -> tuple:
        return ("insert_row", params if isinstance(params, list) else [])

    def update_cmd(self, params: list) -> tuple:
        return ("update", params if isinstance(params, list) else [])

    def delete_cmd(self, params: list) -> tuple:
        return ("delete", params if isinstance(params, list) else [])

    def db_write_call(
        self, connection: Token, table: Token, command: tuple
    ) -> DbWriteCall:
        cmd_name, payload = command
        return DbWriteCall(
            connection=str(connection),
            table=str(table),
            command=cmd_name,
            payload=payload,
        )

    def db_connection_call(
        self, connection: Token, command
    ) -> DbConnectionCall:
        if isinstance(command, DbConnectionCall):
            return DbConnectionCall(
                connection=str(connection),
                command=command.command,
                params=command.params,
            )
        return DbConnectionCall(
            connection=str(connection),
            command=str(command),
            params=[],
        )

    def connection_command(self, child) -> object:
        return child

    def list_tables_cmd(self, *args) -> DbConnectionCall:
        params = list(args[0]) if args and isinstance(args[0], list) else []
        return DbConnectionCall(
            connection="",
            command="list_tables",
            params=params,
        )

    def sync_schema_cmd(self) -> DbConnectionCall:
        return DbConnectionCall(
            connection="",
            command="sync_schema",
            params=[],
        )

    # ============================================================
    # Query block
    # ============================================================

    def db_query_block_stmt(self, child) -> object:
        return child

    def db_query_block(self, connection: Token, body) -> DbQueryBlock:
        aliases, returns = body
        return DbQueryBlock(
            connection=str(connection),
            aliases=aliases,
            returns=returns,
        )

    def query_body(self, *args) -> tuple:
        aliases = [a for a in args if isinstance(a, QueryAlias)]
        returns = next(r for r in args if isinstance(r, QueryReturn))
        return (aliases, returns)

    def query_alias(self, *args) -> QueryAlias:
        alias = str(args[0])
        table = str(args[1])
        condition = args[2] if len(args) > 2 else None
        return QueryAlias(alias=alias, table=table, condition=condition)

    def query_return(self, fields) -> QueryReturn:
        return QueryReturn(
            fields=fields if isinstance(fields, list) else [fields]
        )

    def return_fields(self, *fields) -> list:
        return list(fields)

    def prefixed_field(self, prefix: Token, name: Token) -> PrefixedField:
        return PrefixedField(prefix=str(prefix), name=str(name))

    def plain_field(self, name: Token) -> PlainField:
        return PlainField(name=str(name))

    # ============================================================
    # Statements
    # ============================================================

    def let_stmt(self, name: Token, value) -> LetStatement:
        return LetStatement(name=str(name), value=value)

    def let_value(self, child) -> object:
        return child

    def if_stmt(self, condition, block, *rest) -> IfStatement:
        elif_clauses = []
        else_block = None
        for item in rest:
            if hasattr(item, "data"):
                if item.data == "elif_clause":
                    elif_cond = item.children[0]
                    elif_blk = item.children[1]
                    elif_clauses.append((elif_cond, elif_blk))
                elif item.data == "else_clause":
                    else_block = item.children[0]
        return IfStatement(
            condition=condition,
            then_block=block if isinstance(block, list) else [block],
            elif_clauses=elif_clauses,
            else_block=else_block,
        )

    def elif_clause(self, condition, block) -> object:
        return Tree("elif_clause", [condition, block])

    def else_clause(self, block) -> object:
        return Tree("else_clause", [block])

    def for_stmt(
        self, variable: Token, iterable, block
    ) -> ForStatement:
        return ForStatement(
            variable=str(variable),
            iterable=iterable,
            body=block if isinstance(block, list) else [block],
        )

    def while_stmt(self, condition, block) -> WhileStatement:
        return WhileStatement(
            condition=condition,
            body=block if isinstance(block, list) else [block],
        )

    def block(self, *statements) -> list:
        return list(statements)

    # ============================================================
    # Setup and system commands
    # ============================================================

    def setup_cmd(self, child) -> object:
        return child

    def connect_cmd(
        self, name: Token, module_type: Token, params
    ) -> ConnectCommand:
        return ConnectCommand(
            connection_name=str(name),
            module_type=str(module_type),
            params=params if isinstance(params, list) else [params],
        )

    def connect_params(self, *params) -> list:
        return list(params)

    def connect_param(self, name: Token, value) -> NameParam:
        return NameParam(name=str(name), value=value)

    def sync_schema_stmt(self, connection: Token) -> SyncSchemaCommand:
        return SyncSchemaCommand(connection=str(connection))

    def list_dbs_cmd(self) -> ListDbsCommand:
        return ListDbsCommand()

    def list_modules_cmd(self) -> ListModulesCommand:
        return ListModulesCommand()
    
    # ============================================================
    # Output statements
    # ============================================================
    
    def output_stmt(self, fields) -> OutputStatement:
        return OutputStatement(
            fields=fields if isinstance(fields, list) else [fields]
        )

    def output_fields(self, *fields) -> list:
        return list(fields)

    def output_field(self, name: Token) -> OutputField:
        return OutputField(name=str(name))
    
    # ============================================================
    # Create view statements
    # ============================================================
    
    def create_view_stmt(
        self,
        connection: Token,
        view_name: Token,
        body,
    ) -> CreateViewStatement:
        aliases, returns = body
        return CreateViewStatement(
            connection=str(connection),
            view_name=str(view_name),
            aliases=aliases,
            returns=returns,
        )
    
    def view_body(self, *args) -> tuple:
        from uqal_core.ast.nodes import ViewAlias, QueryReturn
        aliases = [a for a in args if isinstance(a, ViewAlias)]
        returns = next(
            (r for r in args if isinstance(r, QueryReturn)), None
        )
        if returns is None:
            raise ValueError("view_body has no return statement.")
        return (aliases, returns)

    def view_alias(self, *args) -> "ViewAlias":
        from uqal_core.ast.nodes import ViewAlias
        alias = str(args[0])
        table = str(args[1])
        condition = args[2] if len(args) > 2 else None
        return ViewAlias(alias=alias, table=table, condition=condition)


    def aliased_prefixed_field(
        self, prefix: Token, name: Token, as_kw: Token, alias: Token
    ) -> AliasedPrefixedField:
        return AliasedPrefixedField(
            prefix=str(prefix),
            name=str(name),
            alias=str(alias),
        )

    def aliased_plain_field(
        self, name: Token, as_kw: Token, alias: Token
    ) -> AliasedPrefixedField:
        return AliasedPrefixedField(
            prefix="",
            name=str(name),
            alias=str(alias),
        )

    def view_return_fields(self, *fields) -> list:
        return list(fields)

    def view_return(self, fields) -> "QueryReturn":
        from uqal_core.ast.nodes import QueryReturn
        return QueryReturn(
            fields=fields if isinstance(fields, list) else [fields]
        )