# scripts/dev/test_multi_module_grammar.py
from uqal_core.module_loader import ModuleLoader
from uqal_core.registry.module_registry import ModuleRegistry
from uqal_core.parser.grammar_builder import GrammarBuilder

registry = ModuleRegistry()
loader = ModuleLoader(registry=registry)
loader.load(["standard.postgresql", "standard.mongodb"])

modules = [
    registry.get_module("standard.postgresql"),
    registry.get_module("standard.mongodb"),
]

builder = GrammarBuilder()
grammar = builder._assemble(modules)

extensions = builder._collect_extensions(modules)
print("extensions:", extensions)
print("extra_rules:", getattr(builder, '_extra_rules', ''))

# In test_multi_module_grammar.py
for module in modules:
    caps = module.get_capabilities()
    print(f"\n{module.get_manifest().name}:")
    print(f"  grammar_extensions: {caps.grammar_extensions}")
    print(f"  grammar_extension text: {repr(module.get_grammar_extension()[:100])}")

# Zeige connection_command Zeilen
for line in grammar.splitlines():
    if any(x in line for x in [
        "module_connection_command",
        "postgresql_sql",
        "mongodb_mongo",
        "connection_command",
    ]):
        print(line)

print()

# Teste ob beide geparst werden können
parser = builder.build(modules)
tests = [
    'testdb.sql("SELECT 1")',
    'mongodb.mongo("{\\"find\\": \\"orders\\"}")',
]
for t in tests:
    try:
        parser.parse(t)
        print(f"ok: {t}")
    except Exception as e:
        print(f"FAIL: {t} -> {e}")
