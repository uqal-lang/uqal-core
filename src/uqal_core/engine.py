"""
UQAL Engine.

The central orchestrator that wires together all core components:
  1. Module loading and registry
  2. Grammar building and parsing
  3. AST transformation
  4. Type checking
  5. Query planning
  6. Execution

This is the main entry point for all three usage modes:
  - CLI command:   engine.run_script("let a = 5")
  - REPL:          engine.run_interactive()
  - Python API:    engine = Engine(); engine.run_script(...)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from uqal_core.ast.transformer import UQALTransformer
from uqal_core.ast.nodes import Program
from uqal_core.execution.executor import Executor
from uqal_core.module_loader import ModuleLoader, ModuleLoadError
from uqal_core.parser.grammar_builder import GrammarBuilder
from uqal_core.planner.query_planner import QueryPlanner
from uqal_core.registry.connection_registry import (
    ConnectionConfig,
    ConnectionRegistry,
)
from uqal_core.registry.module_registry import ModuleRegistry
from uqal_core.typecheck.checker import TypeChecker


@dataclass
class ExecutionResult:
    """
    Result of running a UQAL script or single statement.

    steps contains one entry per top-level statement, each with
    its own status - partial failures are captured here rather
    than aborting the entire script (see specification chapter 12).
    """

    status: str  # "success" | "partial_failure" | "failure"
    steps: list[dict[str, Any]] = field(default_factory=list)

    def is_success(self) -> bool:
        return self.status == "success"

    def failed_steps(self) -> list[dict]:
        return [s for s in self.steps if s.get("status") == "failed"]

    def __repr__(self) -> str:
        return (
            f"ExecutionResult(status={self.status!r}, "
            f"steps={len(self.steps)}, "
            f"failed={len(self.failed_steps())})"
        )


class Engine:
    """
    Main UQAL engine.

    Manages the full lifecycle from script text to execution result.
    Can be used directly as a Python API or driven by the CLI.

    Usage (Python API):
        engine = Engine()
        engine.connect("db1", "postgresql", host="localhost", port=5432)
        engine.load_modules(["standard.postgresql"])
        result = engine.run_script(
            "let a = db1.orders.get_value(where id = 5, field amount)"
        )

    Usage (CLI):
        Driven by uqal_core.cli.commands.run and
        uqal_core.cli.commands.repl
    """

    def __init__(self) -> None:
        self._module_registry = ModuleRegistry()
        self._connection_registry = ConnectionRegistry()
        self._module_loader = ModuleLoader(
            registry=self._module_registry
        )
        self._grammar_builder = GrammarBuilder()
        self._transformer = UQALTransformer()
        self._planner = QueryPlanner()
        self._parser = None  # built lazily after modules are loaded

    # ---- Setup ----

    def load_modules(self, module_names: list[str]) -> None:
        """
        Loads the given modules (plus transitive dependencies).
        Invalidates the cached parser so it is rebuilt with the
        new grammar extensions on the next run_script() call.
        """
        self._module_loader.load(module_names)
        self._grammar_builder.invalidate()
        self._parser = None

    def connect(
        self,
        connection_name: str,
        module_type: str,
        **options: Any,
    ) -> None:
        """
        Registers a database connection.

        Standard fields (host, port, database) are extracted from
        options automatically. Everything else goes into the free
        options dict and is only read by the module itself.
        """
        standard_fields = {"host", "port", "database"}
        standard = {
            k: v for k, v in options.items()
            if k in standard_fields
        }
        extra = {
            k: v for k, v in options.items()
            if k not in standard_fields
        }

        config = ConnectionConfig(
            connection_name=connection_name,
            module_type=module_type,
            host=standard.get("host"),
            port=standard.get("port"),
            database=standard.get("database"),
            options=extra,
        )
        self._connection_registry.register(config)

    def list_connections(self) -> list[str]:
        return self._connection_registry.list_connections()

    def list_available_modules(self) -> list[str]:
        return self._module_loader.list_available()

    def list_loaded_modules(self) -> list[str]:
        return self._module_registry.list_modules()

    # ---- Execution ----

    def run_script(self, script: str) -> ExecutionResult:
        """
        Parses, type-checks, plans, and executes a complete UQAL
        script.

        Returns an ExecutionResult with per-statement status so
        partial failures are visible without losing successful
        results.
        """
        # Step 1: build parser if needed
        parser = self._get_parser()

        # Step 2: parse
        try:
            tree = parser.parse(script)
        except Exception as exc:
            return ExecutionResult(
                status="failure",
                steps=[{
                    "step": 0,
                    "status": "failed",
                    "error": f"Parse error: {exc}",
                }],
            )

        # Step 3: transform to AST
        try:
            program: Program = self._transformer.transform(tree)
        except Exception as exc:
            return ExecutionResult(
                status="failure",
                steps=[{
                    "step": 0,
                    "status": "failed",
                    "error": f"AST transformation error: {exc}",
                }],
            )

        # Step 4: type check
        checker = TypeChecker(
            module_registry=self._module_registry,
            connection_registry=self._connection_registry,
        )
        type_errors = checker.check(program)
        if type_errors:
            return ExecutionResult(
                status="failure",
                steps=[{
                    "step": 0,
                    "status": "failed",
                    "error": "Type errors:\n" + "\n".join(
                        f"  - {e}" for e in type_errors
                    ),
                }],
            )

        # Step 5: plan
        try:
            plan = self._planner.plan(program)
        except Exception as exc:
            return ExecutionResult(
                status="failure",
                steps=[{
                    "step": 0,
                    "status": "failed",
                    "error": f"Planning error: {exc}",
                }],
            )

        # Step 6: execute
        executor = Executor(
            module_registry=self._module_registry,
            connection_registry=self._connection_registry,
        )
        step_results = executor.execute(plan)

        # Step 7: convert to ExecutionResult format
        steps = [
            {
                "step":      r.step_index + 1,
                "status":    r.status,
                "result":    r.result,
                "error":     r.error,
                "is_output": r.is_output,
            }
            for r in step_results
        ]

        any_failed = any(s["status"] == "failed" for s in steps)
        return ExecutionResult(
            status="partial_failure" if any_failed else "success",
            steps=steps,
        )

    def run_statement(self, statement: str) -> ExecutionResult:
        """
        Convenience method for running a single statement.
        Used by the REPL for line-by-line execution.
        """
        return self.run_script(statement)

    # ---- Internal ----

    def _get_parser(self):
        if self._parser is None:
            modules = [
                self._module_registry.get_module(name)
                for name in self._module_registry.list_modules()
            ]
            self._parser = self._grammar_builder.build(modules)
        return self._parser