"""Tests for MongoDBModule, MongoDBTranslator, and native_validator."""
import pytest
from uqal_core.ast.nodes import (
    Compare,
    CoreTypeRef,
    DbTableCall,
    DbWriteCall,
    FieldDefinition,
    FieldParam,
    FieldsParam,
    IntegerLiteral,
    LogicalAnd,
    SchemaDefinition,
    StringLiteral,
    VariableRef,
    WhereParam,
)
from uqal_core.modules.standard.mongodb import native_validator
from uqal_core.modules.standard.mongodb.module import MongoDBModule
from uqal_core.modules.standard.mongodb.translator import MongoDBTranslator

pytestmark = pytest.mark.unit


def _table_call(command: str, params=None) -> DbTableCall:
    return DbTableCall(
        connection="testdb",
        table="orders",
        command=command,
        params=params or [],
    )


def _where(field: str, op: str, value) -> WhereParam:
    if isinstance(value, str):
        val_node = StringLiteral(value=value)
    else:
        val_node = IntegerLiteral(value=value)
    return WhereParam(condition=Compare(
        left=VariableRef(parts=[field]),
        operator=op,
        right=val_node,
    ))


# ---- Module identity ----

def test_module_instantiates():
    module = MongoDBModule()
    assert module is not None


def test_module_manifest_name():
    module = MongoDBModule()
    assert module.get_manifest().name == "standard.mongodb"


def test_module_manifest_version():
    module = MongoDBModule()
    assert module.get_manifest().version is not None


def test_module_native_command_name():
    module = MongoDBModule()
    assert module.get_native_command_name() == "mongo"


def test_module_has_translator():
    module = MongoDBModule()
    assert module._translator is not None


# ---- Translator: get_table ----

def test_translate_get_table_command():
    t = MongoDBTranslator()
    result = t.translate(_table_call("get_table"))
    assert result["command"] == "find"


def test_translate_get_table_collection():
    t = MongoDBTranslator()
    result = t.translate(_table_call("get_table"))
    assert result["collection"] == "orders"


def test_translate_get_table_empty_filter():
    t = MongoDBTranslator()
    result = t.translate(_table_call("get_table"))
    assert result["filter"] == {}


def test_translate_get_table_empty_projection():
    t = MongoDBTranslator()
    result = t.translate(_table_call("get_table"))
    assert result["projection"] == {}


# ---- Translator: get_row ----

def test_translate_get_row_command():
    t = MongoDBTranslator()
    result = t.translate(_table_call("get_row"))
    assert result["command"] == "find_one"


def test_translate_get_row_collection():
    t = MongoDBTranslator()
    result = t.translate(_table_call("get_row"))
    assert result["collection"] == "orders"


# ---- Translator: get_value ----

def test_translate_get_value_command():
    t = MongoDBTranslator()
    result = t.translate(_table_call("get_value", params=[FieldParam(name="amount")]))
    assert result["command"] == "find_one"


def test_translate_get_value_field():
    t = MongoDBTranslator()
    result = t.translate(_table_call("get_value", params=[FieldParam(name="amount")]))
    assert result["field"] == "amount"


def test_translate_get_value_projection():
    t = MongoDBTranslator()
    result = t.translate(_table_call("get_value", params=[FieldParam(name="amount")]))
    assert result["projection"] == {"amount": 1}


# ---- Translator: filter translation ----

def test_filter_string_equality():
    t = MongoDBTranslator()
    result = t.translate(_table_call("get_table", params=[_where("status", "=", "open")]))
    assert result["filter"] == {"status": "open"}


def test_filter_integer_equality():
    t = MongoDBTranslator()
    result = t.translate(_table_call("get_table", params=[_where("id", "=", 42)]))
    assert result["filter"] == {"id": 42}


def test_filter_not_equal():
    t = MongoDBTranslator()
    result = t.translate(_table_call("get_table", params=[_where("status", "!=", "closed")]))
    assert result["filter"] == {"status": {"$ne": "closed"}}


def test_filter_greater_than():
    t = MongoDBTranslator()
    result = t.translate(_table_call("get_table", params=[_where("price", ">", 100)]))
    assert result["filter"] == {"price": {"$gt": 100}}


def test_filter_less_than():
    t = MongoDBTranslator()
    result = t.translate(_table_call("get_table", params=[_where("price", "<", 50)]))
    assert result["filter"] == {"price": {"$lt": 50}}


