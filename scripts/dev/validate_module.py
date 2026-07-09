"""
Module validator.

Checks if a UQAL module correctly implements all required
extension points and registration mechanisms.

Usage:
    uv run python scripts/dev/validate_module.py standard.neo4j
    uv run python scripts/dev/validate_module.py standard.postgresql
    uv run python scripts/dev/validate_module.py standard.mongodb
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))


def check(condition: bool, message: str, level: str = "ERROR") -> bool:
    """Prints a check result and returns True if passed."""
    icon = "✓" if condition else ("⚠" if level == "WARN" else "✗")
    color = "\033[92m" if condition else (
        "\033[93m" if level == "WARN" else "\033[91m"
    )
    reset = "\033[0m"
    print(f"  {color}{icon}{reset} {message}")
    return condition


def validate_module(module_name: str) -> bool:
    print(f"\n{'='*60}")
    print(f"Validating module: {module_name}")
    print(f"{'='*60}")

    errors = 0
    warnings = 0

    # ---- 1. Load module ----
    print("\n[1] Module loading")
    try:
        from uqal_core.module_loader import ModuleLoader
        from uqal_core.registry.module_registry import ModuleRegistry

        registry = ModuleRegistry()
        loader = ModuleLoader(registry=registry)
        loader.load([module_name])
        module = registry.get_module(module_name)
        check(True, f"Module '{module_name}' loads successfully")
    except Exception as e:
        check(False, f"Module load failed: {e}")
        print("\n❌ Cannot continue — module failed to load.")
        return False

    # ---- 2. Required interface methods ----
    print("\n[2] Required UQALModule interface methods")

    required_methods = [
        "get_manifest",
        "get_grammar_extension",
        "get_capabilities",
        "get_type_mapping",
        "get_native_command_name",
        "get_connection_schema",
        "build_connection",
        "translate",
        "execute",
        "execute_native",
        "validate_native_query",
        "get_schema_store",
        "sync_schema_from_source",
        "load_cached_schema",
        "save_schema_cache",
        "create_view",
    ]

    for method in required_methods:
        has_method = hasattr(module, method) and callable(
            getattr(module, method)
        )
        if not check(has_method, f"Has method: {method}"):
            errors += 1

    # ---- 3. Manifest ----
    print("\n[3] Manifest")
    try:
        manifest = module.get_manifest()
        if not check(bool(manifest.name), f"manifest.name = '{manifest.name}'"):
            errors += 1
        if not check(bool(manifest.version), f"manifest.version = '{manifest.version}'"):
            errors += 1
        check(True, f"manifest.requires = {manifest.requires}", "INFO")
    except Exception as e:
        check(False, f"get_manifest() failed: {e}")
        errors += 1

    # ---- 4. Type mapping ----
    print("\n[4] Type mapping")
    try:
        from uqal_core.types import CoreType
        mapping = module.get_type_mapping()
        all_covered = True
        for core_type in CoreType:
            covered = core_type.value in mapping
            if not check(covered, f"Maps CoreType.{core_type.name}"):
                warnings += 1
                all_covered = False
        if all_covered:
            check(True, "All core types mapped")
    except Exception as e:
        check(False, f"get_type_mapping() failed: {e}")
        errors += 1

    # ---- 5. Connection schema ----
    print("\n[5] Connection schema")
    try:
        from uqal_core.config.connection_schema import ConnectionSchema
        schema_cls = module.get_connection_schema()
        if not check(
            issubclass(schema_cls, ConnectionSchema),
            f"Returns ConnectionSchema subclass: {schema_cls.__name__}"
        ):
            errors += 1

        fields = schema_cls.all_fields()
        if not check(len(fields) > 0, f"Has {len(fields)} connection fields"):
            errors += 1

        required = [f for f in fields if f.required]
        secrets = [f for f in fields if f.secret]
        check(True, f"Required fields: {[f.name for f in required]}", "INFO")
        check(True, f"Secret fields: {[f.name for f in secrets]}", "INFO")

    except Exception as e:
        check(False, f"get_connection_schema() failed: {e}")
        errors += 1

    # ---- 6. Grammar extension ----
    print("\n[6] Grammar extension")
    try:
        grammar_ext = module.get_grammar_extension()
        has_grammar = bool(grammar_ext.strip())
        check(has_grammar or True, f"Grammar extension: {'yes' if has_grammar else 'none (ok if no extension needed)'}")

        caps = module.get_capabilities()
        grammar_exts = getattr(caps, "grammar_extensions", {})

        if has_grammar:
            # Check that declared rules exist in grammar text
            for point, rules in grammar_exts.items():
                for rule in rules:
                    rule_in_grammar = rule in grammar_ext
                    if not check(
                        rule_in_grammar,
                        f"Rule '{rule}' declared in '{point}' exists in grammar"
                    ):
                        errors += 1

            # Check native command name
            native_cmd = module.get_native_command_name()
            cmd_in_grammar = native_cmd in grammar_ext
            if not check(
                cmd_in_grammar,
                f"Native command '{native_cmd}()' found in grammar"
            ):
                warnings += 1

        # Check grammar builds with this module
        from uqal_core.parser.grammar_builder import GrammarBuilder
        builder = GrammarBuilder()
        try:
            parser = builder.build([module])
            check(True, "Grammar builds successfully with this module")
        except Exception as e:
            check(False, f"Grammar build failed: {e}")
            errors += 1

    except Exception as e:
        check(False, f"Grammar extension check failed: {e}")
        errors += 1

    # ---- 7. Module node registry ----
    print("\n[7] Module node registry")
    try:
        from uqal_core.ast.module_nodes import _MODULE_NODE_REGISTRY
        caps = module.get_capabilities()
        grammar_exts = getattr(caps, "grammar_extensions", {})

        # Check condition extensions are registered
        condition_rules = grammar_exts.get("condition", [])
        if condition_rules:
            for rule in condition_rules:
                registered = rule in _MODULE_NODE_REGISTRY
                if not check(
                    registered,
                    f"Condition rule '{rule}' registered in module_nodes"
                ):
                    errors += 1
        else:
            check(True, "No condition extensions (no registration needed)")

        # Show all registered handlers
        if _MODULE_NODE_REGISTRY:
            check(
                True,
                f"Registered handlers: {list(_MODULE_NODE_REGISTRY.keys())}",
                "INFO"
            )

    except Exception as e:
        check(False, f"Module node registry check failed: {e}")
        errors += 1

    # ---- 8. Capabilities ----
    print("\n[8] Capabilities")
    try:
        caps = module.get_capabilities()
        check(
            caps.module_name == module_name,
            f"capability.module_name = '{caps.module_name}'"
        )
        check(
            bool(caps.provided_types),
            f"provided_types: {caps.provided_types}"
        )
        check(
            bool(caps.translatable_nodes),
            f"translatable_nodes: {caps.translatable_nodes}"
        )
    except Exception as e:
        check(False, f"get_capabilities() failed: {e}")
        errors += 1

    # ---- 9. Grammar extension test parse ----
    print("\n[9] Native command parse test")
    try:
        from uqal_core.parser.grammar_builder import GrammarBuilder
        from uqal_core.ast.transformer import UQALTransformer

        native_cmd = module.get_native_command_name()
        grammar_ext = module.get_grammar_extension()

        if native_cmd and grammar_ext:
            builder = GrammarBuilder()
            parser = builder.build([module])
            transformer = UQALTransformer()

            # Test native command parsing
            test_script = f'testdb.{native_cmd}("test query")'
            try:
                tree = parser.parse(test_script)
                program = transformer.transform(tree)
                check(True, f"Parses: {test_script}")

                from uqal_core.ast.nodes import DbConnectionCall
                stmt = program.statements[0]
                if not check(
                    isinstance(stmt, DbConnectionCall),
                    f"Transforms to DbConnectionCall"
                ):
                    warnings += 1
                if not check(
                    stmt.command == "native_sql",
                    f"Command is 'native_sql'"
                ):
                    warnings += 1
            except Exception as e:
                check(False, f"Parse failed: {e}")
                errors += 1
        else:
            check(True, "No native command (skipping parse test)")

    except Exception as e:
        check(False, f"Parse test failed: {e}")
        errors += 1

    # ---- Summary ----
    print(f"\n{'='*60}")
    print(f"Summary for {module_name}:")
    print(f"  Errors:   {errors}")
    print(f"  Warnings: {warnings}")

    if errors == 0 and warnings == 0:
        print(f"\033[92m  ✓ Module is fully compliant\033[0m")
    elif errors == 0:
        print(f"\033[93m  ⚠ Module has warnings but is functional\033[0m")
    else:
        print(f"\033[91m  ✗ Module has {errors} error(s)\033[0m")
    print(f"{'='*60}\n")

    return errors == 0


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: uv run python scripts/dev/validate_module.py <module_name>")
        print("       uv run python scripts/dev/validate_module.py --all")
        sys.exit(1)

    if sys.argv[1] == "--all":
        from uqal_core.module_loader import ModuleLoader
        from uqal_core.registry.module_registry import ModuleRegistry
        registry = ModuleRegistry()
        loader = ModuleLoader(registry=registry)
        available = loader.list_available()
        print(f"Validating all {len(available)} modules...")
        results = {}
        for module_name in available:
            if module_name == "standard.dummy":
                continue  # Skip dummy
            results[module_name] = validate_module(module_name)

        print("\n" + "="*60)
        print("FINAL RESULTS:")
        for name, passed in results.items():
            status = "\033[92m✓ PASS\033[0m" if passed else "\033[91m✗ FAIL\033[0m"
            print(f"  {status}  {name}")
        print("="*60)
        sys.exit(0 if all(results.values()) else 1)

    else:
        passed = validate_module(sys.argv[1])
        sys.exit(0 if passed else 1)