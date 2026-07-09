"""Neo4j connection schema."""

from __future__ import annotations

from uqal_core.config.connection_schema import ConnectionField, ConnectionSchema


class Neo4jConnectionSchema(ConnectionSchema):
    extends = None
    fields = [
        ConnectionField(
            name="host",
            type="string",
            secret=False,
            required=False,
            default="localhost",
            description="Neo4j host (ignored if uri is set)",
        ),
        ConnectionField(
            name="port",
            type="integer",
            secret=False,
            required=False,
            default=7687,
            description="Bolt port (ignored if uri is set)",
        ),
        ConnectionField(
            name="database",
            type="string",
            secret=False,
            required=False,
            default="neo4j",
            description="Neo4j database name",
        ),
        ConnectionField(
            name="uri",
            type="string",
            secret=True,
            required=False,
            description=(
                "Full Bolt URI e.g. bolt://localhost:7687 or "
                "neo4j+s://xxx.databases.neo4j.io (AuraDB). "
                "If set, host/port are ignored."
            ),
        ),
        ConnectionField(
            name="user",
            type="string",
            secret=True,
            required=True,
            description="Neo4j user",
        ),
        ConnectionField(
            name="password",
            type="string",
            secret=True,
            required=True,
            description="Neo4j password",
        ),
        ConnectionField(
            name="connect_timeout",
            type="integer",
            secret=False,
            required=False,
            default=10,
            description="Connection timeout in seconds",
        ),
    ]