"""
Grammar builder.

Assembles the final, runtime grammar from two sources:
  1. The fixed base grammar (base_grammar.lark + fragments/)
  2. Grammar extensions contributed by loaded modules at the three
     extension points (see language specification, chapter 9.1):

     MODULE_TABLE_COMMAND  - new table-level commands
                             (db1.table.postgis.within(...))
     MODULE_CONDITION      - new condition expressions
                             (postgis.within(location, polygon(...)))
     MODULE_PARAM          - new parameter types inside parentheses

Each extension point has a placeholder rule in the base grammar that
matches nothing by default (/(?!)/). The builder replaces these with
the actual module contributions at startup.

The resulting Lark parser instance is cached - modules are loaded
once per session, so the grammar is only compiled once.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from lark import Lark

if TYPE_CHECKING:
    from uqal_core.module_interface import UQALModule

# Path to the base grammar file, always relative to this file.
_BASE_GRAMMAR_PATH = Path(__file__).parent / "base_grammar.lark"
_PARSER_DIR = Path(__file__).parent

# The three extension point placeholder names as they appear in the
# base grammar. The builder replaces their definitions at runtime.
_EXTENSION_POINTS = {
    "table_command":      "module_table_command",
    "connection_command": "module_connection_command",
    "condition":          "module_condition",
    "param":              "module_param",
}


class GrammarBuilder:
    """
    Builds and caches a Lark parser instance for the current set of
    loaded modules.

    Usage:
        builder = GrammarBuilder()
        parser = builder.build(loaded_modules)
        tree = parser.parse("let a = db1.orders.get_value(where id = 5, field amount)")
    """

    def __init__(self) -> None:
        self._cached_parser: Lark | None = None
        self._cached_module_names: frozenset[str] = frozenset()

    def build(self, modules: list["UQALModule"]) -> Lark:
        """
        Returns a compiled Lark parser for the given set of modules.

        If called again with the same set of modules, returns the
        cached parser without recompiling - grammar compilation is
        expensive and should only happen once per module set.
        """
        module_names = frozenset(
            m.get_manifest().name for m in modules
        )

        if (
            self._cached_parser is not None
            and module_names == self._cached_module_names
        ):
            return self._cached_parser

        grammar = self._assemble(modules)
        self._cached_parser = Lark(
            grammar,
            parser="earley",
            import_paths=[str(_PARSER_DIR)],
        )
        self._cached_module_names = module_names
        return self._cached_parser

    def invalidate(self) -> None:
        """
        Clears the cached parser. Call this when the set of loaded
        modules changes (e.g. after uqal add-module).
        """
        self._cached_parser = None
        self._cached_module_names = frozenset()

    # ---- Assembly ----

    def _assemble(self, modules: list["UQALModule"]) -> str:
        """
        Builds the final grammar string by:
          1. Loading the base grammar
          2. Collecting grammar extensions from all modules
          3. Replacing the three extension point placeholders
        """
        base = _BASE_GRAMMAR_PATH.read_text(encoding="utf-8")

        extensions = self._collect_extensions(modules)

        grammar = base
        for point_key, placeholder_rule in _EXTENSION_POINTS.items():
            contributed = extensions.get(point_key, [])
            grammar = self._replace_extension_point(
                grammar, placeholder_rule, contributed
            )

        return grammar

    def _collect_extensions(
        self, modules: list["UQALModule"]
    ) -> dict[str, list[str]]:
        collected: dict[str, list[str]] = {
            "table_command":      [],
            "connection_command": [],   # neu
            "condition":          [],
            "param":              [],
        }
        extra_rules: list[str] = []

        for module in modules:
            extension_grammar = module.get_grammar_extension()
            if not extension_grammar.strip():
                continue

            caps = module.get_capabilities()
            grammar_extensions = getattr(
                caps, "grammar_extensions", {}
            )

            extra_rules.append(extension_grammar)

            for point_key in collected:
                rule_names = grammar_extensions.get(point_key, [])
                collected[point_key].extend(rule_names)

        self._extra_rules = "\n".join(extra_rules)
        return collected


    def _replace_extension_point(
        self,
        grammar: str,
        placeholder_rule: str,
        contributed_rules: list[str],
    ) -> str:
        if not contributed_rules:
            return grammar

        import re

        alternatives = " | ".join(contributed_rules)

        # Match the rule name, any amount of whitespace, colon,
        # any whitespace, then the placeholder pattern
        pattern = re.compile(
            rf'{re.escape(placeholder_rule)}\s*:\s*(?:/\\x00/|/\(\?!\)/)'
        )

        if pattern.search(grammar):
            grammar = pattern.sub(
                f'{placeholder_rule}: {alternatives}',
                grammar,
            )

        if hasattr(self, "_extra_rules") and self._extra_rules:
            grammar = grammar + "\n" + self._extra_rules
            self._extra_rules = ""

        return grammar