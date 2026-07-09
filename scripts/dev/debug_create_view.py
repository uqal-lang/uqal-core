# scripts/dev/debug_create_view.py
from uqal_core.module_loader import ModuleLoader
from uqal_core.registry.module_registry import ModuleRegistry
from uqal_core.parser.grammar_builder import GrammarBuilder

registry = ModuleRegistry()
loader = ModuleLoader(registry=registry)
loader.load(["standard.postgresql"])

modules = [registry.get_module("standard.postgresql")]
builder = GrammarBuilder()
parser = builder.build(modules)

script = """uqal_hr.create_view v_test:
    let e = table employees
    let d = table departments where d.id = e.department_id
    return e.id, e.name as emp_name, d.name"""

try:
    tree = parser.parse(script)
    print("ok")
    print(tree.pretty())
except Exception as e:
    print(f"FAIL: {e}")