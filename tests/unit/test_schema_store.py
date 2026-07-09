"""Tests for uqal_core.schema.schema_store"""
import pytest
from uqal_core.schema.schema_store import (
    FieldDefinition,
    SchemaStore,
    TableDefinition,
    core_type_field,
)
from uqal_core.types import CoreType

pytestmark = pytest.mark.unit


def make_users_table() -> TableDefinition:
    return TableDefinition(
        name="users",
        fields=[
            core_type_field("id", CoreType.INTEGER, primary_key=True),
            core_type_field("name", CoreType.STRING, required=True),
            core_type_field("active", CoreType.BOOLEAN),
        ],
    )


def test_schema_store_add_and_list():
    store = SchemaStore()
    store.add_table(make_users_table())
    assert "users" in store.list_tables()


def test_schema_store_get_table():
    store = SchemaStore()
    store.add_table(make_users_table())
    table = store.get_table("users")
    assert table.name == "users"
    assert len(table.fields) == 3


def test_schema_store_get_unknown_table():
    store = SchemaStore()
    with pytest.raises(KeyError, match="not known"):
        store.get_table("nonexistent")


def test_schema_store_has_table():
    store = SchemaStore()
    store.add_table(make_users_table())
    assert store.has_table("users") is True
    assert store.has_table("orders") is False


def test_table_get_field():
    table = make_users_table()
    field = table.get_field("name")
    assert field is not None
    assert field.type == CoreType.STRING.value
    assert field.required is True


def test_table_get_unknown_field():
    table = make_users_table()
    assert table.get_field("nonexistent") is None


def test_table_has_field():
    table = make_users_table()
    assert table.has_field("id") is True
    assert table.has_field("email") is False


def test_core_type_field_helper():
    f = core_type_field("id", CoreType.INTEGER, primary_key=True)
    assert f.name == "id"
    assert f.type == "integer"
    assert f.primary_key is True


def test_schema_store_list_sorted():
    store = SchemaStore()
    store.add_table(TableDefinition(name="zebra"))
    store.add_table(TableDefinition(name="apple"))
    assert store.list_tables() == ["apple", "zebra"]
