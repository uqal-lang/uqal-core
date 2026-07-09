"""
Neo4j schema discovery.

Discovers:
  - Node Labels → SchemaStore tables
  - Properties per Label → FieldDefinitions
  - Relationship Types → RelationshipDefinitions
  - Relationship Properties → stored in native_metadata
"""

from __future__ import annotations

from uqal_core.schema.schema_store import (
    FieldDefinition,
    RelationshipDefinition,
    SchemaStore,
    TableDefinition,
)
from uqal_core.modules.standard.neo4j.type_mapping import (
    python_type_to_core,
)


def _discover_labels(session) -> list[str]:
    """Returns all node labels in the database."""
    result = session.run("CALL db.labels() YIELD label RETURN label")
    return [record["label"] for record in result]


def _discover_label_properties(
    session, label: str, sample_size: int = 100
) -> list[FieldDefinition]:
    """
    Discovers properties for a label by sampling nodes.
    Returns FieldDefinitions with inferred types.
    """
    result = session.run(
        f"MATCH (n:`{label}`) RETURN n LIMIT {sample_size}"
    )
    nodes = [record["n"] for record in result]

    if not nodes:
        return []

    # Collect all property names and their types
    prop_counts: dict[str, int] = {}
    prop_types: dict[str, set] = {}

    for node in nodes:
        for key, value in dict(node).items():
            prop_counts[key] = prop_counts.get(key, 0) + 1
            prop_types.setdefault(key, set()).add(
                python_type_to_core(value)
            )

    total = len(nodes)
    fields = []

    for prop_name, count in sorted(prop_counts.items()):
        types = prop_types[prop_name]
        core_type = (
            list(types)[0] if len(types) == 1 else "string"
        )
        # Required if present in >80% of sampled nodes
        required = count / total > 0.8

        fields.append(FieldDefinition(
            name=prop_name,
            type=core_type,
            primary_key=False,
            required=required,
        ))

    return fields


def _discover_relationships(session) -> list[str]:
    """Returns all relationship types."""
    result = session.run(
        "CALL db.relationshipTypes() YIELD relationshipType "
        "RETURN relationshipType"
    )
    return [record["relationshipType"] for record in result]


def _discover_relationship_schema(
    session, rel_type: str
) -> dict:
    """
    Discovers start/end labels and properties for a relationship type.
    Returns a dict with source, target, properties.
    """
    # Get source and target labels
    result = session.run(f"""
        MATCH (a)-[r:`{rel_type}`]->(b)
        RETURN DISTINCT labels(a) AS source_labels,
                        labels(b) AS target_labels,
                        keys(r)   AS rel_keys
        LIMIT 10
    """)

    records = list(result)
    if not records:
        return {
            "source": "Unknown",
            "target": "Unknown",
            "properties": [],
        }

    # Use first record as representative
    first = records[0]
    source_labels = first["source_labels"]
    target_labels = first["target_labels"]

    # Collect all property keys
    all_keys: set[str] = set()
    for record in records:
        all_keys.update(record["rel_keys"])

    # Sample properties to get types
    prop_types: dict[str, str] = {}
    if all_keys:
        result2 = session.run(f"""
            MATCH ()-[r:`{rel_type}`]->()
            RETURN r LIMIT 50
        """)
        for record in result2:
            rel = record["r"]
            for key, value in dict(rel).items():
                if key not in prop_types:
                    prop_types[key] = python_type_to_core(value)

    return {
        "source": source_labels[0] if source_labels else "Unknown",
        "target": target_labels[0] if target_labels else "Unknown",
        "properties": [
            {"name": k, "type": v}
            for k, v in prop_types.items()
        ],
    }


def sync_full_schema(
    driver,
    database: str = "neo4j",
    sample_size: int = 100,
) -> SchemaStore:
    """
    Discovers the full schema for a Neo4j database.

    Labels → tables
    Properties → fields (sampled)
    Relationships → RelationshipDefinitions with source/target/properties
    """
    store = SchemaStore()

    with driver.session(database=database) as session:
        labels = _discover_labels(session)
        rel_types = _discover_relationships(session)

        # Discover relationship schemas first
        rel_schemas: dict[str, dict] = {}
        for rel_type in rel_types:
            rel_schemas[rel_type] = _discover_relationship_schema(
                session, rel_type
            )

        # Build tables for each label
        for label in labels:
            fields = _discover_label_properties(
                session, label, sample_size
            )

            # Find relationships involving this label
            relationships = []
            for rel_type, rel_schema in rel_schemas.items():
                if rel_schema["source"] == label:
                    rel_props = rel_schema.get("properties", [])
                    relationships.append(RelationshipDefinition(
                        name=rel_type,
                        target_table=rel_schema["target"],
                        native_description=(
                            f"(:{label})-[:{rel_type}]->"
                            f"(:{rel_schema['target']})"
                        ),
                    ))

            store.add_table(TableDefinition(
                name=label,
                fields=fields,
                relationships=relationships,
                native_metadata={
                    "label":     label,
                    "node_type": "label",
                    "rel_schemas": {
                        rel_type: rel_schemas[rel_type]
                        for rel_type in rel_types
                        if rel_schemas[rel_type]["source"] == label
                    },
                },
            ))

    return store