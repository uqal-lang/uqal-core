"""
PostgreSQL AST translator.

Converts UQAL AST nodes into PostgreSQL SQL strings using
parameterized queries (psycopg2 format) to prevent SQL injection.
"""

from __future__ import annotations

from typing import Any

from uqal_core.ast.nodes import (
    BinaryOp,
    BoolLiteral,
    Compare,
    CoreTypeRef,
    DbGenericCall,
    DbQueryBlock,
    DbTableCall,
    DbWriteCall,
    FieldParam,
    FieldsParam,
    FloatLiteral,
    IntegerLiteral,
    IsNotNull,
    IsNull,
    LogicalAnd,
    LogicalNot,
    LogicalOr,
    ModuleTypeRef,
    NameParam,
    NullLiteral,
    SchemaDefinition,
    StringLiteral,
    VariableRef,
    WhereParam,
)
from uqal_core.modules.standard.postgresql.type_mapping import (
    resolve_type,
)


class PostgreSQLTranslator:
    """
    Translates UQAL AST nodes to parameterized PostgreSQL SQL.

    Returns a tuple of (sql_string, params_tuple) that can be
    passed directly to psycopg2's cursor.execute().
    """

    def translate(self, node: Any) -> tuple[str, tuple]:
        if isinstance(node, DbTableCall):
            return self._translate_table_call(node)
        if isinstance(node, DbWriteCall):
            return self._translate_write_call(node)
        if isinstance(node, DbQueryBlock):
            return self._translate_query_block(node)
        if isinstance(node, DbGenericCall):
            return self._translate_generic_call(node)
        raise NotImplementedError(
            f"PostgreSQLTranslator cannot translate node type "
            f"'{type(node).__name__}'"
        )

    # ---- Read commands ----

    def _translate_table_call(
        self, node: DbTableCall
    ) -> tuple[str, tuple]:
        table = self._quote_identifier(node.table)
        params: list[Any] = []

        # Extract parameters
        fields = self._extract_fields(node.params)
        where_sql, where_params = self._extract_where(node.params)
        params.extend(where_params)

        field_sql = ", ".join(
            self._quote_identifier(f) for f in fields
        ) if fields else "*"

        sql = f"SELECT {field_sql} FROM {table}"
        if where_sql:
            sql += f" WHERE {where_sql}"

        # Add LIMIT 1 for single-value/single-row commands
        if node.command in ("get_value", "get_row"):
            sql += " LIMIT 1"

        return sql, tuple(params)

    # ---- Write commands ----

    def _translate_write_call(
        self, node: DbWriteCall
    ) -> tuple[str, tuple]:
        if node.command == "insert_table":
            return self._translate_create_table(node)
        if node.command == "insert_row":
            return self._translate_insert(node)
        if node.command == "update":
            return self._translate_update(node)
        if node.command == "delete":
            return self._translate_delete(node)
        raise NotImplementedError(
            f"Unknown write command: {node.command}"
        )

    def _translate_create_table(
        self, node: DbWriteCall
    ) -> tuple[str, tuple]:
        table = self._quote_identifier(node.table)
        schema: SchemaDefinition = node.payload

        col_defs = []
        constraints = []

        for field in schema.fields:
            type_ref = field.type_ref
            if isinstance(type_ref, CoreTypeRef):
                pg_type = resolve_type(type_ref.name)
            elif isinstance(type_ref, ModuleTypeRef):
                pg_type = resolve_type(
                    type_ref.type_name, type_ref.param
                )
            else:
                pg_type = "TEXT"

            col_def = (
                f"{self._quote_identifier(field.name)} {pg_type}"
            )
            if field.required:
                col_def += " NOT NULL"
            if field.primary_key:
                constraints.append(
                    f"PRIMARY KEY ({self._quote_identifier(field.name)})"
                )
            col_defs.append(col_def)

        all_defs = col_defs + constraints
        sql = (
            f"CREATE TABLE IF NOT EXISTS {table} "
            f"({', '.join(all_defs)})"
        )
        return sql, ()

    def _translate_insert(
        self, node: DbWriteCall
    ) -> tuple[str, tuple]:
        table = self._quote_identifier(node.table)
        params_list: list[Any] = node.payload \
            if isinstance(node.payload, list) else []

        name_params = [
            p for p in params_list if isinstance(p, NameParam)
        ]
        if not name_params:
            raise ValueError(
                "insert_row requires at least one field=value pair."
            )

        cols = ", ".join(
            self._quote_identifier(p.name) for p in name_params
        )
        placeholders = ", ".join("%s" for _ in name_params)
        values = tuple(
            self._eval_literal(p.value) for p in name_params
        )

        sql = (
            f"INSERT INTO {table} ({cols}) "
            f"VALUES ({placeholders}) RETURNING *"
        )
        return sql, values

    def _translate_update(
        self, node: DbWriteCall
    ) -> tuple[str, tuple]:
        table = self._quote_identifier(node.table)
        params_list = node.payload \
            if isinstance(node.payload, list) else []

        name_params = [
            p for p in params_list if isinstance(p, NameParam)
        ]
        where_params_list = [
            p for p in params_list if isinstance(p, WhereParam)
        ]

        if not name_params:
            raise ValueError("update requires at least one field=value.")
        if not where_params_list:
            raise ValueError(
                "update requires a where clause to prevent "
                "accidental full-table updates."
            )

        set_parts = []
        set_values: list[Any] = []
        for p in name_params:
            set_parts.append(
                f"{self._quote_identifier(p.name)} = %s"
            )
            set_values.append(self._eval_literal(p.value))

        where_sql, where_values = self._build_condition(
            where_params_list[0].condition
        )

        sql = (
            f"UPDATE {table} "
            f"SET {', '.join(set_parts)} "
            f"WHERE {where_sql} "
            f"RETURNING *"
        )
        return sql, tuple(set_values + list(where_values))

    def _translate_delete(
        self, node: DbWriteCall
    ) -> tuple[str, tuple]:
        table = self._quote_identifier(node.table)
        params_list = node.payload \
            if isinstance(node.payload, list) else []

        where_params_list = [
            p for p in params_list if isinstance(p, WhereParam)
        ]
        if not where_params_list:
            raise ValueError(
                "delete requires a where clause to prevent "
                "accidental full-table deletes."
            )

        where_sql, where_values = self._build_condition(
            where_params_list[0].condition
        )

        sql = f"DELETE FROM {table} WHERE {where_sql}"
        return sql, tuple(where_values)

    # ---- Query block (JOIN) ----

    def _translate_query_block(
        self, node: DbQueryBlock
    ) -> tuple[str, tuple]:
        if not node.aliases:
            raise ValueError("Query block has no table aliases.")

        params: list[Any] = []
        primary = node.aliases[0]
        primary_table = self._quote_identifier(primary.table)
        primary_alias = self._quote_identifier(primary.alias)

        from_clause = f"{primary_table} {primary_alias}"
        join_clauses = []

        for alias in node.aliases[1:]:
            t = self._quote_identifier(alias.table)
            a = self._quote_identifier(alias.alias)
            if alias.condition:
                cond_sql, cond_params = self._build_condition(
                    alias.condition
                )
                params.extend(cond_params)
                join_clauses.append(
                    f"JOIN {t} {a} ON {cond_sql}"
                )
            else:
                join_clauses.append(f"CROSS JOIN {t} {a}")

        # Return fields
        return_fields = []
        for rf in node.returns.fields:
            if hasattr(rf, "prefix"):
                return_fields.append(
                    f"{self._quote_identifier(rf.prefix)}."
                    f"{self._quote_identifier(rf.name)}"
                )
            else:
                return_fields.append(self._quote_identifier(rf.name))

        field_sql = ", ".join(return_fields) if return_fields else "*"

        sql = f"SELECT {field_sql} FROM {from_clause}"
        if join_clauses:
            sql += " " + " ".join(join_clauses)

        # Primary table WHERE condition
        if primary.condition:
            where_sql, where_params = self._build_condition(
                primary.condition
            )
            sql += f" WHERE {where_sql}"
            params = list(where_params) + params

        return sql, tuple(params)

    # ---- Generic call ----

    def _translate_generic_call(
        self, node: DbGenericCall
    ) -> tuple[str, tuple]:
        # Generic calls are converted to SELECT with all params
        fields = self._extract_fields(node.params)
        where_sql, where_params = self._extract_where(node.params)

        field_sql = ", ".join(fields) if fields else "*"
        # table comes from params
        table_param = next(
            (p for p in node.params
             if isinstance(p, NameParam) and p.name == "table"),
            None,
        )
        table = self._quote_identifier(
            str(table_param.value) if table_param else "unknown"
        )
        sql = f"SELECT {field_sql} FROM {table}"
        if where_sql:
            sql += f" WHERE {where_sql}"
        return sql, tuple(where_params)

    # ---- Condition builder ----

    def _build_condition(
        self, condition: Any
    ) -> tuple[str, list[Any]]:
        params: list[Any] = []

        if isinstance(condition, Compare):
            left = self._expr_to_sql(condition.left, params)
            right = self._expr_to_sql(condition.right, params)
            op = self._map_operator(condition.operator)
            return f"{left} {op} {right}", params

        if isinstance(condition, IsNull):
            left = self._expr_to_sql(condition.operand, params)
            return f"{left} IS NULL", params

        if isinstance(condition, IsNotNull):
            left = self._expr_to_sql(condition.operand, params)
            return f"{left} IS NOT NULL", params

        if isinstance(condition, LogicalAnd):
            left_sql, left_params = self._build_condition(
                condition.left
            )
            right_sql, right_params = self._build_condition(
                condition.right
            )
            return (
                f"({left_sql} AND {right_sql})",
                left_params + right_params,
            )

        if isinstance(condition, LogicalOr):
            left_sql, left_params = self._build_condition(
                condition.left
            )
            right_sql, right_params = self._build_condition(
                condition.right
            )
            return (
                f"({left_sql} OR {right_sql})",
                left_params + right_params,
            )

        if isinstance(condition, LogicalNot):
            inner_sql, inner_params = self._build_condition(
                condition.operand
            )
            return f"NOT ({inner_sql})", inner_params

        from uqal_core.ast.condition_registry import get_condition_builder
        builder = get_condition_builder(type(condition))
        if builder:
            sql, ext_params = builder(condition)
            return sql, list(ext_params)

        return "TRUE", []

    def _expr_to_sql(
        self, node: Any, params: list[Any]
    ) -> str:
        if isinstance(node, IntegerLiteral):
            params.append(node.value)
            return "%s"
        if isinstance(node, FloatLiteral):
            params.append(node.value)
            return "%s"
        if isinstance(node, StringLiteral):
            params.append(node.value)
            return "%s"
        if isinstance(node, BoolLiteral):
            params.append(node.value)
            return "%s"
        if isinstance(node, NullLiteral):
            return "NULL"
        if isinstance(node, VariableRef):
            # Field reference - use as identifier
            parts = [
                str(p) for p in node.parts
                if isinstance(p, str)
            ]
            return ".".join(
                self._quote_identifier(p) for p in parts
            )
        if isinstance(node, BinaryOp):
            left = self._expr_to_sql(node.left, params)
            right = self._expr_to_sql(node.right, params)
            return f"({left} {node.operator} {right})"
        return "NULL"

    # ---- Helpers ----

    def _extract_fields(self, params: list) -> list[str]:
        for p in params:
            if isinstance(p, FieldsParam):
                return list(p.names)
            if isinstance(p, FieldParam):
                return [p.name]
        return []

    def _extract_where(
        self, params: list
    ) -> tuple[str, list[Any]]:
        for p in params:
            if isinstance(p, WhereParam):
                return self._build_condition(p.condition)
        return "", []

    def _map_operator(self, op: str) -> str:
        return {"=": "=", "==": "=", "!=": "!=",
                ">": ">", "<": "<", ">=": ">=",
                "<=": "<="}.get(op, op)

    def _quote_identifier(self, name: str) -> str:
        # Double-quote PostgreSQL identifiers to handle reserved words
        return f'"{name}"'

    def _eval_literal(self, node: Any) -> Any:
        if isinstance(node, (IntegerLiteral, FloatLiteral,
                              StringLiteral, BoolLiteral)):
            return node.value
        if isinstance(node, NullLiteral):
            return None
        return str(node)