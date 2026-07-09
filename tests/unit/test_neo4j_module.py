"""Tests for Neo4jModule loading, translate(), and native_validator."""
import pytest
from uqal_core.ast.nodes import (
    BoolLiteral,
    Compare,
    DbTableCall,
    FieldParam,
    FieldsParam,
    IntegerLiteral,
    StringLiteral,
    VariableRef,
    WhereParam,
)
from uqal_core.module_loader import ModuleLoader
from uqal_core.modules.standard.neo4j import native_validator
from uqal_core.modules.standard.neo4j.module import Neo4jModule
from uqal_core.modules.standard.neo4j.translator import Neo4jTranslator
from uqal_core.registry.module_registry import ModuleRegistry

pytestmark = pytest.mark.unit


def _table_call(command: str, params=None) -> DbTableCall:
    return DbTableCall(
        connection="graphdb",
        table="Order",
        command=command,
        params=params or [],
    )


def _where_str(field: str, op: str, value: str) -> WhereParam:
    return WhereParam(condition=Compare(
        left=VariableRef(parts=[field]),
        operator=op,
        right=StringLiteral(value=value),
    ))


def _where_int(field: str, op: str, value: int) -> WhereParam:
    return WhereParam(condition=Compare(
        left=VariableRef(parts=[field]),
        operator=op,
        right=IntegerLiteral(value=value),
    ))


# ---- Module loading ----

def test_module_loads_via_module_loader():
    registry = ModuleRegistry()
    loader = ModuleLoader(registry=registry)
    loader.load(["standard.neo4j"])
    module = registry.get_module("standard.neo4j")
    assert module.get_manifest().name == "standard.neo4j"


def test_module_manifest_name():
    module = Neo4jModule()
    assert module.get_manifest().name == "standard.neo4j"


def test_module_manifest_version():
    module = Neo4jModule()
    assert module.get_manifest().version == "0.1.0"


def test_module_native_command_name():
    module = Neo4jModule()
    assert module.get_native_command_name() == "cypher"


def test_module_has_translator():
    module = Neo4jModule()
    assert module._translator is not None


# ---- translate() for DbTableCall: get_table ----

def test_translate_get_table_produces_match():
    t = Neo4jTranslator()
    cypher, _ = t.translate(_table_call("get_table"))
    assert "MATCH" in cypher


def test_translate_get_table_includes_label():
    t = Neo4jTranslator()
    cypher, _ = t.translate(_table_call("get_table"))
    assert "`Order`" in cypher


def test_translate_get_table_produces_return():
    t = Neo4jTranslator()
    cypher, _ = t.translate(_table_call("get_table"))
    assert "RETURN" in cypher


def test_translate_get_table_no_limit():
    t = Neo4jTranslator()
    cypher, _ = t.translate(_table_call("get_table"))
    assert "LIMIT" not in cypher


def test_translate_get_table_returns_node_without_fields():
    t = Neo4jTranslator()
    cypher, _ = t.translate(_table_call("get_table"))
    assert "RETURN n" in cypher


# ---- translate() for DbTableCall: get_row ----

def test_translate_get_row_uses_find_one_semantics():
    t = Neo4jTranslator()
    cypher, _ = t.translate(_table_call("get_row"))
    assert "LIMIT 1" in cypher


def test_translate_get_row_includes_label():
    t = Neo4jTranslator()
    cypher, _ = t.translate(_table_call("get_row"))
    assert "`Order`" in cypher


# ---- translate() for DbTableCall: get_value ----

def test_translate_get_value_has_limit():
    t = Neo4jTranslator()
    cypher, _ = t.translate(_table_call("get_value", params=[FieldParam(name="amount")]))
    assert "LIMIT 1" in cypher


def test_translate_get_value_projects_field():
    t = Neo4jTranslator()
    cypher, _ = t.translate(_table_call("get_value", params=[FieldParam(name="amount")]))
    assert "amount" in cypher


# ---- Filter translation ----

def test_filter_produces_where_clause():
    t = Neo4jTranslator()
    cypher, _ = t.translate(_table_call("get_table", params=[_where_str("status", "=", "open")]))
    assert "WHERE" in cypher


