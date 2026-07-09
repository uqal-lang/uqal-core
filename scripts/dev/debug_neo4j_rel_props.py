# scripts/dev/debug_neo4j_rel_props.py
from uqal_core.module_loader import ModuleLoader
from uqal_core.registry.module_registry import ModuleRegistry
from uqal_core.parser.grammar_builder import GrammarBuilder
from uqal_core.ast.transformer import UQALTransformer

registry = ModuleRegistry()
loader = ModuleLoader(registry=registry)
loader.load(["standard.neo4j"])

modules = [registry.get_module("standard.neo4j")]
builder = GrammarBuilder()
parser = builder.build(modules)
transformer = UQALTransformer()

script = """neo4j_shop.query:
    let o = table Order where order_id = "ORD-001"
    let p = table Product where o CONTAINS[quantity, unit_price] p
    return p.name, quantity, unit_price"""

tree = parser.parse(script)
program = transformer.transform(tree)

stmt = program.statements[0]
print("Aliases:")
for alias in stmt.aliases:
    print(f"  {alias.alias} -> {alias.table}, condition={alias.condition}")

# Translate
module = registry.get_module("standard.neo4j")
cypher, params = module.translate(stmt)
print("\nCypher:", cypher)
print("Params:", params)
tree = parser.parse(script)
print(tree.pretty())
