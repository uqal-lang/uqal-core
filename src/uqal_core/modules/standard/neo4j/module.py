"""
Neo4j UQAL module.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from neo4j import GraphDatabase
from lark import Token

from uqal_core.execution.result_set import ResultSet
from uqal_core.module_interface import (
    CapabilityManifest,
    ModuleManifest,
    UQALModule,
)
from uqal_core.ast.nodes import RelationshipTraversal
from uqal_core.ast.module_nodes import register_node_handler
from uqal_core.modules.standard.neo4j.capabilities import (
    NEO4J_CAPABILITIES,
)
from uqal_core.modules.standard.neo4j.connection_schema import (
    Neo4jConnectionSchema,
)
from uqal_core.modules.standard.neo4j import native_validator
from uqal_core.modules.standard.neo4j.schema_sync import (
    sync_full_schema,
)
from uqal_core.modules.standard.neo4j.translator import (
    Neo4jTranslator,
)
from uqal_core.modules.standard.neo4j.type_mapping import CORE_TO_NEO4J
from uqal_core.config.connection_schema import ConnectionSchema
from uqal_core.schema.schema_store import SchemaStore


class Neo4jModule(UQALModule):
    """Full UQALModule implementation for Neo4j."""

    def __init__(self) -> None:
        self._schema_store = SchemaStore()
        self._translator = Neo4jTranslator()

    # ---- 1. Identity ----

    def get_manifest(self) -> ModuleManifest:
        return ModuleManifest(
            name="standard.neo4j",
            version="0.1.0",
            requires=[],
        )

    def get_grammar_extension(self) -> str:
        ext_file = Path(__file__).parent / "grammar_extension.lark"
        if ext_file.exists():
            return ext_file.read_text(encoding="utf-8")
        return ""

    def get_capabilities(self) -> CapabilityManifest:
        return NEO4J_CAPABILITIES

    def get_type_mapping(self) -> dict[str, Any]:
        return dict(CORE_TO_NEO4J)

    def get_native_command_name(self) -> str:
        return "cypher"

    def get_connection_schema(self) -> type[ConnectionSchema]:
        return Neo4jConnectionSchema

    # ---- 2. Connection ----

    def build_connection(self, config: Any) -> Any:
        options = config.options or {}

        uri = options.get("uri")
        if not uri:
            host = config.host or "localhost"
            port = config.port or 7687
            uri = f"bolt://{host}:{port}"

        user = options.get("user", "neo4j")
        password = options.get("password", "")
        timeout = config.options.get("connect_timeout", 10)

        driver = GraphDatabase.driver(
            uri,
            auth=(user, password),
            connection_timeout=timeout,
        )

        # Verify connection
        driver.verify_connectivity()

        # Store database name for later use
        driver._uqal_database = config.database or "neo4j"
        return driver

    # ---- 3. Translation + Execution ----

    def translate(self, ast_subtree: Any) -> Any:
        return self._translator.translate(ast_subtree)

    def execute(
        self, native_query: Any, connection: Any
    ) -> ResultSet:
        if isinstance(native_query, str):
            return self.execute_native(native_query, connection)

        cypher, params = native_query
        return self._run_cypher(cypher, params, connection)

    def _run_cypher(
        self,
        cypher: str,
        params: dict,
        connection: Any,
    ) -> ResultSet:
        database = getattr(
            connection, "_uqal_database", "neo4j"
        )

        with connection.session(database=database) as session:
            result = session.run(cypher, params)
            records = list(result)

            if not records:
                return ResultSet(
                    rows=[],
                    source_module="standard.neo4j",
                )

            # Convert Neo4j records to plain dicts
            rows = []
            for record in records:
                row = {}
                for key in record.keys():
                    value = record[key]
                    row[key] = self._serialize_value(value)
                rows.append(row)

            return ResultSet(
                rows=rows,
                source_module="standard.neo4j",
            )

    def execute_native(
        self, query: str, connection: Any
    ) -> ResultSet:
        database = getattr(
            connection, "_uqal_database", "neo4j"
        )

        with connection.session(database=database) as session:
            errors = native_validator.validate(query, session)
            if errors:
                raise ValueError(
                    f"Native query validation failed: {errors}"
                )

        return self._run_cypher(query, {}, connection)

    def validate_native_query(self, query: str) -> list[str]:
        return native_validator.security_check(query)

    # ---- 4. Schema ----

    def get_schema_store(self) -> SchemaStore:
        return self._schema_store

    def sync_schema_from_source(self, connection: Any) -> SchemaStore:
        database = getattr(
            connection, "_uqal_database", "neo4j"
        )
        self._schema_store = sync_full_schema(
            connection, database
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
                connection_name, schema, "standard.neo4j"
            )
        except Exception:
            pass

    def create_view(
        self,
        view_name: str,
        aliases: list,
        returns: Any,
        connection: Any,
    ) -> str:
        """
        Neo4j does not have native views.
        We store the query as a named Cypher snippet in metadata.
        For now this is a no-op placeholder.
        """
        raise NotImplementedError(
            "Neo4j does not support views natively. "
            "Use neo4j.cypher() for complex queries or "
            "save them as UQAL scripts."
        )

    # ---- Helpers ----

    def _serialize_value(self, value: Any) -> Any:
        """Converts Neo4j driver types to Python native types."""
        if value is None:
            return None

        type_name = type(value).__name__

        # Neo4j Node → dict of properties
        if type_name == "Node":
            return dict(value)

        # Neo4j Relationship → dict of properties
        if type_name == "Relationship":
            return dict(value)

        # Neo4j Date/DateTime → ISO string
        if hasattr(value, "iso_format"):
            return value.iso_format()

        # Neo4j Integer → Python int
        if type_name in ("Integer", "Long"):
            return int(value)

        # Neo4j Float/Double → Python float
        if type_name in ("Float", "Double"):
            return float(value)

        # List → recurse
        if isinstance(value, list):
            return [self._serialize_value(v) for v in value]

        # Dict → recurse
        if isinstance(value, dict):
            return {
                k: self._serialize_value(v)
                for k, v in value.items()
            }

        return value
    
    def _handle_neo4j_rel_traversal(children: list) -> RelationshipTraversal:
        token_children = [str(c) for c in children if isinstance(c, Token)]

        if len(token_children) < 3:
            return children

        source_alias = token_children[0]
        relationship_type = token_children[1]
        target_alias = token_children[-1]

        # Everything between relationship_type and target_alias
        # are the property names (empty if simple form: NAME NAME NAME)
        properties = token_children[2:-1]

        return RelationshipTraversal(
            source_alias=source_alias,
            relationship_type=relationship_type,
            target_alias=target_alias,
            properties=properties,
        )
    register_node_handler("neo4j_rel_traversal", _handle_neo4j_rel_traversal)