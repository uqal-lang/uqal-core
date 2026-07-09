"""
PostgreSQL module capabilities.
"""

from __future__ import annotations

from uqal_core.module_interface import CapabilityManifest
from uqal_core.modules.standard.postgresql.type_mapping import (
    MODULE_TYPES,
)

POSTGRESQL_CAPABILITIES = CapabilityManifest(
    module_name="standard.postgresql",
    table_commands={},
    expression_extensions={},
    provided_types=list(MODULE_TYPES.keys()),
    grammar_extensions={
        "table_command":      [],
        "connection_command": ["postgresql_sql"],
        "condition":          [],
        "param":              [],
    },
    translatable_nodes=[
        "DbTableCall",
        "DbWriteCall",
        "DbQueryBlock",
        "DbGenericCall",
        "DbConnectionCall",
    ],
)