def test_filter_greater_equal():
    t = MongoDBTranslator()
    result = t.translate(_table_call("get_table", params=[_where("qty", ">=", 5)]))
    assert result["filter"] == {"qty": {"$gte": 5}}


def test_filter_less_equal():
    t = MongoDBTranslator()
    result = t.translate(_table_call("get_table", params=[_where("qty", "<=", 10)]))
    assert result["filter"] == {"qty": {"$lte": 10}}


def test_filter_logical_and():
    t = MongoDBTranslator()
    cond = LogicalAnd(
        left=Compare(
            left=VariableRef(parts=["status"]),
            operator="=",
            right=StringLiteral(value="open"),
        ),
        right=Compare(
            left=VariableRef(parts=["active"]),
            operator="=",
            right=StringLiteral(value="true"),
        ),
    )
    result = t.translate(_table_call("get_table", params=[WhereParam(condition=cond)]))
    assert "$and" in result["filter"]
    assert len(result["filter"]["$and"]) == 2


# ---- Translator: projection translation ----

def test_projection_field_param():
    t = MongoDBTranslator()
    result = t.translate(_table_call("get_table", params=[FieldParam(name="name")]))
    assert result["projection"] == {"name": 1}


def test_projection_fields_param_multiple():
    t = MongoDBTranslator()
    result = t.translate(_table_call("get_table", params=[FieldsParam(names=["id", "name", "price"])]))
    assert result["projection"] == {"id": 1, "name": 1, "price": 1}


def test_projection_empty_without_params():
    t = MongoDBTranslator()
    result = t.translate(_table_call("get_table"))
    assert result["projection"] == {}


def test_unsupported_node_raises():
    t = MongoDBTranslator()
    with pytest.raises(NotImplementedError):
        t.translate(object())


# ---- native_validator: security_check ----

def test_security_check_blocks_dollar_where():
    errors = native_validator.security_check('{"find": "orders", "$where": "this.x > 0"}')
    assert len(errors) >= 1
    assert any("not allowed" in e for e in errors)


def test_security_check_blocks_function():
    errors = native_validator.security_check('{"$function": "..."}')
    assert len(errors) >= 1


def test_security_check_blocks_accumulator():
    errors = native_validator.security_check('{"$accumulator": {}}')
    assert len(errors) >= 1


def test_security_check_allows_clean_query():
    errors = native_validator.security_check('{"find": "orders", "filter": {"status": "open"}}')
    assert errors == []


def test_security_check_case_insensitive():
    errors = native_validator.security_check('{"$WHERE": "true"}')
    assert len(errors) >= 1


def test_security_check_returns_list():
    errors = native_validator.security_check('{}')
    assert isinstance(errors, list)


# ---- native_validator: syntax_check ----

def test_syntax_check_valid_json():
    errors = native_validator.syntax_check('{"find": "orders"}')
    assert errors == []


def test_syntax_check_empty_object():
    errors = native_validator.syntax_check('{}')
    assert errors == []


def test_syntax_check_invalid_json():
    errors = native_validator.syntax_check('not json {{{')
    assert len(errors) == 1
    assert "Invalid JSON" in errors[0]


def test_syntax_check_missing_brace():
    errors = native_validator.syntax_check('{"find": "orders"')
    assert len(errors) >= 1


def test_syntax_check_returns_list():
    errors = native_validator.syntax_check('{}')
    assert isinstance(errors, list)


# ---- native_validator: validate (combined) ----

def test_validate_security_violation_skips_syntax_check():
    errors = native_validator.validate('{"$where": "true"}')
    assert any("Security violation" in e for e in errors)


def test_validate_syntax_error_when_no_security_issue():
    errors = native_validator.validate('invalid json')
    assert any("Invalid JSON" in e for e in errors)


def test_validate_empty_for_valid_safe_query():
    errors = native_validator.validate('{"find": "users"}')
    assert errors == []


def test_validate_returns_list():
    errors = native_validator.validate('{}')
    assert isinstance(errors, list)


# ---- MongoDBModule.validate_native_query ----

def test_module_validate_native_query_blocks_where():
    module = MongoDBModule()
    errors = module.validate_native_query('{"$where": "1==1"}')
    assert len(errors) >= 1


def test_module_validate_native_query_passes_clean():
    module = MongoDBModule()
    errors = module.validate_native_query('{"find": "orders"}')
    assert errors == []


def test_module_validate_native_query_invalid_json():
    module = MongoDBModule()
    errors = module.validate_native_query('not json')
    assert len(errors) >= 1
