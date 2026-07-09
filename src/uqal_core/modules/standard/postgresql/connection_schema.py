"""
PostgreSQL connection schema.

Defines all parameters needed to connect to a PostgreSQL instance,
including standard fields (stored in uqal_config.json) and secrets
(stored in .env).
"""

from __future__ import annotations

from uqal_core.config.connection_schema import ConnectionField, ConnectionSchema


class PostgreSQLConnectionSchema(ConnectionSchema):
    extends = None
    fields = [
        ConnectionField(
            name="host",
            type="string",
            secret=False,
            required=True,
            description="Database host (e.g. localhost or db.example.com)",
        ),
        ConnectionField(
            name="port",
            type="integer",
            secret=False,
            required=False,
            default=5432,
            description="Database port",
        ),
        ConnectionField(
            name="database",
            type="string",
            secret=False,
            required=True,
            description="Database name",
        ),
        ConnectionField(
            name="user",
            type="string",
            secret=True,
            required=True,
            description="Database user",
        ),
        ConnectionField(
            name="password",
            type="string",
            secret=True,
            required=False,
            description="Database password (omit for Managed Identity)",
        ),
        ConnectionField(
            name="sslmode",
            type="string",
            secret=False,
            required=False,
            default="prefer",
            description="SSL mode: disable/allow/prefer/require/verify-full",
        ),
        ConnectionField(
            name="sslcert",
            type="string",
            secret=True,
            required=False,
            description="Path to client SSL certificate",
        ),
        ConnectionField(
            name="sslkey",
            type="string",
            secret=True,
            required=False,
            description="Path to client SSL key",
        ),
        ConnectionField(
            name="sslrootcert",
            type="string",
            secret=True,
            required=False,
            description="Path to SSL root certificate",
        ),
        ConnectionField(
            name="connect_timeout",
            type="integer",
            secret=False,
            required=False,
            default=10,
            description="Connection timeout in seconds",
        ),
        ConnectionField(
            name="application_name",
            type="string",
            secret=False,
            required=False,
            default="uqal",
            description="Application name shown in pg_stat_activity",
        ),
    ]