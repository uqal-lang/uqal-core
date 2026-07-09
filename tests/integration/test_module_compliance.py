"""
Module compliance tests.

Automatically validates all standard modules against the
UQALModule interface requirements. These tests ensure that
any new module or change to an existing module doesn't break
the required extension points.

Tests mirror the checks in scripts/dev/validate_module.py
but in pytest format for CI integration.
"""

import pytest
from pathlib import Path

pytestmark = pytest.mark.integration

# Modules to validate (skip dummy - it's intentionally minimal)
MODULES_TO_TEST = [
    "standard.postgresql",
    "standard.mongodb",
    "standard.neo4j",
]


@pytest.fixture(scope="module")
def loaded_modules():
    """Loads all standard modules once for all tests."""
    from uqal_core.module_loader import ModuleLoader
    from uqal_core.registry.module_registry import ModuleRegistry

    registry = ModuleRegistry()
    loader = ModuleLoader(registry=registry)

    modules = {}
    for name in MODULES_TO_TEST:
        loader.load([name])
        modules[name] = registry.get_module(name)

    return modules


@pytest.fixture(scope="module")
def grammar_parser(loaded_modules):
    """Builds a grammar parser with all modules loaded."""
    from uqal_core.parser.grammar_builder import GrammarBuilder
    builder = GrammarBuilder()
    return builder.build(list(loaded_modules.values()))


# ============================================================
# Parametrized compliance checks
# ============================================================

@pytest.mark.parametrize("module_name", MODULES_TO_TEST)
def test_module_loads(loaded_modules, module_name):
    assert module_name in loaded_modules
    assert loaded_modules[module_name] is not None


@pytest.mark.parametrize("module_name", MODULES_TO_TEST)
def test_required_methods(loaded_modules, module_name):
    module = loaded_modules[module_name]
    required = [
        "get_manifest", "get_grammar_extension", "get_capabilities",
        "get_type_mapping", "get_native_command_name",
        "get_connection_schema", "build_connection",
        "translate", "execute", "execute_native",
        "validate_native_query", "get_schema_store",
        "sync_schema_from_source", "load_cached_schema",
        "save_schema_cache", "create_view",
    ]
    for method in required:
        assert hasattr(module, method) and callable(
            getattr(module, method)
        ), f"Module '{module_name}' missing method: {method}"


@pytest.mark.parametrize("module_name", MODULES_TO_TEST)
def test_manifest(loaded_modules, module_name):
    manifest = loaded_modules[module_name].get_manifest()
    assert manifest.name == module_name
    assert manifest.version
    assert isinstance(manifest.requires, list)


@pytest.mark.parametrize("module_name", MODULES_TO_TEST)
def test_type_mapping_covers_all_core_types(
    loaded_modules, module_name
):
    from uqal_core.types import CoreType
    mapping = loaded_modules[module_name].get_type_mapping()
    for core_type in CoreType:
        assert core_type.value in mapping, (
            f"Module '{module_name}' missing type mapping "
            f"for CoreType.{core_type.name}"
        )


@pytest.mark.parametrize("module_name", MODULES_TO_TEST)
def test_connection_schema(loaded_modules, module_name):
    from uqal_core.config.connection_schema import ConnectionSchema
    schema_cls = loaded_modules[module_name].get_connection_schema()
    assert issubclass(schema_cls, ConnectionSchema)
    assert len(schema_cls.all_fields()) > 0


@pytest.mark.parametrize("module_name", MODULES_TO_TEST)
def test_grammar_extension_rules_in_grammar(
    loaded_modules, module_name
):
    module = loaded_modules[module_name]
    grammar_ext = module.get_grammar_extension()
    caps = module.get_capabilities()
    grammar_exts = getattr(caps, "grammar_extensions", {})

    for point, rules in grammar_exts.items():
        for rule in rules:
            assert rule in grammar_ext, (
                f"Module '{module_name}': rule '{rule}' declared "
                f"in '{point}' but not found in grammar extension"
            )


