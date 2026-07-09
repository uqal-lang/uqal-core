"""
The contract every module must fulfil.

This is the single point of contact between the core and any database
backend. The core never knows anything specific about PostgreSQL,
MongoDB, Neo4j, or any other system - it only ever talks to instances
of this abstract class (see language specification, chapter 14.4).

A module - whether shipped as a "standard" module, a community module,
or a private, internal module - must implement every method below.
There is no partial implementation: the ABC enforces this at class
definition time, not at first use.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from uqal_core.execution.result_set import ResultSet
from uqal_core.schema.schema_store import SchemaStore
from uqal_core.config.connection_schema import ConnectionSchema


class CapabilityManifest:
    def __init__(
        self,
        module_name: str,
        table_commands: dict[str, dict[str, Any]] | None = None,
        expression_extensions: dict[str, dict[str, Any]] | None = None,
        provided_types: list[str] | None = None,
        grammar_extensions: dict[str, list[str]] | None = None,
        translatable_nodes: list[str] | None = None,
    ) -> None:
        self.module_name = module_name
        self.table_commands = table_commands or {}
        self.expression_extensions = expression_extensions or {}
        self.provided_types = provided_types or []
        self.grammar_extensions = grammar_extensions or {}
        self.translatable_nodes = translatable_nodes or []

    def __repr__(self) -> str:
        return (
            f"CapabilityManifest(module={self.module_name!r}, "
            f"commands={list(self.table_commands.keys())}, "
            f"types={self.provided_types})"
        )


class ModuleManifest:
    """
    Static identity and dependency information for a module, read by
    the module loader before anything else (see specification
    chapter 10 "Module dependencies").
    """

    def __init__(
        self,
        name: str,
        version: str,
        requires: list[str] | None = None,
        is_extension: bool = False,
    ) -> None:
        self.name = name
        self.version = version
        self.requires = requires or []
        self.is_extension = is_extension

    def __repr__(self) -> str:
        return (
            f"ModuleManifest(name={self.name!r}, "
            f"version={self.version!r}, "
            f"requires={self.requires})"
        )


class UQALModule(ABC):
    """
    Abstract base class every module must inherit from and fully
    implement.

    Grouped into three sections:

    1. Identity / grammar (what the module IS and contributes):
       get_manifest, get_grammar_extension, get_capabilities,
       get_type_mapping

    2. Connection (how the module CONNECTS to its database):
       build_connection

    3. Data / schema (how the module STORES and RETRIEVES data):
       translate, execute, get_schema_store, sync_schema_from_source
    """

    # ---- 1. Identity / grammar ----

    @abstractmethod
    def get_manifest(self) -> ModuleManifest:
        """
        Returns this module's identity and dependencies. Called by the
        module loader before the module is otherwise used.
        """
        ...

    @abstractmethod
    def get_grammar_extension(self) -> str:
        """
        Returns this module's grammar fragment (in lark syntax) to be
        inserted at the appropriate extension point(s) of the base
        grammar (see specification chapter 9.1). Returns an empty
        string if this module does not extend the grammar.
        """
        ...

    @abstractmethod
    def get_capabilities(self) -> CapabilityManifest:
        """
        Returns the commands, expressions, and types this module
        contributes to the language. Used by the grammar builder and
        the type checker.
        """
        ...

    @abstractmethod
    def get_type_mapping(self) -> dict[str, Any]:
        """
        Returns the translation table from core base types to this
        module's native type system, e.g.:
            {"string": "VARCHAR(255)", "integer": "INTEGER"}

        Every CoreType member must have an entry - validated by the
        module loader.
        """
        ...

    # ---- 2. Connection ----

    @abstractmethod
    def build_connection(self, config: "ConnectionConfig") -> Any:
        """
        Builds a native, live database connection from the generic
        ConnectionConfig. The module reads whatever it needs from
        config.options (auth tokens, SSL certs, driver flags, managed
        identity settings, etc.) and returns a native connection object
        (e.g. a psycopg2 connection, a neo4j.Driver instance).

        The returned object is stored back in config.native_connection
        by the registry and passed to execute() on every call - the
        core never inspects it.
        """
        ...

    @abstractmethod
    def get_connection_schema(self) -> type[ConnectionSchema]:
        """
        Returns the ConnectionSchema class (not an instance) describing
        what parameters this module needs to build a connection.

        Used by:
        - 'uqal add-connection' for interactive prompting
        - 'uqal add-connection' flag generation
        - ConfigManager for validation before saving
        """
        ...

    # ---- 3. Data / schema ----

    @abstractmethod
    def translate(self, ast_subtree: Any) -> Any:
        """
        Translates a portion of the parsed AST that the planner has
        determined belongs entirely to this module's connection into
        this module's native query representation (e.g. a SQL string,
        a Cypher string, a MongoDB query dict).

        Pure translation only - does NOT execute anything, so it can
        be unit tested without a live database connection.
        """
        ...

    @abstractmethod
    def execute(self, native_query: Any, connection: Any) -> ResultSet:
        """
        Executes an already-translated native query against a live
        connection and wraps the result into the unified ResultSet
        format (see execution/result_set.py).
        """
        ...

    @abstractmethod
    def get_schema_store(self) -> SchemaStore:
        """
        Returns the currently known schema for this module's connection.
        """
        ...

    @abstractmethod
    def sync_schema_from_source(self, connection: Any) -> SchemaStore:
        """
        Reads the actual structure from the live database and returns
        it as a freshly built SchemaStore. Called by "db1.sync_schema"
        and by "live=true" metadata queries.
        """
        ...

    @abstractmethod
    def create_view(
        self,
        view_name: str,
        aliases: list,
        returns: Any,
        connection: Any,
    ) -> str:
        """
        Creates a view in the database.
        Returns the view name on success.

        PostgreSQL: CREATE OR REPLACE VIEW ... AS SELECT ...
        MongoDB:    db.createView(name, source, pipeline)
        """
        ...