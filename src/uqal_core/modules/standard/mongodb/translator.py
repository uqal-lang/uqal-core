"""
MongoDB AST translator.

Converts UQAL AST nodes into pymongo operation dicts.
"""

from __future__ import annotations

from typing import Any

from uqal_core.ast.nodes import (
    BoolLiteral,
    Compare,
    CoreTypeRef,
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
    SchemaDefinition,
    StringLiteral,
    VariableRef,
    WhereParam,
)
from uqal_core.modules.standard.mongodb.type_mapping import CORE_TO_BSON


class MongoDBTranslator:

    def translate(self, node: Any) -> dict:
        if isinstance(node, DbTableCall):
            return self._translate_table_call(node)
        if isinstance(node, DbWriteCall):
            return self._translate_write_call(node)
        raise NotImplementedError(
            f"MongoDBTranslator cannot translate '{type(node).__name__}'"
        )

    def _translate_table_call(self, node: DbTableCall) -> dict:
        collection = node.table
        filter_dict = self._extract_filter(node.params)
        projection = self._extract_projection(node.params)

        if node.command == "get_value":
            field_names = list(projection.keys()) if projection else []
            return {
                "command":    "find_one",
                "collection": collection,
                "filter":     filter_dict,
                "projection": projection,
                "field":      field_names[0] if field_names else None,
            }

        if node.command == "get_row":
            return {
                "command":    "find_one",
                "collection": collection,
                "filter":     filter_dict,
                "projection": projection,
            }

        return {
            "command":    "find",
            "collection": collection,
            "filter":     filter_dict,
            "projection": projection,
        }

    def _translate_write_call(self, node: DbWriteCall) -> dict:
        if node.command == "insert_table":
            return self._translate_create_collection(node)
        if node.command == "insert_row":
            return self._translate_insert(node)
        if node.command == "update":
            return self._translate_update(node)
        if node.command == "delete":
            return self._translate_delete(node)
        raise NotImplementedError(
            f"Unknown write command: {node.command}"
        )

    def _translate_create_collection(self, node: DbWriteCall) -> dict:
        schema: SchemaDefinition = node.payload
        required = [f.name for f in schema.fields if f.required]
        properties = {}
        for field in schema.fields:
            if isinstance(field.type_ref, CoreTypeRef):
                bson_type = CORE_TO_BSON.get(
                    field.type_ref.name, "string"
                )
            else:
                bson_type = "string"
            properties[field.name] = {"bsonType": bson_type}

        return {
            "command":    "create_collection",
            "collection": node.table,
            "validator": {
                "$jsonSchema": {
                    "bsonType":   "object",
                    "required":   required,
                    "properties": properties,
                }
            },
        }

    def _translate_insert(self, node: DbWriteCall) -> dict:
        params = node.payload if isinstance(node.payload, list) else []
        document = {
            p.name: self._eval_literal(p.value)
            for p in params
            if isinstance(p, NameParam)
        }
        return {
            "command":    "insert_one",
            "collection": node.table,
            "document":   document,
        }

    def _translate_update(self, node: DbWriteCall) -> dict:
        params = node.payload if isinstance(node.payload, list) else []
        filter_dict = self._extract_filter(params)
        update_fields = {
            p.name: self._eval_literal(p.value)
            for p in params
            if isinstance(p, NameParam)
        }
        if not filter_dict:
            raise ValueError(
                "update requires a where clause to prevent "
                "accidental full-collection updates."
            )
        return {
            "command":    "update_one",
            "collection": node.table,
            "filter":     filter_dict,
            "update":     {"$set": update_fields},
        }

    def _translate_delete(self, node: DbWriteCall) -> dict:
        params = node.payload if isinstance(node.payload, list) else []
        filter_dict = self._extract_filter(params)
        if not filter_dict:
            raise ValueError(
                "delete requires a where clause to prevent "
                "accidental full-collection deletes."
            )
        return {
            "command":    "delete_one",
            "collection": node.table,
            "filter":     filter_dict,
        }

    def _extract_filter(self, params: list) -> dict:
        for p in params:
            if isinstance(p, WhereParam):
                return self._build_filter(p.condition)
        return {}

    def _extract_projection(self, params: list) -> dict:
        for p in params:
            if isinstance(p, FieldsParam):
                return {name: 1 for name in p.names}
            if isinstance(p, FieldParam):
                return {p.name: 1}
        return {}

    def _build_filter(self, condition: Any) -> dict:
        if isinstance(condition, Compare):
            field = self._field_name(condition.left)
            value = self._eval_literal(condition.right)
            op = condition.operator
            if op in ("=", "=="):
                return {field: value}
            if op == "!=":
                return {field: {"$ne": value}}
            if op == ">":
                return {field: {"$gt": value}}
            if op == "<":
                return {field: {"$lt": value}}
            if op == ">=":
                return {field: {"$gte": value}}
            if op == "<=":
                return {field: {"$lte": value}}

        if isinstance(condition, LogicalAnd):
            return {"$and": [
                self._build_filter(condition.left),
                self._build_filter(condition.right),
            ]}

        if isinstance(condition, LogicalOr):
            return {"$or": [
                self._build_filter(condition.left),
                self._build_filter(condition.right),
            ]}

        if isinstance(condition, LogicalNot):
            return {"$nor": [self._build_filter(condition.operand)]}

        if isinstance(condition, IsNull):
            return {self._field_name(condition.operand): {"$exists": False}}

        if isinstance(condition, IsNotNull):
            return {self._field_name(condition.operand): {"$exists": True}}

        return {}

    def _field_name(self, node: Any) -> str:
        if isinstance(node, VariableRef):
            return ".".join(
                str(p) for p in node.parts if isinstance(p, str)
            )
        return str(node)

    def _eval_literal(self, node: Any) -> Any:
        if isinstance(node, IntegerLiteral):
            return node.value
        if isinstance(node, FloatLiteral):
            return node.value
        if isinstance(node, StringLiteral):
            return node.value
        if isinstance(node, BoolLiteral):
            return node.value
        if isinstance(node, NullLiteral):
            return None
        return str(node)