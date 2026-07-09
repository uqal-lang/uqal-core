"""Neo4j module capabilities."""

from __future__ import annotations

from uqal_core.module_interface import CapabilityManifest
from uqal_core.modules.standard.neo4j.type_mapping import MODULE_TYPES

NEO4J_CAPABILITIES = CapabilityManifest(
    module_name="standard.neo4j",
    table_commands={},
    expression_extensions={},
    provided_types=list(MODULE_TYPES.keys()),
    grammar_extensions={
        "table_command":      [],
        "connection_command": ["neo4j_cypher"],
        "condition":          ["neo4j_rel_traversal"],  # neu
        "param":              [],
    },
    translatable_nodes=[
        "DbTableCall",
        "DbWriteCall",
        "DbQueryBlock",
        "DbConnectionCall",
    ],
)