@pytest.mark.parametrize("module_name", MODULES_TO_TEST)
def test_grammar_builds_with_module(loaded_modules, module_name):
    from uqal_core.parser.grammar_builder import GrammarBuilder
    module = loaded_modules[module_name]
    builder = GrammarBuilder()
    parser = builder.build([module])
    assert parser is not None


@pytest.mark.parametrize("module_name", MODULES_TO_TEST)
def test_native_command_parseable(
    loaded_modules, module_name, grammar_parser
):
    from uqal_core.ast.transformer import UQALTransformer
    from uqal_core.ast.nodes import DbConnectionCall

    module = loaded_modules[module_name]
    native_cmd = module.get_native_command_name()
    grammar_ext = module.get_grammar_extension()

    if not native_cmd or not grammar_ext:
        pytest.skip("Module has no native command")

    transformer = UQALTransformer()
    test_script = f'testdb.{native_cmd}("test query")'

    tree = grammar_parser.parse(test_script)
    program = transformer.transform(tree)

    assert len(program.statements) == 1
    stmt = program.statements[0]
    assert isinstance(stmt, DbConnectionCall)
    assert stmt.command == "native_sql"


@pytest.mark.parametrize("module_name", MODULES_TO_TEST)
def test_capabilities_module_name_matches(
    loaded_modules, module_name
):
    caps = loaded_modules[module_name].get_capabilities()
    assert caps.module_name == module_name


@pytest.mark.parametrize("module_name", MODULES_TO_TEST)
def test_capabilities_has_provided_types(
    loaded_modules, module_name
):
    caps = loaded_modules[module_name].get_capabilities()
    assert isinstance(caps.provided_types, list)


@pytest.mark.parametrize("module_name", MODULES_TO_TEST)
def test_capabilities_has_translatable_nodes(
    loaded_modules, module_name
):
    caps = loaded_modules[module_name].get_capabilities()
    assert isinstance(caps.translatable_nodes, list)
    assert len(caps.translatable_nodes) > 0


@pytest.mark.parametrize("module_name", MODULES_TO_TEST)
def test_condition_extensions_registered(
    loaded_modules, module_name
):
    from uqal_core.ast.module_nodes import _MODULE_NODE_REGISTRY

    caps = loaded_modules[module_name].get_capabilities()
    grammar_exts = getattr(caps, "grammar_extensions", {})
    condition_rules = grammar_exts.get("condition", [])

    for rule in condition_rules:
        assert rule in _MODULE_NODE_REGISTRY, (
            f"Module '{module_name}': condition rule '{rule}' "
            f"not registered in module_nodes registry"
        )


# ============================================================
# Cross-module tests
# ============================================================

def test_all_modules_grammar_builds_together(loaded_modules):
    """All modules can be loaded simultaneously without conflicts."""
    from uqal_core.parser.grammar_builder import GrammarBuilder
    builder = GrammarBuilder()
    parser = builder.build(list(loaded_modules.values()))
    assert parser is not None


def test_no_duplicate_native_commands(loaded_modules):
    """Each module has a unique native command name."""
    commands = {}
    for name, module in loaded_modules.items():
        cmd = module.get_native_command_name()
        assert cmd not in commands, (
            f"Duplicate native command '{cmd}' in "
            f"'{name}' and '{commands[cmd]}'"
        )
        commands[cmd] = name


def test_no_duplicate_grammar_rules(loaded_modules):
    """Each module declares unique grammar rule names."""
    all_rules: dict[str, str] = {}
    for name, module in loaded_modules.items():
        caps = module.get_capabilities()
        grammar_exts = getattr(caps, "grammar_extensions", {})
        for point, rules in grammar_exts.items():
            for rule in rules:
                assert rule not in all_rules, (
                    f"Duplicate grammar rule '{rule}' in "
                    f"'{name}' and '{all_rules[rule]}'"
                )
                all_rules[rule] = name