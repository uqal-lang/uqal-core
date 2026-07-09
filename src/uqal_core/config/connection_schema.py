"""
Connection schema definition.

Every module declares what connection parameters it needs via a
ConnectionSchema subclass. This drives both the interactive
add-connection prompts and the flag-based scripting mode.

The Core defines the structure, modules provide the content.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ConnectionField:
    """
    A single parameter in a connection schema.

    secret=True  → stored in .env as UQAL_<NAME>_<KEY>
    secret=False → stored in uqal_config.json

    required_if allows conditional required fields:
        ConnectionField("ssl_cert", "string", secret=True,
                        required=False, required_if="use_ssl")
    means ssl_cert is required only when use_ssl=True.
    """

    name: str
    type: str                    # "string" | "integer" | "boolean"
    secret: bool
    required: bool
    default: Any = None
    description: str = ""
    required_if: str | None = None

    def is_required_given(self, values: dict[str, Any]) -> bool:
        """
        Returns True if this field is required given the current
        values of other fields (handles required_if logic).
        """
        if not self.required and self.required_if is None:
            return False
        if self.required and self.required_if is None:
            return True
        # Conditional: required only if required_if field is truthy
        return bool(values.get(self.required_if))

    def cast(self, raw: str) -> Any:
        """Casts a raw string input to the declared type."""
        if self.type == "integer":
            return int(raw)
        if self.type == "boolean":
            return raw.lower() in ("true", "yes", "1")
        return raw


class ConnectionSchema:
    """
    Base class for all module connection schemas.

    Subclass this in your module and set fields + optionally extends.

    Example:
        class PostgreSQLConnectionSchema(ConnectionSchema):
            extends = None
            fields = [
                ConnectionField("host", "string", secret=False,
                                required=True, description="DB host"),
                ConnectionField("password", "string", secret=True,
                                required=True),
            ]
    """

    extends: str | None = None
    fields: list[ConnectionField] = field(default_factory=list)

    @classmethod
    def all_fields(cls) -> list[ConnectionField]:
        """
        Returns all fields including inherited ones from extends.
        Own fields take priority over inherited fields with the same name.
        """
        return list(cls.fields)

    @classmethod
    def secret_fields(cls) -> list[ConnectionField]:
        return [f for f in cls.all_fields() if f.secret]

    @classmethod
    def config_fields(cls) -> list[ConnectionField]:
        return [f for f in cls.all_fields() if not f.secret]

    @classmethod
    def validate(cls, values: dict[str, Any]) -> list[str]:
        """
        Validates a set of values against this schema.
        Returns a list of error strings - empty means valid.
        """
        errors = []
        for field_def in cls.all_fields():
            if field_def.is_required_given(values):
                if field_def.name not in values or values[field_def.name] is None:
                    errors.append(
                        f"Required field '{field_def.name}' is missing."
                        + (
                            f" ({field_def.description})"
                            if field_def.description
                            else ""
                        )
                    )
        return errors