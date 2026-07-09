"""
PostgreSQL UQAL module.

Implements the full UQALModule interface for PostgreSQL databases.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import psycopg2
import psycopg2.extras

from uqal_core.execution.result_set import ResultSet
from uqal_core.module_interface import (
    CapabilityManifest,
    ModuleManifest,
    UQALModule,
)
from uqal_core.modules.standard.postgresql.capabilities import (
    POSTGRESQL_CAPABILITIES,
)
from uqal_core.modules.standard.postgresql.complexity import (
    calculate as calc_complexity,
)
from uqal_core.modules.standard.postgresql.connection_schema import (
    PostgreSQLConnectionSchema,
)
from uqal_core.modules.standard.postgresql import native_validator
from uqal_core.modules.standard.postgresql.schema_sync import (
    sync_full_schema,
)
from uqal_core.modules.standard.postgresql.translator import (
    PostgreSQLTranslator,
)
from uqal_core.modules.standard.postgresql.type_mapping import (
    CORE_TO_NATIVE,
)
from uqal_core.config.connection_schema import ConnectionSchema
from uqal_core.schema.schema_store import SchemaStore

_CACHE_DIR = Path(".uqal") / "schemas"


class PostgreSQLModule(UQALModule):
    """
    Full UQALModule implementation for PostgreSQL.
    """

    def __init__(self) -> None:
        self._schema_store = SchemaStore()
        self._translator = PostgreSQLTranslator()

    # ---- 1. Identity / grammar ----

    def get_manifest(self) -> ModuleManifest:
        return ModuleManifest(
            name="standard.postgresql",
            version="0.1.0",
            requires=[],
        )

    def get_grammar_extension(self) -> str:
        ext_file = Path(__file__).parent / "grammar_extension.lark"
        if ext_file.exists():
            return ext_file.read_text(encoding="utf-8")
        return ""

    def get_capabilities(self) -> CapabilityManifest:
        return POSTGRESQL_CAPABILITIES

    def get_type_mapping(self) -> dict[str, Any]:
        return dict(CORE_TO_NATIVE)

    def get_native_command_name(self) -> str:
        return "sql"

    def get_connection_schema(self) -> type[ConnectionSchema]:
        return PostgreSQLConnectionSchema


    # ---- 2. Connection ----

    def build_connection(self, config: Any) -> Any:
        options = config.options or {}
        kwargs: dict[str, Any] = {
            "host":             config.host or "localhost",
            "port":             config.port or 5432,
            "dbname":           config.database or "",
            "user":             options.get("user", ""),
            "connect_timeout":  options.get("connect_timeout", 10),
            "application_name": options.get(
                "application_name", "uqal"
            ),
        }

        password = options.get("password")
        if password:
            kwargs["password"] = password

        sslmode = options.get("sslmode", "prefer")
        if sslmode and sslmode != "disable":
            kwargs["sslmode"] = sslmode
            if options.get("sslcert"):
                kwargs["sslcert"] = options["sslcert"]
            if options.get("sslkey"):
                kwargs["sslkey"] = options["sslkey"]
            if options.get("sslrootcert"):
                kwargs["sslrootcert"] = options["sslrootcert"]

        conn = psycopg2.connect(**kwargs)
        conn.autocommit = True
        return conn

    # ---- 3. Data / schema ----

    def translate(self, ast_subtree: Any) -> Any:
        return self._translator.translate(ast_subtree)

    def execute(
        self, native_query: Any, connection: Any
    ) -> ResultSet:
        if isinstance(native_query, str):
            # Native SQL string (from sql() command)
            return self._execute_native(native_query, (), connection)

        sql, params = native_query
        return self._execute_native(sql, params, connection)

    def execute_native(
        self, query: str, connection: Any
    ) -> ResultSet:
        errors = native_validator.validate(query, connection)
        if errors:
            raise ValueError(
                f"Native query validation failed: {errors}"
            )
        return self._execute_native(query, (), connection)

    def _execute_native(
        self,
        sql: str,
        params: tuple,
        connection: Any,
    ) -> ResultSet:
        cursor = connection.cursor(
            cursor_factory=psycopg2.extras.RealDictCursor
        )
        try:
            cursor.execute(sql, params)
            if cursor.description is not None:
                rows = [dict(row) for row in cursor.fetchall()]
            else:
                rows = []
            return ResultSet(
                rows=rows,
                source_module="standard.postgresql",
            )
        finally:
            cursor.close()

    def validate_native_query(self, query: str) -> list[str]:
        return native_validator.security_check(query)

    def get_schema_store(self) -> SchemaStore:
        return self._schema_store

    def sync_schema_from_source(self, connection: Any) -> SchemaStore:
        self._schema_store = sync_full_schema(connection)
        return self._schema_store
    
    def create_view(
        self,
        view_name: str,
        aliases: list,
        returns: Any,
        connection: Any,
    ) -> str:
        """
        Creates a PostgreSQL view from UQAL view body.

        let o = table orders where status = 'open'
        let u = table users where u.id = o.user_id
        return o.id, o.status, u.name

        →

        CREATE OR REPLACE VIEW view_name AS
        SELECT o.id, o.status, u.name
        FROM orders o
        JOIN users u ON u.id = o.user_id
        WHERE o.status = 'open'
        """
        sql = self._build_view_sql(view_name, aliases, returns)
        cursor = connection.cursor()
        try:
            for statement in sql.split(';'):
                statement = statement.strip()
                if statement:  # ← nur nicht-leere Statements ausführen
                    cursor.execute(statement)
            connection.commit()
        finally:
            cursor.close()
        return view_name

    def _build_view_sql(
        self, view_name: str, aliases: list, returns: Any
    ) -> str:
        from uqal_core.modules.standard.postgresql.translator import (
            PostgreSQLTranslator,
        )
        from uqal_core.ast.nodes import AliasedPrefixedField
        from collections import Counter
        import click

        translator = PostgreSQLTranslator()

        # ---- Schritt 1: Alle finalen Namen + Ursprungsnamen sammeln ----
        field_info = []
        for rf in returns.fields:
            if isinstance(rf, AliasedPrefixedField):
                field_info.append({
                    "final":  rf.alias,
                    "origin": rf.name,
                    "manual": True,
                    "rf":     rf,
                })
            elif hasattr(rf, "prefix"):
                field_info.append({
                    "final":  rf.name,
                    "origin": rf.name,
                    "manual": False,
                    "rf":     rf,
                })
            else:
                field_info.append({
                    "final":  rf.name,
                    "origin": rf.name,
                    "manual": False,
                    "rf":     rf,
                })

        # Duplikate in finalen Namen
        final_counts = Counter(f["final"] for f in field_info)
        final_duplicates = {
            name for name, count in final_counts.items() if count > 1
        }

        # Ursprungsnamen die mehrfach vorkommen
        origin_counts = Counter(f["origin"] for f in field_info)
        origin_duplicates = {
            name for name, count in origin_counts.items() if count > 1
        }

        # Warnings: gleicher Ursprung aber teilweise manuell umbenannt
        for origin in origin_duplicates:
            fields_with_origin = [
                f for f in field_info if f["origin"] == origin
            ]
            manual = [f for f in fields_with_origin if f["manual"]]
            if manual:
                table_names = []
                for f in fields_with_origin:
                    rf = f["rf"]
                    if hasattr(rf, "prefix"):
                        table_name = next(
                            (
                                a.table for a in aliases
                                if a.alias == rf.prefix
                            ),
                            rf.prefix,
                        )
                        table_names.append(f"'{table_name}.{origin}'")
                manual_aliases = [f["final"] for f in manual]
                click.echo(
                    click.style(
                        f"  ⚠ Warning: {', '.join(table_names)} share "
                        f"origin name '{origin}'. "
                        f"Manual alias(es) {manual_aliases} applied.",
                        fg="yellow",
                    )
                )

        # ---- Schritt 2: SQL-Felder generieren ----
        return_fields = []
        for info in field_info:
            rf = info["rf"]

            if isinstance(rf, AliasedPrefixedField):
                # Manueller Alias — immer respektieren
                col = f'"{rf.prefix}"."{rf.name}" AS "{rf.alias}"'

            elif hasattr(rf, "prefix"):
                field_name = rf.name
                if field_name in final_duplicates:
                    # Duplikat → Tabellennamen voranstellen
                    table_name = next(
                        (
                            a.table for a in aliases
                            if a.alias == rf.prefix
                        ),
                        rf.prefix,
                    )
                    auto_alias = f"{table_name}_{field_name}"
                    col = (
                        f'"{rf.prefix}"."{rf.name}" AS "{auto_alias}"'
                    )
                else:
                    col = f'"{rf.prefix}"."{rf.name}"'

            else:
                col = f'"{rf.name}"'

            return_fields.append(col)

        field_sql = ", ".join(return_fields)

        # ---- FROM clause ----
        primary = aliases[0]
        from_clause = f'"{primary.table}" "{primary.alias}"'

        # ---- JOIN clauses ----
        join_parts = []
        for alias in aliases[1:]:
            t = f'"{alias.table}" "{alias.alias}"'
            if alias.condition:
                cond_sql, _ = translator._build_condition(alias.condition)
                join_parts.append(f"JOIN {t} ON {cond_sql}")
            else:
                join_parts.append(f"CROSS JOIN {t}")

        # ---- WHERE from primary condition ----
        where_parts = []
        if primary.condition:
            cond_sql, _ = translator._build_condition(primary.condition)
            where_parts.append(cond_sql)

        # ---- Assemble ----
        drop_sql = f'DROP VIEW IF EXISTS "{view_name}"'
        create_sql = f'CREATE VIEW "{view_name}" AS\n'
        create_sql += f"SELECT {field_sql}\n"
        create_sql += f"FROM {from_clause}\n"
        if join_parts:
            create_sql += "\n".join(join_parts) + "\n"
        if where_parts:
            create_sql += f"WHERE {' AND '.join(where_parts)}\n"

        return f"{drop_sql};\n{create_sql}"
    
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
                connection_name, schema, "standard.postgresql"
            )
        except Exception:
            pass