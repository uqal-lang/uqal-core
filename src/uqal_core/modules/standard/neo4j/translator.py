"""
Neo4j AST translator.

Converts UQAL AST nodes into Cypher queries.

Key design decisions:
  - DbTableCall → simple MATCH (n:Label) WHERE ... RETURN ...
  - DbQueryBlock → path traversal MATCH (a)-[:REL]->(b)-[:REL2]->(c)
  - Relationship syntax in query: "where a REL_TYPE b" triggers
    path traversal instead of property filter
"""

from __future__ import annotations

from typing import Any

from uqal_core.ast.nodes import (
    BoolLiteral,
    Compare,
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
    NameParam,
    NullLiteral,
    QueryAlias,
    StringLiteral,
    VariableRef,
    WhereParam,
)


class Neo4jTranslator:
    """
    Translates UQAL AST nodes to Cypher query strings.

    Returns a tuple of (cypher_string, params_dict) where
    params_dict uses $param syntax for safe parameter binding.
    """

    def translate(self, node: Any) -> tuple[str, dict]:
        if isinstance(node, DbTableCall):
            return self._translate_table_call(node)
        if isinstance(node, DbQueryBlock):
            return self._translate_query_block(node)
        if isinstance(node, DbWriteCall):
            return self._translate_write_call(node)
        raise NotImplementedError(
            f"Neo4jTranslator cannot translate '{type(node).__name__}'"
        )

    # ---- Node queries (DbTableCall) ----

    def _translate_table_call(
        self, node: DbTableCall
    ) -> tuple[str, dict]:
        label = node.table
        params: dict[str, Any] = {}

        # Extract WHERE and fields
        where_cypher, where_params = self._extract_where(
            node.params, "n", params
        )
        fields = self._extract_fields(node.params)
        params.update(where_params)

        # RETURN clause
        if fields:
            return_parts = [f"n.{f} AS {f}" for f in fields]
            return_clause = ", ".join(return_parts)
        else:
            return_clause = "n"

        cypher = f"MATCH (n:`{label}`)"
        if where_cypher:
            cypher += f" WHERE {where_cypher}"
        cypher += f" RETURN {return_clause}"

        # LIMIT for get_value and get_row
        if node.command in ("get_value", "get_row"):
            cypher += " LIMIT 1"

        return cypher, params

    # ---- Path traversal (DbQueryBlock) ----

    def _translate_query_block(
        self, node: DbQueryBlock
    ) -> tuple[str, dict]:
        params: dict[str, Any] = {}
        path_segments = []
        where_parts = []
        
        # Track which plain field names belong to which relationship variable
        rel_property_map: dict[str, str] = {}  # field_name -> rel_var

        aliases = node.aliases
        primary = aliases[0]

        path_segments.append(f"({primary.alias}:`{primary.table}`)")

        if primary.condition:
            cond, cond_params = self._build_condition(
                primary.condition, primary.alias, params
            )
            if cond:
                where_parts.append(cond)
            params.update(cond_params)

        for alias in aliases[1:]:
            rel_type, rel_props = self._detect_relationship(
                alias, [a.alias for a in aliases]
            )
            if rel_type:
                rel_var = f"r_{alias.alias}"
                if rel_props:
                    for prop in rel_props:
                        rel_property_map[prop] = rel_var
                    path_segments.append(
                        f"-[{rel_var}:`{rel_type}`]->"
                        f"({alias.alias}:`{alias.table}`)"
                    )
                else:
                    path_segments.append(
                        f"-[:`{rel_type}`]->"
                        f"({alias.alias}:`{alias.table}`)"
                    )
            else:
                where_parts.append(
                    f"({alias.alias}:`{alias.table}`)"
                )

            if alias.condition:
                prop_cond = self._extract_property_conditions(
                    alias.condition, alias.alias, params
                )
                if prop_cond:
                    where_parts.append(prop_cond)

        cypher = "MATCH " + "".join(path_segments)

        if where_parts:
            cypher += " WHERE " + " AND ".join(where_parts)

        # RETURN clause — now checks rel_property_map for plain fields
        return_parts = []
        for rf in node.returns.fields:
            if hasattr(rf, "prefix"):
                return_parts.append(
                    f"{rf.prefix}.{rf.name} AS {rf.name}"
                )
            else:
                # Plain field — check if it's a relationship property
                if rf.name in rel_property_map:
                    rel_var = rel_property_map[rf.name]
                    return_parts.append(
                        f"{rel_var}.{rf.name} AS {rf.name}"
                    )
                else:
                    return_parts.append(rf.name)

        cypher += " RETURN " + ", ".join(return_parts)

        return cypher, params

    def _detect_relationship(
        self,
        alias: QueryAlias,
        known_aliases: list[str],
    ) -> tuple[str | None, list[str]]:
        """
        Detects if an alias's WHERE condition is a RelationshipTraversal
        node (e.g. "u PLACED o" or "o CONTAINS[qty, price] p").

        Returns (relationship_type, property_names) or (None, []).
        """
        from uqal_core.ast.nodes import RelationshipTraversal

        if alias.condition is None:
            return None, []

        if isinstance(alias.condition, RelationshipTraversal):
            return (
                alias.condition.relationship_type,
                alias.condition.properties,
            )

        return None, []

    def _extract_property_conditions(
        self,
        condition: Any,
        alias: str,
        params: dict,
    ) -> str:
        """
        Extracts only property-based conditions (not relationship
        traversal patterns) from a condition node.
        """
        if isinstance(condition, Compare):
            left = condition.left
            if isinstance(left, VariableRef):
                parts = [str(p) for p in left.parts]
                # If it's a simple alias.property reference
                if len(parts) == 2 and parts[0] == alias:
                    cond, p = self._build_condition(
                        condition, alias, params
                    )
                    params.update(p)
                    return cond
            return ""

        if isinstance(condition, LogicalAnd):
            left = self._extract_property_conditions(
                condition.left, alias, params
            )
            right = self._extract_property_conditions(
                condition.right, alias, params
            )
            if left and right:
                return f"({left} AND {right})"
            return left or right

        if isinstance(condition, LogicalOr):
            left = self._extract_property_conditions(
                condition.left, alias, params
            )
            right = self._extract_property_conditions(
                condition.right, alias, params
            )
            if left and right:
                return f"({left} OR {right})"
            return left or right

        return ""

    # ---- Write commands ----

    def _translate_write_call(
        self, node: DbWriteCall
    ) -> tuple[str, dict]:
        if node.command == "insert_row":
            return self._translate_create_node(node)
        if node.command == "update":
            return self._translate_update_node(node)
        if node.command == "delete":
            return self._translate_delete_node(node)
        raise NotImplementedError(
            f"Neo4j write command not supported: {node.command}"
        )

    def _translate_create_node(
        self, node: DbWriteCall
    ) -> tuple[str, dict]:
        label = node.table
        params_list = node.payload if isinstance(
            node.payload, list
        ) else []
        props = {
            p.name: self._eval_literal(p.value)
            for p in params_list
            if isinstance(p, NameParam)
        }
        param_key = f"props_{label.lower()}"
        cypher = (
            f"CREATE (n:`{label}` ${param_key}) RETURN n"
        )
        return cypher, {param_key: props}

    def _translate_update_node(
        self, node: DbWriteCall
    ) -> tuple[str, dict]:
        label = node.table
        params_list = node.payload if isinstance(
            node.payload, list
        ) else []
        params: dict[str, Any] = {}

        where_cypher, where_params = self._extract_where(
            params_list, "n", params
        )
        params.update(where_params)

        set_parts = []
        for p in params_list:
            if isinstance(p, NameParam):
                key = f"set_{p.name}"
                set_parts.append(f"n.{p.name} = ${key}")
                params[key] = self._eval_literal(p.value)

        if not where_cypher:
            raise ValueError(
                "update requires a where clause."
            )
        if not set_parts:
            raise ValueError(
                "update requires at least one field=value."
            )

        cypher = (
            f"MATCH (n:`{label}`) WHERE {where_cypher} "
            f"SET {', '.join(set_parts)} RETURN n"
        )
        return cypher, params

    def _translate_delete_node(
        self, node: DbWriteCall
    ) -> tuple[str, dict]:
        label = node.table
        params_list = node.payload if isinstance(
            node.payload, list
        ) else []
        params: dict[str, Any] = {}

        where_cypher, where_params = self._extract_where(
            params_list, "n", params
        )
        params.update(where_params)

        if not where_cypher:
            raise ValueError(
                "delete requires a where clause."
            )

        cypher = (
            f"MATCH (n:`{label}`) WHERE {where_cypher} "
            f"DETACH DELETE n"
        )
        return cypher, params

    # ---- Condition builder ----

    def _extract_where(
        self,
        params_list: list,
        node_alias: str,
        params: dict,
    ) -> tuple[str, dict]:
        for p in params_list:
            if isinstance(p, WhereParam):
                return self._build_condition(
                    p.condition, node_alias, params
                )
        return "", {}

    def _build_condition(
        self,
        condition: Any,
        node_alias: str,
        params: dict,
    ) -> tuple[str, dict]:
        local_params: dict[str, Any] = {}

        if isinstance(condition, Compare):
            left = self._expr_to_cypher(
                condition.left, node_alias, local_params
            )
            right = self._expr_to_cypher(
                condition.right, node_alias, local_params
            )
            op = self._map_operator(condition.operator)
            return f"{left} {op} {right}", local_params

        if isinstance(condition, IsNull):
            left = self._expr_to_cypher(
                condition.operand, node_alias, local_params
            )
            return f"{left} IS NULL", local_params

        if isinstance(condition, IsNotNull):
            left = self._expr_to_cypher(
                condition.operand, node_alias, local_params
            )
            return f"{left} IS NOT NULL", local_params

        if isinstance(condition, LogicalAnd):
            left, lp = self._build_condition(
                condition.left, node_alias, params
            )
            right, rp = self._build_condition(
                condition.right, node_alias, params
            )
            local_params.update(lp)
            local_params.update(rp)
            return f"({left} AND {right})", local_params

        if isinstance(condition, LogicalOr):
            left, lp = self._build_condition(
                condition.left, node_alias, params
            )
            right, rp = self._build_condition(
                condition.right, node_alias, params
            )
            local_params.update(lp)
            local_params.update(rp)
            return f"({left} OR {right})", local_params

        if isinstance(condition, LogicalNot):
            inner, ip = self._build_condition(
                condition.operand, node_alias, params
            )
            local_params.update(ip)
            return f"NOT ({inner})", local_params

        return "true", local_params

    def _expr_to_cypher(
        self,
        node: Any,
        alias: str,
        params: dict,
    ) -> str:
        if isinstance(node, IntegerLiteral):
            key = f"p{len(params)}"
            params[key] = node.value
            return f"${key}"
        if isinstance(node, FloatLiteral):
            key = f"p{len(params)}"
            params[key] = node.value
            return f"${key}"
        if isinstance(node, StringLiteral):
            key = f"p{len(params)}"
            params[key] = node.value
            return f"${key}"
        if isinstance(node, BoolLiteral):
            return "true" if node.value else "false"
        if isinstance(node, NullLiteral):
            return "null"
        if isinstance(node, VariableRef):
            parts = [str(p) for p in node.parts
                     if isinstance(p, str)]
            if len(parts) == 1:
                return f"{alias}.{parts[0]}"
            if len(parts) == 2:
                return f"{parts[0]}.{parts[1]}"
            return ".".join(parts)
        return str(node)

    # ---- Helpers ----

    def _extract_fields(self, params: list) -> list[str]:
        for p in params:
            if isinstance(p, FieldsParam):
                return list(p.names)
            if isinstance(p, FieldParam):
                return [p.name]
        return []

    def _map_operator(self, op: str) -> str:
        return {
            "=":  "=",
            "==": "=",
            "!=": "<>",
            ">":  ">",
            "<":  "<",
            ">=": ">=",
            "<=": "<=",
        }.get(op, op)

    def _eval_literal(self, node: Any) -> Any:
        if isinstance(node, (
            IntegerLiteral, FloatLiteral,
            StringLiteral, BoolLiteral
        )):
            return node.value
        if isinstance(node, NullLiteral):
            return None
        return str(node)