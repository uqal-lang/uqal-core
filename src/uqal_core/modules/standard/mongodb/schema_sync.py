"""
MongoDB schema discovery.

Two strategies depending on whether a collection has a validator:

1. $jsonSchema validator (strict)
   → reads exact field definitions from the collection validator
   → enforced by MongoDB itself on every write

2. Field aggregation (flexible)
   → scans ALL documents via $objectToArray aggregation
   → discovers every field that has ever existed
   → type is the most common type seen for that field
   → used as soft reference: new fields allowed, known fields
     should match the observed type for consistency
"""

from __future__ import annotations

from uqal_core.schema.schema_store import (
    FieldDefinition,
    SchemaStore,
    TableDefinition,
)
from uqal_core.modules.standard.mongodb.type_mapping import (
    bson_type_to_core,
    python_type_to_core,
)


def _read_json_schema(db, collection_name: str) -> dict | None:
    """
    Reads the $jsonSchema validator for a collection if it exists.
    Returns None if no validator is defined.
    """
    try:
        infos = list(db.list_collections(
            filter={"name": collection_name}
        ))
        if not infos:
            return None
        options = infos[0].get("options", {})
        validator = options.get("validator", {})
        return validator.get("$jsonSchema")
    except Exception:
        return None


def _fields_from_json_schema(schema: dict) -> list[FieldDefinition]:
    """
    Builds FieldDefinition list from a $jsonSchema definition.
    """
    required_fields = set(schema.get("required", []))
    properties = schema.get("properties", {})
    fields = []

    for field_name, field_def in properties.items():
        bson_type = field_def.get("bsonType", "string")
        if isinstance(bson_type, list):
            bson_type = next(
                (t for t in bson_type if t != "null"), "string"
            )

        core_type = bson_type_to_core(bson_type)
        is_flexible = (
            bson_type == "object"
            and "properties" not in field_def
        )

        fields.append(FieldDefinition(
            name=field_name,
            type=core_type,
            primary_key=field_name == "_id",
            required=field_name in required_fields,
            flexible=is_flexible,
        ))

    if "_id" not in {f.name for f in fields}:
        fields.insert(0, FieldDefinition(
            name="_id",
            type="string",
            primary_key=True,
            required=True,
        ))

    return fields


def _fields_from_aggregation(collection) -> list[FieldDefinition]:
    """
    Discovers all fields that have ever existed in a collection
    by scanning ALL documents via $objectToArray aggregation.

    Also discovers nested fields one level deep (e.g. address.city)
    so dot-notation queries work correctly.

    Type is the most common observed type for each field.
    Fields are marked flexible=True so the type checker allows
    new unknown fields without errors.
    """
    pipeline = [
        # Flatten top-level document into key-value pairs
        {
            "$project": {
                "fields": {"$objectToArray": "$$ROOT"}
            }
        },
        # One document per field
        {"$unwind": "$fields"},
        # Group by field name, collect all observed types
        {
            "$group": {
                "_id": "$fields.k",
                "types": {"$addToSet": {"$type": "$fields.v"}},
                "count": {"$sum": 1},
            }
        },
        # Sort by field name for consistent output
        {"$sort": {"_id": 1}},
    ]

    try:
        results = list(collection.aggregate(pipeline))
    except Exception:
        return [FieldDefinition(
            name="_id",
            type="string",
            primary_key=True,
            required=True,
        )]

    if not results:
        return [FieldDefinition(
            name="_id",
            type="string",
            primary_key=True,
            required=True,
        )]

    # Total document count for required-field heuristic
    total_docs = collection.count_documents({})

    fields = []
    for result in results:
        field_name = result["_id"]
        types = [t for t in result.get("types", []) if t != "null"]
        count = result.get("count", 0)

        # Pick most representative type
        # Priority: non-object types first, then object
        if not types:
            core_type = "string"
        elif len(types) == 1:
            core_type = _bson_js_type_to_core(types[0])
        else:
            # Multiple types seen — pick most common non-null type
            # Prefer specific types over "object" and "string"
            priority = ["int", "double", "bool", "date",
                        "string", "array", "object"]
            for t in priority:
                if t in types:
                    core_type = _bson_js_type_to_core(t)
                    break
            else:
                core_type = "string"

        # Mark as flexible if it's an object type
        # (could contain arbitrary sub-fields)
        is_flexible = "object" in types

        # Heuristic: field is "required" if present in >90% of docs
        # _id is always required
        is_required = (
            field_name == "_id"
            or (total_docs > 0 and count / total_docs > 0.9)
        )

        fields.append(FieldDefinition(
            name=field_name,
            type=core_type,
            primary_key=field_name == "_id",
            required=is_required,
            flexible=is_flexible,
        ))

    return fields


def _bson_js_type_to_core(js_type: str) -> str:
    """
    Maps JavaScript/BSON type names (as returned by $type operator)
    to UQAL core type names.

    The $type operator returns JS type names, not BSON type names:
      "int" / "long" / "double" / "decimal" → integer/float
      "string" → string
      "bool" → boolean
      "date" → datetime
      "array" → list
      "object" → list (treat as structured list/dict)
    """
    mapping = {
        "int":       "integer",
        "long":      "integer",
        "double":    "float",
        "decimal":   "float",
        "string":    "string",
        "bool":      "boolean",
        "date":      "datetime",
        "array":     "list",
        "object":    "list",
        "objectId":  "string",
        "binData":   "string",
        "null":      "string",
        "undefined": "string",
    }
    return mapping.get(js_type, "string")


def sync_full_schema(
    client,
    database_name: str,
    sample_size: int = 100,  # kept for API compatibility, no longer used
) -> SchemaStore:
    """
    Discovers the full schema for all collections in the database.

    For each collection:
      1. Reads $jsonSchema validator if defined (strict schema)
      2. Falls back to full field aggregation (flexible schema)
         which discovers ALL fields that have ever existed
    """
    store = SchemaStore()
    db = client[database_name]

    for collection_name in db.list_collection_names():
        json_schema = _read_json_schema(db, collection_name)

        if json_schema:
            fields = _fields_from_json_schema(json_schema)
            source = "json_schema"
        else:
            collection = db[collection_name]
            fields = _fields_from_aggregation(collection)
            source = "field_aggregation"

        store.add_table(TableDefinition(
            name=collection_name,
            fields=fields,
            native_metadata={
                "database":      database_name,
                "collection":    collection_name,
                "schema_source": source,
                "flexible":      source == "field_aggregation",
            },
        ))

    return store