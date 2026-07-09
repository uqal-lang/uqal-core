"""
MongoDB connection schema.
"""

from __future__ import annotations

from uqal_core.config.connection_schema import ConnectionField, ConnectionSchema


class MongoDBConnectionSchema(ConnectionSchema):
    extends = None
    fields = [
        ConnectionField(
            name="host",
            type="string",
            secret=False,
            required=False,
            default="localhost",
            description="MongoDB host (ignored if connection_string is set)",
        ),
        ConnectionField(
            name="port",
            type="integer",
            secret=False,
            required=False,
            default=27017,
            description="MongoDB port (ignored if connection_string is set)",
        ),
        ConnectionField(
            name="database",
            type="string",
            secret=False,
            required=True,
            description="Database name",
        ),
        ConnectionField(
            name="connection_string",
            type="string",
            secret=True,
            required=False,
            description=(
                "Full MongoDB connection string "
                "(e.g. mongodb+srv://user:pass@cluster.mongodb.net/db). "
                "If set, host/port/user/password are ignored."
            ),
        ),
        ConnectionField(
            name="user",
            type="string",
            secret=True,
            required=False,
            description="MongoDB user (not needed with connection_string)",
        ),
        ConnectionField(
            name="password",
            type="string",
            secret=True,
            required=False,
            description="MongoDB password (not needed with connection_string)",
        ),
        ConnectionField(
            name="auth_source",
            type="string",
            secret=False,
            required=False,
            default="admin",
            description="Authentication database",
        ),
        ConnectionField(
            name="tls",
            type="boolean",
            secret=False,
            required=False,
            default=False,
            description="Enable TLS/SSL",
        ),
        ConnectionField(
            name="connect_timeout_ms",
            type="integer",
            secret=False,
            required=False,
            default=10000,
            description="Connection timeout in milliseconds",
        ),
        ConnectionField(
            name="sample_size",
            type="integer",
            secret=False,
            required=False,
            default=100,
            description=(
                "Number of documents to sample for schema discovery "
                "when no $jsonSchema validator is defined."
            ),
        ),
    ]