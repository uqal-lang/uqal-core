# test_sql_grammar.py
from uqal_core.module_loader import ModuleLoader
from uqal_core.registry.module_registry import ModuleRegistry
from uqal_core.parser.grammar_builder import GrammarBuilder

registry = ModuleRegistry()
loader = ModuleLoader(registry=registry)
loader.load(["standard.postgresql"])

modules = [registry.get_module("standard.postgresql")]
builder = GrammarBuilder()
parser = builder.build(modules)

tests = [
    'testdb.sql("SELECT 1")',
    'testdb.sql("SELECT * FROM orders")',
]

for t in tests:
    try:
        tree = parser.parse(t)
        print(f"ok: {t}")
        print(tree.pretty())
    except Exception as e:
        print(f"FAIL: {t}")
        print(f"      {e}")