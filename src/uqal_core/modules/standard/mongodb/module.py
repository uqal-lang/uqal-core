"""
MongoDB UQAL module.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pymongo
import pymongo.errors

from uqal_core.execution.result_set import ResultSet
from uqal_core.module_interface import (
    CapabilityManifest,
    ModuleManifest,
    UQALModule,
)
from uqal_core.modules.standard.mongodb.capabilities import (
    MONGODB_CAPABILITIES,
)
from uqal_core.modules.standard.mongodb.connection_schema import (
    MongoDBConnectionSchema,
)
from uqal_core.modules.standard.mongodb import native_validator
from uqal_core.modules.standard.mongodb.schema_sync import (
    sync_full_schema,
)
from uqal_core.modules.standard.mongodb.translator import (
    MongoDBTranslator,
)
from uqal_core.modules.standard.mongodb.type_mapping import CORE_TO_BSON
from uqal_core.config.connection_schema import ConnectionSchema
from uqal_core.schema.schema_store import SchemaStore


class MongoDBModule(UQALModule):
    """Full UQALModule implementation for MongoDB."""

    def __init__(self) -> None:
        self._schema_store = SchemaStore()
        self._translator = MongoDBTranslator()

    # ---- 1. Identity ----

    def get_manifest(self) -> ModuleManifest:
        return ModuleManifest(
            name="standard.mongodb",
            version="0.1.0",
            requires=[],
        )

    def get_grammar_extension(self) -> str:
        ext_file = Path(__file__).parent / "grammar_extension.lark"
        if ext_file.exists():
            return ext_file.read_text(encoding="utf-8")
        return ""

    def get_capabilities(self) -> CapabilityManifest:
        return MONGODB_CAPABILITIES

    def get_type_mapping(self) -> dict[str, Any]:
        return dict(CORE_TO_BSON)

    def get_native_command_name(self) -> str:
        return "mongo"

    def get_connection_schema(self) -> type[ConnectionSchema]:
        return MongoDBConnectionSchema

    def get_cache_thresholds(self) -> dict[str, float] | None:
        return {
            "never":       0.0,
            "memory":      2.0,
            "disk_long":   8.0,
            "disk_medium": 25.0,
        }

    # ---- 2. Connection ----

    def build_connection(self, config: Any) -> Any:
        options = config.options or {}

        conn_string = options.get("connection_string")
        if conn_string:
            client = pymongo.MongoClient(
                conn_string,
                serverSelectionTimeoutMS=options.get(
                    "connect_timeout_ms", 10000
                ),
            )
        else:
            kwargs: dict[str, Any] = {
                "host": config.host or "localhost",
                "port": config.port or 27017,
                "serverSelectionTimeoutMS": options.get(
                    "connect_timeout_ms", 10000
                ),
            }
            user = options.get("user")
            password = options.get("password")
            if user and password:
                kwargs["username"] = user
                kwargs["password"] = password
                kwargs["authSource"] = options.get(
                    "auth_source", "admin"
                )
            if options.get("tls"):
                kwargs["tls"] = True

            client = pymongo.MongoClient(**kwargs)

        # Verify connection
        client.admin.command("ping")

        # Store database name for later use
        client._uqal_database = config.database or "test"
        return client

    # ---- 3. Translation + Execution ----

    def translate(self, ast_subtree: Any) -> Any:
        return self._translator.translate(ast_subtree)

    def execute(
        self, native_query: Any, connection: Any
    ) -> ResultSet:
        if isinstance(native_query, str):
            return self.execute_native(native_query, connection)
        return self._run_query(native_query, connection)

    def _run_query(
        self, query_dict: dict, connection: Any
    ) -> ResultSet:
        db_name = connection._uqal_database
        db = connection[db_name]
        collection_name = query_dict["collection"]
        command = query_dict["command"]
        collection = db[collection_name]

        if command == "find":
            cursor = collection.find(
                query_dict.get("filter", {}),
                query_dict.get("projection") or None,
            )
            rows = [self._serialize_doc(doc) for doc in cursor]
            return ResultSet(
                rows=rows,
                source_module="standard.mongodb",
            )

        if command == "find_one":
            doc = collection.find_one(
                query_dict.get("filter", {}),
                query_dict.get("projection") or None,
            )
            if doc is None:
                return ResultSet(
                    rows=[],
                    source_module="standard.mongodb",
                )
            doc = self._serialize_doc(doc)
            field = query_dict.get("field")
            if field and field in doc:
                return ResultSet.single_value(
                    doc[field], field, "standard.mongodb"
                )
            return ResultSet(
                rows=[doc],
                source_module="standard.mongodb",
            )

        if command == "insert_one":
            result = collection.insert_one(query_dict["document"])
            return ResultSet(
                rows=[{"inserted_id": str(result.inserted_id)}],
                source_module="standard.mongodb",
            )

        if command == "update_one":
            result = collection.update_one(
                query_dict["filter"],
                query_dict["update"],
            )
            return ResultSet(
                rows=[{"modified_count": result.modified_count}],
                source_module="standard.mongodb",
            )

        if command == "delete_one":
            result = collection.delete_one(query_dict["filter"])
            return ResultSet(
                rows=[{"deleted_count": result.deleted_count}],
                source_module="standard.mongodb",
            )

        if command == "create_collection":
            try:
                db.create_collection(
                    query_dict["collection"],
                    validator=query_dict.get("validator"),
                )
                return ResultSet(
                    rows=[{"created": query_dict["collection"]}],
                    source_module="standard.mongodb",
                )
            except pymongo.errors.CollectionInvalid:
                return ResultSet(
                    rows=[{"exists": query_dict["collection"]}],
                    source_module="standard.mongodb",
                )

        raise NotImplementedError(
            f"Unknown MongoDB command: {command}"
        )

    def execute_native(
        self, query: str, connection: Any
    ) -> ResultSet:
        errors = native_validator.validate(query)
        if errors:
            raise ValueError(
                f"Native query validation failed: {errors}"
            )
        try:
            query_dict = json.loads(query)
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON query: {e}")

        db_name = connection._uqal_database
        db = connection[db_name]

        if "find" in query_dict:
            collection_name = query_dict.pop("find")
            collection = db[collection_name]
            filter_dict = query_dict.get("filter", {})
            projection = query_dict.get("projection")
            cursor = collection.find(filter_dict, projection)
            rows = [self._serialize_doc(doc) for doc in cursor]
            return ResultSet(
                rows=rows,
                source_module="standard.mongodb",
            )

        result = db.command(query_dict)
        return ResultSet(
            rows=[self._serialize_doc(result)],
            source_module="standard.mongodb",
        )

    def validate_native_query(self, query: str) -> list[str]:
        return native_validator.validate(query)

    # ---- 4. Schema ----

    def get_schema_store(self) -> SchemaStore:
        return self._schema_store

    def sync_schema_from_source(self, connection: Any) -> SchemaStore:
        db_name = connection._uqal_database
        sample_size = 100
        self._schema_store = sync_full_schema(
            connection, db_name, sample_size
        )
        return self._schema_store

    def load_cached_schema(
        self, connection_name: str
    ) -> SchemaStore | None:
        try:
            from uqal_core.cache.cache_manager import CacheManager
            return CacheManager().load(connection_name)
        except Exception:
            return None

    def save_schema_cache(
        self, connection_name: str, schema: SchemaStore
    ) -> None:
        try:
            from uqal_core.cache.cache_manager import CacheManager
            CacheManager().save(
                connection_name, schema, "standard.mongodb"
            )
        except Exception:
            pass

    # ---- Helpers ----

    def _serialize_doc(self, doc: dict) -> dict:
        """Converts MongoDB types to JSON-serializable values."""
        result = {}
        for key, value in doc.items():
            type_name = type(value).__name__
            if type_name in ("ObjectId", "Decimal128", "Binary"):
                result[key] = str(value)
            elif isinstance(value, dict):
                result[key] = self._serialize_doc(value)
            elif isinstance(value, list):
                result[key] = [
                    self._serialize_doc(v) if isinstance(v, dict)
                    else str(v) if type(v).__name__ == "ObjectId"
                    else v
                    for v in value
                ]
            else:
                result[key] = value
        return result
    
    def create_view(
        self,
        view_name: str,
        aliases: list,
        returns: Any,
        connection: Any,
    ) -> str:
        """
        Creates a MongoDB view via aggregation pipeline.

        let o = table orders where status = "open"
        let u = table users where u.id = o.user_id
        return o.id, o.status, u.name

        →

        db.createView("view_name", "orders", [
            { $match: { status: "open" } },
            { $lookup: {
                from: "users",
                localField: "user_id",
                foreignField: "id",
                as: "u"
            }},
            { $unwind: "$u" },
            { $project: {
                id: "$id",
                status: "$status",
                name: "$u.name"
            }}
        ])
        """
        from uqal_core.modules.standard.mongodb.translator import (
            MongoDBTranslator,
        )

        translator = MongoDBTranslator()
        db_name = connection._uqal_database
        db = connection[db_name]

        if not aliases:
            raise ValueError("create_view requires at least one table alias.")

        # Primary collection
        primary = aliases[0]
        source_collection = primary.table
        pipeline = []

        # $match from primary WHERE condition
        if primary.condition:
            filter_dict = translator._build_filter(primary.condition)
            if filter_dict:
                pipeline.append({"$match": filter_dict})

        # $lookup + $unwind for each additional alias (JOIN equivalent)
        for alias in aliases[1:]:
            lookup = {
                "$lookup": {
                    "from": alias.table,
                    "as":   alias.alias,
                }
            }

            # Try to extract join condition fields
            # e.g. where u.id = o.user_id → localField: user_id, foreignField: id
            if alias.condition:
                local, foreign = self._extract_join_fields(
                    alias.condition, alias.alias, primary.alias
                )
                if local and foreign:
                    lookup["$lookup"]["localField"]   = local
                    lookup["$lookup"]["foreignField"] = foreign
                else:
                    # Fallback: no field hint — use pipeline lookup
                    filter_dict = translator._build_filter(
                        alias.condition
                    )
                    lookup["$lookup"]["pipeline"] = [
                        {"$match": {"$expr": filter_dict}}
                    ]

            pipeline.append(lookup)

            # $unwind to flatten the joined array into single documents
            pipeline.append({
                "$unwind": {
                    "path": f"${alias.alias}",
                    "preserveNullAndEmptyArrays": True,
                }
            })

            # $match from alias WHERE condition (after lookup)
            if alias.condition:
                filter_dict = translator._build_filter(alias.condition)
                if filter_dict:
                    pipeline.append({"$match": filter_dict})

        # $project for return fields
        projection = self._build_view_projection(
            returns, aliases, primary.alias
        )
        if projection:
            pipeline.append({"$project": projection})

        # Drop existing view if it exists
        try:
            if view_name in db.list_collection_names():
                db[view_name].drop()
        except Exception:
            pass

        # Create the view
        db.create_collection(
            view_name,
            viewOn=source_collection,
            pipeline=pipeline,
        )

        return view_name

    def _extract_join_fields(
        self,
        condition: Any,
        join_alias: str,
        primary_alias: str,
    ) -> tuple[str | None, str | None]:
        """
        Extracts localField and foreignField from a join condition.

        e.g. where u.id = o.user_id
        join_alias = "u", primary_alias = "o"
        → foreignField = "id" (from u), localField = "user_id" (from o)
        """
        from uqal_core.ast.nodes import Compare, VariableRef

        if not isinstance(condition, Compare):
            return None, None

        left = condition.left
        right = condition.right

        if not (isinstance(left, VariableRef) and isinstance(right, VariableRef)):
            return None, None

        left_parts = [str(p) for p in left.parts if isinstance(p, str)]
        right_parts = [str(p) for p in right.parts if isinstance(p, str)]

        if len(left_parts) < 2 or len(right_parts) < 2:
            return None, None

        left_alias, left_field = left_parts[0], left_parts[1]
        right_alias, right_field = right_parts[0], right_parts[1]

        # join_alias.field = primary_alias.field
        if left_alias == join_alias and right_alias == primary_alias:
            return right_field, left_field  # localField, foreignField
        if left_alias == primary_alias and right_alias == join_alias:
            return left_field, right_field
        return None, None

    def _build_view_projection(
        self,
        returns: Any,
        aliases: list,
        primary_alias: str,
    ) -> dict:
        """
        Builds a MongoDB $project stage from return fields.

        e.g. return o.id, o.status, u.name
        primary_alias = "o"
        →
        {
            "id":     "$id",         ← from primary
            "status": "$status",     ← from primary
            "name":   "$u.name",     ← from joined alias
            "_id":    0              ← suppress default _id
        }
        """
        from uqal_core.ast.nodes import AliasedPrefixedField

        projection = {"_id": 0}
        seen_names: dict[str, int] = {}

        for rf in returns.fields:
            if isinstance(rf, AliasedPrefixedField):
                # Manual alias: e.name AS emp_name
                if rf.prefix == primary_alias:
                    projection[rf.alias] = f"${rf.name}"
                else:
                    projection[rf.alias] = f"${rf.prefix}.{rf.name}"

            elif hasattr(rf, "prefix"):
                field_name = rf.name
                output_name = field_name

                # Auto-alias for duplicates using table name
                if field_name in seen_names:
                    table_name = next(
                        (a.table for a in aliases if a.alias == rf.prefix),
                        rf.prefix,
                    )
                    output_name = f"{table_name}_{field_name}"

                seen_names[field_name] = seen_names.get(field_name, 0) + 1

                if rf.prefix == primary_alias:
                    projection[output_name] = f"${rf.name}"
                else:
                    projection[output_name] = f"${rf.prefix}.{rf.name}"

            else:
                projection[rf.name] = f"${rf.name}"
                seen_names[rf.name] = seen_names.get(rf.name, 0) + 1

        return projection