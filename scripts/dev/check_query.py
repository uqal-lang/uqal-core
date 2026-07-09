"""
Parse and translate a UQAL query — shows the parse tree, AST nodes,
and the translated native query output.

Useful for testing module translation during development without
needing a real database connection.

Usage:
    uv run python scripts/dev/check_query.py "mydb.users.get_table()"
    uv run python scripts/dev/check_query.py "mydb.users.get_table(where active = true, fields id, name)"
    uv run python scripts/dev/check_query.py "let x = 1 + 2  output x"
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))


def header(title: str) -> None:
    print(f"\n\033[1;34m{'─' * 60}\033[0m")
    print(f"\033[1;34m  {title}\033[0m")
    print(f"\033[1;34m{'─' * 60}\033[0m")


def check_query(query: str, module_names: list[str] | None = None) -> None:
    from uqal_core.module_loader import ModuleLoader
    from uqal_core.registry.module_registry import ModuleRegistry
    from uqal_core.parser.grammar_builder import GrammarBuilder
    from uqal_core.ast.transformer import UQALTransformer

    modules_to_load = module_names or ["standard.postgresql", "standard.mongodb", "standard.neo4j"]

    registry = ModuleRegistry()
    loader = ModuleLoader(registry=registry)
    loader.load(modules_to_load)

    # Use all registered modules (includes transitive dependencies)
    loaded_modules = [registry.get_module(m) for m in registry.list_modules()]

    builder = GrammarBuilder()
    parser = builder.build(loaded_modules)
    transformer = UQALTransformer()

    header("Input query")
    print(f"  {query}")

    header("Parse tree")
    try:
        tree = parser.parse(query)
        print(tree.pretty())
    except Exception as e:
        print(f"\033[91m  ✗ Parse failed: {e}\033[0m")
        return

    header("AST nodes")
    try:
        program = transformer.transform(tree)
        for i, stmt in enumerate(program.statements):
            print(f"  [{i}] {type(stmt).__name__}: {stmt}")
    except Exception as e:
        print(f"\033[91m  ✗ Transform failed: {e}\033[0m")
        return

    header("Translation")
    try:
        for i, stmt in enumerate(program.statements):
            # Find the module that handles this statement
            for module in loaded_modules:
                try:
                    result = module.translate(stmt)
                    if result is not None:
                        query_str, params = result
                        print(f"  Module:  {module.get_manifest().name}")
                        print(f"  Query:   {query_str}")
                        if params:
                            print(f"  Params:  {params}")
                        break
                except (NotImplementedError, AttributeError):
                    continue
    except Exception as e:
        print(f"  (translation not available for this statement type: {e})")

    print()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: uv run python scripts/dev/check_query.py \"<query>\"")
        print("       uv run python scripts/dev/check_query.py \"<query>\" --module standard.neo4j")
        sys.exit(1)

    query = sys.argv[1]
    modules = None

    if "--module" in sys.argv:
        idx = sys.argv.index("--module")
        modules = sys.argv[idx + 1:]

    check_query(query, modules)
