"""MongoDB module capabilities."""

from __future__ import annotations

from uqal_core.module_interface import CapabilityManifest
from uqal_core.modules.standard.mongodb.type_mapping import MODULE_TYPES

MONGODB_CAPABILITIES = CapabilityManifest(
    module_name="standard.mongodb",
    table_commands={},
    expression_extensions={},
    provided_types=list(MODULE_TYPES.keys()),
    grammar_extensions={
        "table_command":      [],
        "connection_command": ["mongodb_mongo"],
        "condition":          [],
        "param":              [],
    },
    translatable_nodes=[
        "DbTableCall",
        "DbWriteCall",
        "DbConnectionCall",
    ],
)