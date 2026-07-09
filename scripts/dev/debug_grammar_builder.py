# scripts/dev/debug_grammar_builder.py
from uqal_core.module_loader import ModuleLoader
from uqal_core.registry.module_registry import ModuleRegistry
from uqal_core.parser.grammar_builder import GrammarBuilder

registry = ModuleRegistry()
loader = ModuleLoader(registry=registry)
loader.load(["standard.postgresql"])

modules = [registry.get_module("standard.postgresql")]
builder = GrammarBuilder()

# Zeige extensions
extensions = builder._collect_extensions(modules)
print("extensions:", extensions)

# Zeige rohe Grammatik um den Platzhalter
grammar = builder._assemble(modules)
for i, line in enumerate(grammar.splitlines()):
    if "module_connection" in line or "postgresql_sql" in line:
        print(f"line {i}: {repr(line)}")