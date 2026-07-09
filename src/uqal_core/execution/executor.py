"""
Executor.

Takes an ExecutionPlan and runs each Step sequentially, collecting
results and partial failures along the way.

The executor maintains an ExecutionContext - a runtime variable store
that grows as let statements are processed. Each step can read from
and write to this context.

Step dispatch:
  DB_QUERY     → module.translate() + module.execute()
  CORE_COMPUTE → evaluate expression in Python (arithmetic, binding)
  META         → schema introspection from module
  SETUP        → connect / sync_schema
  SYSTEM       → list dbs / list modules
  CONTROL_FLOW → if/for/while with nested block execution
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from uqal_core.ast.nodes import (
    BinaryOp,
    BoolLiteral,
    Compare,
    ConnectCommand,
    DbConnectionCall,
    DbGenericCall,
    DbQueryBlock,
    DbTableCall,
    DbWriteCall,
    FieldParam,
    FieldsParam,
    FloatLiteral,
    ForStatement,
    IfStatement,
    IntegerLiteral,
    IsNotNull,
    IsNull,
    LetStatement,
    ListDbsCommand,
    ListModulesCommand,
    LogicalAnd,
    LogicalNot,
    LogicalOr,
    NameParam,
    Negate,
    NullLiteral,
    StringLiteral,
    SyncSchemaCommand,
    VariableRef,
    WhereParam,
    WhileStatement,
    OutputStatement,
    OutputField,
)
from uqal_core.execution.result_set import ResultSet
from uqal_core.planner.query_planner import ExecutionPlan, Step, StepKind
from uqal_core.registry.connection_registry import ConnectionRegistry
from uqal_core.registry.module_registry import ModuleRegistry


@dataclass
class ExecutionContext:
    """
    Runtime variable store.

    Holds the current value of every let-bound variable.
    Nested scopes (if/for/while) use child contexts so inner
    variables don't leak into outer scope.
    """

    _vars: dict[str, Any] = field(default_factory=dict)
    _parent: "ExecutionContext | None" = None

    def set(self, name: str, value: Any) -> None:
        self._vars[name] = value

    def get(self, name: str) -> Any:
        if name in self._vars:
            return self._vars[name]
        if self._parent is not None:
            return self._parent.get(name)
        raise NameError(
            f"Variable '{name}' is not defined in the current scope."
        )

    def has(self, name: str) -> bool:
        if name in self._vars:
            return True
        if self._parent is not None:
            return self._parent.has(name)
        return False

    def child(self) -> "ExecutionContext":
        return ExecutionContext(_parent=self)

    def all_vars(self) -> dict[str, Any]:
        result = {}
        if self._parent:
            result.update(self._parent.all_vars())
        result.update(self._vars)
        return result


@dataclass
class StepResult:
    """Result of executing a single step."""
    step_index: int
    status: str          # "success" | "failed"
    result: Any = None
    error: str | None = None
    is_output: bool = False


class Executor:
    """
    Executes an ExecutionPlan step by step.

    Usage:
        executor = Executor(module_registry, connection_registry)
        results = executor.execute(plan)
    """

    def __init__(
        self,
        module_registry: ModuleRegistry,
        connection_registry: ConnectionRegistry,
    ) -> None:
        self._modules = module_registry
        self._connections = connection_registry

    def execute(self, plan: ExecutionPlan) -> list[StepResult]:
        """
        Executes all steps in the plan sequentially.
        Returns a list of StepResults - one per step. Failed steps
        are recorded but do not abort subsequent steps (partial
        failure semantics, see specification chapter 12).
        """
        from uqal_core.ast.nodes import OutputStatement

        context = ExecutionContext()
        results: list[StepResult] = []

        for step in plan.steps:
            try:
                value = self._execute_step(step, context)
                if step.result_var:
                    context.set(step.result_var, value)
                results.append(StepResult(
                    step_index=step.index,
                    status="success",
                    result=value,
                    is_output=isinstance(step.node, OutputStatement),
                ))
            except Exception as exc:
                results.append(StepResult(
                    step_index=step.index,
                    status="failed",
                    error=str(exc),
                ))

        return results

    # ---- Step dispatch ----

    def _execute_step(self, step: Step, ctx: ExecutionContext) -> Any:
        if step.kind == StepKind.DB_QUERY:
            return self._execute_db_query(step, ctx)
        if step.kind == StepKind.CORE_COMPUTE:
            return self._execute_core_compute(step, ctx)
        if step.kind == StepKind.META:
            return self._execute_meta(step, ctx)
        if step.kind == StepKind.SETUP:
            return self._execute_setup(step, ctx)
        if step.kind == StepKind.SYSTEM:
            return self._execute_system(step, ctx)
        if step.kind == StepKind.CONTROL_FLOW:
            return self._execute_control_flow(step, ctx)
        if step.kind == StepKind.DDL:
            return self._execute_ddl(step, ctx)
        raise NotImplementedError(
            f"Unknown step kind: {step.kind}"
        )

    # ---- DB Query ----

    def _ensure_connection(self, connection_name: str) -> Any:
        """
        Ensures a native connection exists for the given connection name.
        Builds it lazily on first access and caches it in the registry.
        Returns the native connection object.
        """
        config = self._connections.get(connection_name)

        if config.native_connection is None:
            module = self._modules.get_module_for_connection(
                connection_name
            )
            native_conn = module.build_connection(config)
            self._connections.update_native_connection(
                connection_name, native_conn
            )
            config = self._connections.get(connection_name)

        return config.native_connection


    def _execute_db_query(
        self, step: Step, ctx: ExecutionContext
    ) -> Any:
        connection_name = step.connection
        if not connection_name:
            raise ValueError("DB_QUERY step has no connection.")

        native_conn = self._ensure_connection(connection_name)
        module = self._modules.get_module_for_connection(connection_name)
        native_query = module.translate(step.node)
        result = module.execute(native_query, native_conn)

        # Auto-unwrap scalars and single rows
        if isinstance(step.node, DbTableCall):
            if step.node.command == "get_value":
                # Return the first field of the first row as a scalar
                if not result.is_empty():
                    first_row = result._rows[0]
                    first_key = list(first_row.keys())[0]
                    return first_row[first_key]
                return None
            elif step.node.command == "get_row":
                # Return the first row as a dict
                if not result.is_empty():
                    return result._rows[0]
                return None

        return result

    # ---- Core compute ----

    def _execute_core_compute(
        self, step: Step, ctx: ExecutionContext
    ) -> Any:
        node = step.node

        if isinstance(node, OutputStatement):
            results = {}
            for field in node.fields:
                try:
                    results[field.name] = ctx.get(field.name)
                except NameError:
                    results[field.name] = None
            return results

        if isinstance(node, LetStatement):
            return self._eval_expression(node.value, ctx)

        return self._eval_expression(node, ctx)
        

    def _eval_expression(self, node: Any, ctx: ExecutionContext) -> Any:
        if isinstance(node, IntegerLiteral):
            return node.value
        if isinstance(node, FloatLiteral):
            return node.value
        if isinstance(node, StringLiteral):
            return node.value
        if isinstance(node, BoolLiteral):
            return node.value
        if isinstance(node, NullLiteral):
            return None
        if isinstance(node, BinaryOp):
            return self._eval_binary_op(node, ctx)
        if isinstance(node, Negate):
            return -self._eval_expression(node.operand, ctx)
        if isinstance(node, VariableRef):
            return self._eval_variable_ref(node, ctx)
        if isinstance(node, (DbTableCall, DbGenericCall, DbQueryBlock)):
            # Inline DB call within an expression
            from uqal_core.planner.query_planner import Step as PStep
            from uqal_core.planner.query_planner import StepKind
            pseudo_step = PStep(
                index=-1,
                kind=StepKind.DB_QUERY,
                node=node,
                connection=getattr(node, "connection", None),
            )
            return self._execute_db_query(pseudo_step, ctx)
        return None

    def _eval_binary_op(self, node: BinaryOp, ctx: ExecutionContext) -> Any:
        left = self._eval_expression(node.left, ctx)
        right = self._eval_expression(node.right, ctx)
        op = node.operator
        if op == "+":
            return left + right
        if op == "-":
            return left - right
        if op == "*":
            return left * right
        if op == "/":
            if right == 0:
                raise ZeroDivisionError("Division by zero.")
            return left / right
        raise ValueError(f"Unknown operator: {op}")

    def _eval_variable_ref(
        self, node: VariableRef, ctx: ExecutionContext
    ) -> Any:
        if not node.parts:
            return None
        base = node.parts[0]
        if not isinstance(base, str):
            return None
        value = ctx.get(base)
        # Handle field access: a.field, a.row(0), etc.
        for part in node.parts[1:]:
            if isinstance(part, str):
                if isinstance(value, ResultSet):
                    # a.field → first row's field
                    if not value.is_empty():
                        value = value.row(0).value(part)
                    else:
                        value = None
                elif isinstance(value, dict):
                    value = value.get(part)
                else:
                    value = getattr(value, part, None)
        return value

    def _eval_condition(
        self, condition: Any, ctx: ExecutionContext
    ) -> bool:
        if isinstance(condition, BoolLiteral):
            return condition.value
        if isinstance(condition, Compare):
            left = self._eval_expression(condition.left, ctx)
            right = self._eval_expression(condition.right, ctx)
            op = condition.operator
            if op in ("=", "=="):
                return left == right
            if op == "!=":
                return left != right
            if op == ">":
                return left > right
            if op == "<":
                return left < right
            if op == ">=":
                return left >= right
            if op == "<=":
                return left <= right
        if isinstance(condition, LogicalAnd):
            return (
                self._eval_condition(condition.left, ctx)
                and self._eval_condition(condition.right, ctx)
            )
        if isinstance(condition, LogicalOr):
            return (
                self._eval_condition(condition.left, ctx)
                or self._eval_condition(condition.right, ctx)
            )
        if isinstance(condition, LogicalNot):
            return not self._eval_condition(condition.operand, ctx)
        if isinstance(condition, IsNull):
            return self._eval_expression(condition.operand, ctx) is None
        if isinstance(condition, IsNotNull):
            return self._eval_expression(condition.operand, ctx) is not None
        return False

    # ---- Meta ----

    def _execute_meta(
        self, step: Step, ctx: ExecutionContext
    ) -> Any:
        node = step.node
        connection_name = step.connection or ""

        if isinstance(node, DbConnectionCall):
            if node.command == "list_tables":
                live = any(
                    isinstance(p, NameParam)
                    and p.name == "live"
                    and p.value
                    for p in node.params
                )
                if live and self._modules.has_module_for_connection(
                    connection_name
                ):
                    native_conn = self._ensure_connection(connection_name)
                    module = self._modules.get_module_for_connection(
                        connection_name
                    )
                    schema = module.sync_schema_from_source(native_conn)
                    self._modules.store_schema(connection_name, schema)
                    return schema.list_tables()
                else:
                    try:
                        schema = self._modules.get_schema(connection_name)
                        return schema.list_tables()
                    except KeyError:
                        return []

            if node.command == "schema":
                try:
                    schema = self._modules.get_schema(connection_name)
                    table_name = step.metadata.get("table", "")
                    if table_name:
                        table = schema.get_table(table_name)
                        return {f.name: f.type for f in table.fields}
                    return schema.list_tables()
                except KeyError:
                    return []

            if node.command == "native_sql":
                query_param = next(
                    (p for p in node.params
                    if isinstance(p, NameParam) and p.name == "query"),
                    None,
                )
                if query_param is None:
                    raise ValueError("native_sql has no query parameter.")

                query = query_param.value.value  # StringLiteral.value
                native_conn = self._ensure_connection(connection_name)
                module = self._modules.get_module_for_connection(connection_name)

                errors = module.validate_native_query(query)
                if errors:
                    raise ValueError(
                        f"Native query validation failed: {errors}"
                    )

                return module.execute_native(query, native_conn)

        return None

    # ---- Setup ----

    def _execute_setup(
        self, step: Step, ctx: ExecutionContext
    ) -> Any:
        node = step.node

        if isinstance(node, ConnectCommand):
            params = {
                p.name: self._eval_expression(p.value, ctx)
                for p in node.params
            }
            from uqal_core.registry.connection_registry import ConnectionConfig
            config = ConnectionConfig(
                connection_name=node.connection_name,
                module_type=node.module_type,
                module_names=[node.module_type],
                host=params.pop("host", None),
                port=params.pop("port", None),
                database=params.pop("database", None),
                options=params,
            )
            if not self._connections.has(node.connection_name):
                self._connections.register(config)
            return f"Connected: {node.connection_name}"

        if isinstance(node, (SyncSchemaCommand, DbConnectionCall)):
            connection_name = (
                node.connection
                if hasattr(node, "connection")
                else step.connection or ""
            )
            if self._connections.has(connection_name):
                native_conn = self._ensure_connection(connection_name)
                module = self._modules.get_module_for_connection(
                    connection_name
                )
                schema = module.sync_schema_from_source(native_conn)
                self._modules.store_schema(connection_name, schema)
                return f"Schema synced: {connection_name}"

        return None


    # ---- System ----

    def _execute_system(
        self, step: Step, ctx: ExecutionContext
    ) -> Any:
        node = step.node
        if isinstance(node, ListDbsCommand):
            return self._connections.list_connections()
        if isinstance(node, ListModulesCommand):
            return self._modules.list_modules()
        return None

    # ---- Control flow ----

    def _execute_control_flow(
        self, step: Step, ctx: ExecutionContext
    ) -> Any:
        node = step.node

        if isinstance(node, IfStatement):
            condition_result = self._eval_condition(
                node.condition, ctx
            )
            if condition_result:
                child_ctx = ctx.child()
                for stmt in node.then_block:
                    from uqal_core.planner.query_planner import (
                        QueryPlanner,
                    )
                    from uqal_core.ast.nodes import Program
                    sub_plan = QueryPlanner().plan(
                        Program(statements=[stmt])
                    )
                    self.execute_in_context(sub_plan, child_ctx)
            else:
                for cond, block in node.elif_clauses:
                    if self._eval_condition(cond, ctx):
                        child_ctx = ctx.child()
                        from uqal_core.planner.query_planner import (
                            QueryPlanner,
                        )
                        from uqal_core.ast.nodes import Program
                        for stmt in block:
                            sub_plan = QueryPlanner().plan(
                                Program(statements=[stmt])
                            )
                            self.execute_in_context(
                                sub_plan, child_ctx
                            )
                        break
                else:
                    if node.else_block:
                        child_ctx = ctx.child()
                        from uqal_core.planner.query_planner import (
                            QueryPlanner,
                        )
                        from uqal_core.ast.nodes import Program
                        for stmt in node.else_block:
                            sub_plan = QueryPlanner().plan(
                                Program(statements=[stmt])
                            )
                            self.execute_in_context(
                                sub_plan, child_ctx
                            )

        elif isinstance(node, ForStatement):
            iterable = self._eval_expression(node.iterable, ctx)
            if isinstance(iterable, ResultSet):
                rows = list(iterable)
            elif isinstance(iterable, (list, tuple)):
                rows = iterable
            else:
                rows = [iterable]

            from uqal_core.planner.query_planner import QueryPlanner
            from uqal_core.ast.nodes import Program
            for item in rows:
                child_ctx = ctx.child()
                child_ctx.set(node.variable, item)
                for stmt in node.body:
                    sub_plan = QueryPlanner().plan(
                        Program(statements=[stmt])
                    )
                    self.execute_in_context(sub_plan, child_ctx)

        elif isinstance(node, WhileStatement):
            from uqal_core.planner.query_planner import QueryPlanner
            from uqal_core.ast.nodes import Program
            max_iterations = 10_000
            iterations = 0
            while self._eval_condition(node.condition, ctx):
                if iterations >= max_iterations:
                    raise RuntimeError(
                        f"While loop exceeded {max_iterations} "
                        f"iterations - possible infinite loop."
                    )
                child_ctx = ctx.child()
                for stmt in node.body:
                    sub_plan = QueryPlanner().plan(
                        Program(statements=[stmt])
                    )
                    self.execute_in_context(sub_plan, child_ctx)
                iterations += 1

        return None

    def execute_in_context(
        self, plan: ExecutionPlan, ctx: ExecutionContext
    ) -> list[StepResult]:
        """
        Executes a sub-plan within an existing context.
        Used for nested blocks (if/for/while bodies).
        """
        results: list[StepResult] = []
        for step in plan.steps:
            try:
                value = self._execute_step(step, ctx)
                if step.result_var:
                    ctx.set(step.result_var, value)
                results.append(StepResult(
                    step_index=step.index,
                    status="success",
                    result=value,
                ))
            except Exception as exc:
                results.append(StepResult(
                    step_index=step.index,
                    status="failed",
                    error=str(exc),
                ))
        return results
    
    def _execute_ddl(
        self, step: Step, ctx: ExecutionContext
    ) -> Any:
        from uqal_core.ast.nodes import CreateViewStatement

        node = step.node

        if isinstance(node, CreateViewStatement):
            native_conn = self._ensure_connection(node.connection)
            module = self._modules.get_module_for_connection(
                node.connection
            )
            result = module.create_view(
                view_name=node.view_name,
                aliases=node.aliases,
                returns=node.returns,
                connection=native_conn,
            )
            return f"View '{result}' created on '{node.connection}'."

        raise NotImplementedError(
            f"Unknown DDL node: {type(node).__name__}"
        )