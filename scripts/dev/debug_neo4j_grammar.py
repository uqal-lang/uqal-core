# scripts/dev/debug_neo4j_grammar.py
from uqal_core.module_loader import ModuleLoader
from uqal_core.registry.module_registry import ModuleRegistry
from uqal_core.parser.grammar_builder import GrammarBuilder

registry = ModuleRegistry()
loader = ModuleLoader(registry=registry)
loader.load(["standard.neo4j"])

modules = [registry.get_module("standard.neo4j")]
builder = GrammarBuilder()

# Zeige extensions
extensions = builder._collect_extensions(modules)
print("extensions:", extensions)

# Zeige zusammengebaute Grammatik - relevante Zeilen
grammar = builder._assemble(modules)
for line in grammar.splitlines():
    if any(x in line for x in [
        "module_condition",
        "neo4j_rel_traversal",
        "condition:",
    ]):
        print(repr(line))

print()

# Teste Parsing
parser = builder.build(modules)
try:
    tree = parser.parse("""neo4j_shop.query:
    let u = table User where active = true
    let o = table Order where u PLACED o
    return u.name, o.amount""")
    print("ok")
    print(tree.pretty())
except Exception as e:
    print(f"FAIL: {e}")