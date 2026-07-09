"""
Dummy module connection schema.

Minimal schema for testing - no real connection needed.
"""

from __future__ import annotations

from uqal_core.config.connection_schema import ConnectionField, ConnectionSchema


class DummyConnectionSchema(ConnectionSchema):
    extends = None
    fields = [
        ConnectionField(
            name="host",
            type="string",
            secret=False,
            required=False,
            default="localhost",
            description="Dummy host (not actually used)",
        ),
        ConnectionField(
            name="token",
            type="string",
            secret=True,
            required=False,
            description="Optional dummy token (stored in .env)",
        ),
    ]