def test_filter_bool_true():
    t = Neo4jTranslator()
    condition = Compare(
        left=VariableRef(parts=["active"]),
        operator="=",
        right=BoolLiteral(value=True),
    )
    cypher, _ = t.translate(_table_call("get_table", params=[WhereParam(condition=condition)]))
    assert "active" in cypher
    assert "true" in cypher


def test_filter_uses_parameterized_values():
    t = Neo4jTranslator()
    _, params = t.translate(_table_call("get_table", params=[_where_int("id", "=", 42)]))
    assert 42 in params.values()


def test_filter_not_equal_maps_to_cypher():
    t = Neo4jTranslator()
    cypher, _ = t.translate(_table_call("get_table", params=[_where_str("status", "!=", "closed")]))
    assert "<>" in cypher


# ---- Fields translation ----

def test_fields_param_in_return():
    t = Neo4jTranslator()
    cypher, _ = t.translate(_table_call("get_table", params=[FieldsParam(names=["name", "price"])]))
    assert "n.name AS name" in cypher
    assert "n.price AS price" in cypher


def test_field_param_single_field():
    t = Neo4jTranslator()
    cypher, _ = t.translate(_table_call("get_table", params=[FieldParam(name="price")]))
    assert "n.price AS price" in cypher


def test_no_fields_returns_full_node():
    t = Neo4jTranslator()
    cypher, _ = t.translate(_table_call("get_table"))
    assert "RETURN n" in cypher


def test_translate_returns_tuple():
    t = Neo4jTranslator()
    result = t.translate(_table_call("get_table"))
    assert isinstance(result, tuple)
    assert len(result) == 2


def test_translate_unsupported_node_raises():
    t = Neo4jTranslator()
    with pytest.raises(NotImplementedError):
        t.translate(object())


# ---- native_validator: security_check ----

def test_security_check_blocks_load_csv():
    errors = native_validator.security_check("LOAD CSV FROM 'file.csv' AS row RETURN row")
    assert len(errors) >= 1
    assert any("not allowed" in e for e in errors)


def test_security_check_blocks_drop():
    errors = native_validator.security_check("DROP INDEX my_index")
    assert len(errors) >= 1


def test_security_check_blocks_create_index():
    errors = native_validator.security_check("CREATE INDEX FOR (n:User) ON (n.email)")
    assert len(errors) >= 1


def test_security_check_blocks_create_constraint():
    errors = native_validator.security_check("CREATE CONSTRAINT FOR (n:User) REQUIRE n.email IS UNIQUE")
    assert len(errors) >= 1


def test_security_check_allows_match_return():
    errors = native_validator.security_check("MATCH (n:User) RETURN n")
    assert errors == []


def test_security_check_case_insensitive():
    errors = native_validator.security_check("load csv from 'file' as row")
    assert len(errors) >= 1


def test_security_check_returns_list():
    errors = native_validator.security_check("MATCH (n) RETURN n")
    assert isinstance(errors, list)


# ---- native_validator: syntax_check without session ----

def test_syntax_check_without_session_returns_empty():
    errors = native_validator.syntax_check("MATCH (n) RETURN n", session=None)
    assert errors == []


def test_syntax_check_without_session_ignores_invalid_cypher():
    errors = native_validator.syntax_check("this is NOT valid cypher @#$%", session=None)
    assert errors == []


def test_syntax_check_session_none_is_default():
    errors = native_validator.syntax_check("MATCH (n) RETURN n")
    assert errors == []


# ---- native_validator: validate (combined) ----

def test_validate_blocks_security_violation():
    errors = native_validator.validate("LOAD CSV FROM 'x' AS row")
    assert any("Security violation" in e for e in errors)


def test_validate_returns_empty_for_safe_query():
    errors = native_validator.validate("MATCH (n:User) RETURN n")
    assert errors == []


# ---- Neo4jModule.validate_native_query ----

def test_module_validate_blocks_load_csv():
    module = Neo4jModule()
    errors = module.validate_native_query("LOAD CSV FROM 'x' AS row")
    assert len(errors) >= 1


def test_module_validate_allows_safe_cypher():
    module = Neo4jModule()
    errors = module.validate_native_query("MATCH (n:User) WHERE n.active = true RETURN n")
    assert errors == []
