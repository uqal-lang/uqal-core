"""
Query planner.

Transforms a type-checked AST (Program) into an ExecutionPlan - an
ordered list of Steps that the executor can run sequentially.

The planner answers three questions for each AST node:
  1. Where does it run? (which connection/module, or in-core)
  2. What does it depend on? (which previous steps must finish first)
  3. What kind of operation is it? (read, write, meta, compute, ...)

Two fundamental step kinds (see language specification chapter 6):

  DB_QUERY   - a native database operation, passed as-is to the
               module's translate() + execute() methods. Includes
               both single-line calls and db.query: blocks.

  CORE_COMPUTE - an in-core operation (arithmetic, variable binding,
                 control flow). Never touches a database.

Cross-DB joins are a special case: two DB_QUERY steps whose results
are combined by a subsequent CORE_COMPUTE step.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from uqal_core.ast.nodes import (
    BinaryOp,
    BoolLiteral,
    ConnectCommand,
    CreateViewStatement,
    DbConnectionCall,
    DbGenericCall,
    DbQueryBlock,
    DbTableCall,
    DbWriteCall,
    FloatLiteral,
    ForStatement,
    IfStatement,
    IntegerLiteral,
    LetStatement,
    ListDbsCommand,
    ListModulesCommand,
    NullLiteral,
    Program,
    StringLiteral,
    SyncSchemaCommand,
    VariableRef,
    WhileStatement,
    OutputStatement,
    OutputField,
)


class StepKind(Enum):
    DB_QUERY     = "db_query"      # native DB operation
    CORE_COMPUTE = "core_compute"  # in-core calculation or binding
    META         = "meta"          # schema/connection introspection
    SETUP        = "setup"         # connect, sync_schema
    SYSTEM       = "system"        # list dbs, list modules
    CONTROL_FLOW = "control_flow"  # if, for, while
    DDL          = "ddl"           # create/drop view, create/drop table


@dataclass
class Step:
    """
    A single executable unit in the plan.

    connection is None for CORE_COMPUTE, META (without a connection),
    SYSTEM, and CONTROL_FLOW steps.

    depends_on lists the indices of steps that must complete before
    this step can run. The executor uses this to detect cross-DB
    joins (two DB_QUERY steps whose results feed a CORE_COMPUTE step).

    result_var is the variable name this step's result should be
    bound to in the execution context (from a let statement), or
    None if the result is discarded.
    """

    index: int
    kind: StepKind
    node: Any                          # the original AST node
    connection: str | None = None      # which DB connection
    result_var: str | None = None      # let binding target
    depends_on: list[int] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)

    def is_db_step(self) -> bool:
        return self.kind == StepKind.DB_QUERY

    def is_cross_db(self, other: "Step") -> bool:
        """
        Returns True if this step and another DB step reference
        different connections - meaning their results must be joined
        in-core, not in a database.
        """
        return (
            self.is_db_step()
            and other.is_db_step()
            and self.connection is not None
            and other.connection is not None
            and self.connection != other.connection
        )


@dataclass
class ExecutionPlan:
    """
    An ordered list of steps ready for the executor.

    steps are in dependency order: a step always appears after all
    steps it depends on.
    """

    steps: list[Step] = field(default_factory=list)

    def db_steps(self) -> list[Step]:
        return [s for s in self.steps if s.is_db_step()]

    def core_steps(self) -> list[Step]:
        return [s for s in self.steps if s.kind == StepKind.CORE_COMPUTE]

    def __repr__(self) -> str:
        return (
            f"ExecutionPlan("
            f"{len(self.steps)} steps, "
            f"{len(self.db_steps())} db, "
            f"{len(self.core_steps())} core)"
        )


class QueryPlanner:
    """
    Converts a type-checked Program AST into an ExecutionPlan.

    Usage:
        planner = QueryPlanner()
        plan = planner.plan(program)
        for step in plan.steps:
            executor.run(step)
    """

    def __init__(self) -> None:
        self._steps: list[Step] = []
        # Maps variable name -> step index that produced it
        # Used to resolve dependencies between steps
        self._var_to_step: dict[str, int] = {}

    def plan(self, program: Program) -> ExecutionPlan:
        """
        Main entry point. Returns a complete ExecutionPlan for the
        given program.
        """
        self._steps = []
        self._var_to_step = {}

        for statement in program.statements:
            self._plan_statement(statement)

        return ExecutionPlan(steps=self._steps)

    # ---- Step creation helpers ----

    def _add_step(
        self,
        kind: StepKind,
        node: Any,
        connection: str | None = None,
        result_var: str | None = None,
        depends_on: list[int] | None = None,
        metadata: dict | None = None,
    ) -> int:
        index = len(self._steps)
        step = Step(
            index=index,
            kind=kind,
            node=node,
            connection=connection,
            result_var=result_var,
            depends_on=depends_on or [],
            metadata=metadata or {},
        )
        self._steps.append(step)
        if result_var:
            self._var_to_step[result_var] = index
        return index

    def _resolve_deps(self, node: Any) -> list[int]:
        """
        Walks an expression node and collects indices of steps whose
        results are referenced (via VariableRef).
        """
        deps: list[int] = []
        self._collect_deps(node, deps)
        return deps

    def _collect_deps(self, node: Any, deps: list[int]) -> None:
        if isinstance(node, VariableRef):
            base = node.parts[0] if node.parts else None
            if isinstance(base, str) and base in self._var_to_step:
                idx = self._var_to_step[base]
                if idx not in deps:
                    deps.append(idx)
        elif isinstance(node, BinaryOp):
            self._collect_deps(node.left, deps)
            self._collect_deps(node.right, deps)
        elif isinstance(node, (DbTableCall, DbGenericCall)):
            # DB call result used inline - no prior step dependency
            pass

    # ---- Statement planning ----

    def _plan_statement(self, stmt: Any) -> None:
        if isinstance(stmt, LetStatement):
            self._plan_let(stmt)
        elif isinstance(stmt, IfStatement):
            self._plan_if(stmt)
        elif isinstance(stmt, ForStatement):
            self._plan_for(stmt)
        elif isinstance(stmt, WhileStatement):
            self._plan_while(stmt)
        elif isinstance(stmt, DbTableCall):
            self._add_step(
                StepKind.DB_QUERY,
                node=stmt,
                connection=stmt.connection,
            )
        elif isinstance(stmt, DbWriteCall):
            self._add_step(
                StepKind.DB_QUERY,
                node=stmt,
                connection=stmt.connection,
                metadata={"command": stmt.command},
            )
        elif isinstance(stmt, DbGenericCall):
            self._add_step(
                StepKind.DB_QUERY,
                node=stmt,
                connection=stmt.connection,
            )
        elif isinstance(stmt, DbQueryBlock):
            self._add_step(
                StepKind.DB_QUERY,
                node=stmt,
                connection=stmt.connection,
                metadata={"block": True},
            )
        elif isinstance(stmt, DbConnectionCall):
            kind = (
                StepKind.SETUP
                if stmt.command == "sync_schema"
                else StepKind.META
            )
            self._add_step(
                kind,
                node=stmt,
                connection=stmt.connection,  # ← muss "testdb" sein
                metadata={"command": stmt.command},
            )
        elif isinstance(stmt, SyncSchemaCommand):
            self._add_step(
                StepKind.SETUP,
                node=stmt,
                connection=stmt.connection,
                metadata={"command": "sync_schema"},
            )
        elif isinstance(stmt, ConnectCommand):
            self._add_step(
                StepKind.SETUP,
                node=stmt,
                metadata={"command": "connect"},
            )
        elif isinstance(stmt, (ListDbsCommand, ListModulesCommand)):
            self._add_step(
                StepKind.SYSTEM,
                node=stmt,
            )
        elif isinstance(stmt, OutputStatement):
            deps = [
                self._var_to_step[f.name]
                for f in stmt.fields
                if f.name in self._var_to_step
            ]
            self._add_step(
                StepKind.CORE_COMPUTE,
                node=stmt,
                depends_on=deps,
                metadata={"kind": "output"},
            )
        elif isinstance(stmt, CreateViewStatement):
            self._add_step(
                StepKind.DDL,
                node=stmt,
                connection=stmt.connection,
                metadata={"kind": "create_view", "view_name": stmt.view_name},
            )

    # ---- Let planning ----

    def _plan_let(self, stmt: LetStatement) -> None:
        value = stmt.value

        if isinstance(value, DbTableCall):
            self._add_step(
                StepKind.DB_QUERY,
                node=value,
                connection=value.connection,
                result_var=stmt.name,
                metadata={"command": value.command},
            )

        elif isinstance(value, DbWriteCall):
            self._add_step(
                StepKind.DB_QUERY,
                node=value,
                connection=value.connection,
                result_var=stmt.name,
                metadata={"command": value.command},
            )

        elif isinstance(value, DbGenericCall):
            self._add_step(
                StepKind.DB_QUERY,
                node=value,
                connection=value.connection,
                result_var=stmt.name,
            )

        elif isinstance(value, DbQueryBlock):
            # A db.query: block is one atomic DB operation
            self._add_step(
                StepKind.DB_QUERY,
                node=value,
                connection=value.connection,
                result_var=stmt.name,
                metadata={"block": True},
            )

        else:
            # Scalar expression or cross-DB computation
            deps = self._resolve_deps(value)
            self._add_step(
                StepKind.CORE_COMPUTE,
                node=stmt,
                result_var=stmt.name,
                depends_on=deps,
            )

    # ---- Control flow planning ----

    def _plan_if(self, stmt: IfStatement) -> None:
        deps = self._resolve_deps(stmt.condition)
        idx = self._add_step(
            StepKind.CONTROL_FLOW,
            node=stmt,
            depends_on=deps,
            metadata={"kind": "if"},
        )
        # Plan nested blocks - they are sub-steps conceptually
        # but we flatten them into the same list for the executor
        for s in stmt.then_block:
            self._plan_statement(s)
        for _, block in stmt.elif_clauses:
            for s in block:
                self._plan_statement(s)
        if stmt.else_block:
            for s in stmt.else_block:
                self._plan_statement(s)

    def _plan_for(self, stmt: ForStatement) -> None:
        deps = self._resolve_deps(stmt.iterable)
        self._add_step(
            StepKind.CONTROL_FLOW,
            node=stmt,
            depends_on=deps,
            metadata={"kind": "for", "variable": stmt.variable},
        )
        for s in stmt.body:
            self._plan_statement(s)

    def _plan_while(self, stmt: WhileStatement) -> None:
        self._add_step(
            StepKind.CONTROL_FLOW,
            node=stmt,
            metadata={"kind": "while"},
        )
        for s in stmt.body:
            self._plan_statement(s)