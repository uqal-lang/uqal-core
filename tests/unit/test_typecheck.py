"""Tests for uqal_core.typecheck.checker"""
import pytest
from pathlib import Path
from lark import Lark
from uqal_core.ast.transformer import UQALTransformer
from uqal_core.ast.nodes import Program
from uqal_core.typecheck.checker import TypeChecker
from uqal_core.registry.connection_registry import (
    ConnectionConfig,
    ConnectionRegistry,
)
from uqal_core.registry.module_registry import ModuleRegistry
from uqal_core.module_loader import ModuleLoader

pytestmark = pytest.mark.unit

_PROJECT_ROOT = Path(__file__).parent.parent.parent
_GRAMMAR = (_PROJECT_ROOT / "src/uqal_core/parser/base_grammar.lark").read_text()
_IMPORT_PATHS = [str(_PROJECT_ROOT / "src/uqal_core/parser")]


@pytest.fixture(scope="module")
def parse():
    parser = Lark(_GRAMMAR, parser="earley", import_paths=_IMPORT_PATHS)
    transformer = UQALTransformer()

    def _parse(script: str) -> Program:
        tree = parser.parse(script)
        return transformer.transform(tree)

    return _parse


@pytest.fixture
def empty_registries():
    return ModuleRegistry(), ConnectionRegistry()


@pytest.fixture
def registries_with_dummy():
    module_registry = ModuleRegistry()
    loader = ModuleLoader(registry=module_registry)
    loader.load(["standard.dummy"])

    conn_registry = ConnectionRegistry()
    conn_registry.register(ConnectionConfig(
        connection_name="db1",
        module_type="dummy",
        module_names=["standard.dummy"],
    ))
    module_registry.bind_module_to_connection("db1", "standard.dummy")

    # Store the initial schema so the type-checker can validate
    # table and field references without requiring a live connection.
    dummy = module_registry.get_module_for_connection("db1")
    module_registry.store_schema("db1", dummy.get_schema_store())

    return module_registry, conn_registry


def check(parse, registries, script) -> list:
    module_registry, conn_registry = registries
    program = parse(script)
    checker = TypeChecker(module_registry, conn_registry)
    return checker.check(program)


def test_defined_variable_no_error(parse, empty_registries):
    errors = check(parse, empty_registries, "let a = 5 let b = a + 1")
    assert errors == []


def test_undefined_variable_error(parse, empty_registries):
    errors = check(parse, empty_registries, "let b = a + 1")
    assert any("'a' is used before" in str(e) for e in errors)


def test_variable_in_if_condition(parse, empty_registries):
    errors = check(parse, empty_registries,
                   "let age = 18 if age > 10 : let x = 1")
    assert errors == []


def test_integer_addition_no_error(parse, empty_registries):
    errors = check(parse, empty_registries,
                   "let a = 5 let b = 3 let c = a + b")
    assert errors == []


def test_string_integer_addition_error(parse, empty_registries):
    errors = check(parse, empty_registries,
                   'let a = "hello" let b = 5 let c = a + b')
    assert any("cannot be applied" in str(e) for e in errors)


def test_string_concatenation_no_error(parse, empty_registries):
    errors = check(parse, empty_registries,
                   'let a = "hello" let b = " world" let c = a + b')
    assert errors == []


def test_unknown_connection_error(parse, empty_registries):
    errors = check(parse, empty_registries,
                   "db1.dummy_table.get_value(where id = 5, field value)")
    assert any("'db1' is not registered" in str(e) for e in errors)


def test_known_connection_no_error(parse, registries_with_dummy):
    errors = check(parse, registries_with_dummy,
                   "db1.dummy_table.get_value(where id = 5, field value)")
    assert errors == []


def test_unknown_table_error(parse, registries_with_dummy):
    errors = check(parse, registries_with_dummy,
                   "db1.nonexistent.get_value(where id = 5, field value)")
    assert any("'nonexistent' does not exist" in str(e) for e in errors)


def test_known_table_no_error(parse, registries_with_dummy):
    errors = check(parse, registries_with_dummy,
                   "db1.dummy_table.get(where id = 5, fields id, value)")
    assert errors == []


def test_unknown_field_error(parse, registries_with_dummy):
    errors = check(parse, registries_with_dummy,
                   "db1.dummy_table.get_value(where id = 5, field nonexistent)")
    assert any("'nonexistent' does not exist" in str(e) for e in errors)


def test_known_field_no_error(parse, registries_with_dummy):
    errors = check(parse, registries_with_dummy,
                   "db1.dummy_table.get_value(where id = 5, field value)")
    assert errors == []


def test_variable_in_where_no_error(parse, registries_with_dummy):
    errors = check(
        parse, registries_with_dummy,
        "let my_id = 5 "
        "db1.dummy_table.get_value(where id = my_id, field value)"
    )
    assert errors == []


def test_multiple_errors_collected(parse, empty_registries):
    errors = check(parse, empty_registries, "let c = a + b")
    assert len(errors) >= 1


def test_is_null_no_error(parse, registries_with_dummy):
    errors = check(parse, registries_with_dummy,
                   "db1.dummy_table.get(where id is null, fields id, value)")
    assert errors == []


def test_is_not_null_no_error(parse, registries_with_dummy):
    errors = check(parse, registries_with_dummy,
                   "db1.dummy_table.get(where id is not null, fields id, value)")
    assert errors == []
