"""
Schema cache manager.

Handles reading/writing SchemaStore to disk as JSON.
Each connection gets one file: .uqal/schemas/<connection>.json

The cache includes a synced_at timestamp so the loader can decide
whether to trigger an automatic re-sync (TTL check).
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from uqal_core.schema.schema_store import (
    FieldDefinition,
    RelationshipDefinition,
    SchemaStore,
    TableDefinition,
)

_SCHEMAS_DIR = ".uqal/schemas"
_DEFAULT_TTL_HOURS = 24


class CacheManager:
    """
    Manages on-disk schema caches in .uqal/schemas/.
    """

    def __init__(self, base_dir: Path | None = None) -> None:
        self._base = base_dir or Path.cwd()
        self._schemas_dir = self._base / _SCHEMAS_DIR
        self._schemas_dir.mkdir(parents=True, exist_ok=True)

    def load(self, connection_name: str) -> SchemaStore | None:
        """
        Loads cached schema from disk.
        Returns None if not found or corrupt.
        """
        path = self._schema_path(connection_name)
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return self._deserialize(data)
        except Exception:
            return None

    def load_with_metadata(
        self, connection_name: str
    ) -> tuple[SchemaStore, dict] | None:
        """
        Loads cached schema plus raw metadata (synced_at, ttl_hours).
        Returns None if not found.
        """
        path = self._schema_path(connection_name)
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            schema = self._deserialize(data)
            metadata = {
                "synced_at": data.get("synced_at", ""),
                "ttl_hours": data.get(
                    "ttl_hours", _DEFAULT_TTL_HOURS
                ),
                "module_type": data.get("module_type", ""),
            }
            return schema, metadata
        except Exception:
            return None

    def save(
        self,
        connection_name: str,
        schema: SchemaStore,
        module_type: str = "",
        ttl_hours: int = _DEFAULT_TTL_HOURS,
    ) -> None:
        """Saves schema to disk with current timestamp."""
        path = self._schema_path(connection_name)
        data = self._serialize(
            schema, connection_name, module_type, ttl_hours
        )
        path.write_text(
            json.dumps(data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def is_expired(self, connection_name: str) -> bool:
        """
        Returns True if the cached schema is older than its TTL,
        or if no cache exists.
        """
        result = self.load_with_metadata(connection_name)
        if result is None:
            return True
        _, metadata = result
        synced_at_str = metadata.get("synced_at", "")
        ttl_hours = metadata.get("ttl_hours", _DEFAULT_TTL_HOURS)

        if not synced_at_str:
            return True

        try:
            synced_at = datetime.fromisoformat(synced_at_str)
            # Make timezone-aware if naive
            if synced_at.tzinfo is None:
                synced_at = synced_at.replace(tzinfo=timezone.utc)
            now = datetime.now(tz=timezone.utc)
            age_hours = (now - synced_at).total_seconds() / 3600
            return age_hours > ttl_hours
        except Exception:
            return True

    def clear(self, connection_name: str | None = None) -> None:
        """
        Clears cached schema files.
        No args: clears all. With name: clears only that connection.
        """
        if connection_name is None:
            for f in self._schemas_dir.glob("*.json"):
                f.unlink()
            return
        path = self._schema_path(connection_name)
        if path.exists():
            path.unlink()

    def list_cached(self) -> list[dict]:
        """
        Returns metadata for all cached connections.
        """
        result = []
        for path in sorted(self._schemas_dir.glob("*.json")):
            connection_name = path.stem
            cached = self.load_with_metadata(connection_name)
            if cached:
                _, metadata = cached
                result.append({
                    "connection": connection_name,
                    "synced_at": metadata.get("synced_at", ""),
                    "ttl_hours": metadata.get(
                        "ttl_hours", _DEFAULT_TTL_HOURS
                    ),
                    "expired": self.is_expired(connection_name),
                    "module_type": metadata.get("module_type", ""),
                })
        return result

    # ---- Serialization ----

    def _schema_path(self, connection_name: str) -> Path:
        return self._schemas_dir / f"{connection_name}.json"

    def _serialize(
        self,
        schema: SchemaStore,
        connection_name: str,
        module_type: str,
        ttl_hours: int,
    ) -> dict:
        return {
            "connection":  connection_name,
            "module_type": module_type,
            "synced_at":   datetime.now(tz=timezone.utc).isoformat(),
            "ttl_hours":   ttl_hours,
            "tables": {
                name: self._serialize_table(table)
                for name, table in schema.tables.items()
            },
        }

    def _serialize_table(self, table: TableDefinition) -> dict:
        return {
            "fields": [
                {
                    "name":          f.name,
                    "type":          f.type,
                    "primary_key":   f.primary_key,
                    "required":      f.required,
                    "default_value": f.default_value,
                }
                for f in table.fields
            ],
            "relationships": [
                {
                    "name":               r.name,
                    "target_table":       r.target_table,
                    "native_description": r.native_description,
                }
                for r in table.relationships
            ],
            "native_metadata": table.native_metadata,
        }

    def _deserialize(self, data: dict) -> SchemaStore:
        store = SchemaStore()
        for table_name, table_data in data.get("tables", {}).items():
            fields = [
                FieldDefinition(
                    name=f["name"],
                    type=f["type"],
                    primary_key=f.get("primary_key", False),
                    required=f.get("required", False),
                    default_value=f.get("default_value"),
                )
                for f in table_data.get("fields", [])
            ]
            relationships = [
                RelationshipDefinition(
                    name=r["name"],
                    target_table=r["target_table"],
                    native_description=r["native_description"],
                )
                for r in table_data.get("relationships", [])
            ]
            store.add_table(TableDefinition(
                name=table_name,
                fields=fields,
                relationships=relationships,
                native_metadata=table_data.get("native_metadata", {}),
            ))
        return store