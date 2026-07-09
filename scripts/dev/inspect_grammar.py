"""
Print the complete combined UQAL grammar for all (or selected) modules.
Useful for debugging grammar rules, extension points, and conflicts.

Usage:
    uv run python scripts/dev/inspect_grammar.py
    uv run python scripts/dev/inspect_grammar.py standard.neo4j
    uv run python scripts/dev/inspect_grammar.py standard.postgresql standard.neo4j
    uv run python scripts/dev/inspect_grammar.py --extension-points
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

_EXTENSION_POINTS = [
    "condition",
    "expr",
    "statement",
    "db_call",
]


def inspect_grammar(module_names: list[str], show_extension_points: bool = False) -> None:
    from uqal_core.module_loader import ModuleLoader
    from uqal_core.registry.module_registry import ModuleRegistry
    from uqal_core.parser.grammar_builder import GrammarBuilder

    registry = ModuleRegistry()
    loader = ModuleLoader(registry=registry)
    loader.load(module_names)
    loaded = [registry.get_module(m) for m in module_names if registry.get_module(m)]

    builder = GrammarBuilder()

    if show_extension_points:
        print("\n\033[1;34mExtension points and their contributors:\033[0m\n")
        for point in _EXTENSION_POINTS:
            contributors = []
            for module in loaded:
                caps = module.get_capabilities()
                exts = getattr(caps, "grammar_extensions", {})
                rules = exts.get(point, [])
                if rules:
                    contributors.append(f"{module.get_manifest().name}: {rules}")
            if contributors:
                print(f"  \033[33m{point}\033[0m")
                for c in contributors:
                    print(f"    → {c}")
            else:
                print(f"  \033[90m{point}  (no extensions)\033[0m")
        print()
        return

    print(f"\n\033[1;34mLoaded modules: {[m.get_manifest().name for m in loaded]}\033[0m\n")

    try:
        grammar_text = builder.get_combined_grammar(loaded)
        print(grammar_text)
    except AttributeError:
        # Fallback: build and show what we can
        parser = builder.build(loaded)
        print("(Grammar built successfully — source text not directly accessible)")
        print(f"\nParser type: {type(parser)}")


if __name__ == "__main__":
    args = sys.argv[1:]

    show_ext_points = "--extension-points" in args
    if show_ext_points:
        args = [a for a in args if a != "--extension-points"]

    if not args:
        args = ["standard.postgresql", "standard.mongodb", "standard.neo4j"]

    inspect_grammar(args, show_extension_points=show_ext_points)
