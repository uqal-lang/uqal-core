"""
Module loader.

Discovers modules in two stages (see language specification,
chapter 10 "Module dependencies"):

  Stage 1 - Entry points:
    Finds all installed packages that registered themselves as UQAL
    modules via the "uqal.modules" entry point group.

  Stage 2 - Local fallback:
    If a requested module was not found via entry points, looks in
    src/uqal_core/modules/ relative to this file. Allows testing
    modules during development without installing them as packages
    and without specifying any absolute path.
"""

from __future__ import annotations

import importlib.util
import inspect
import sys
from graphlib import TopologicalSorter
from importlib.metadata import entry_points
from pathlib import Path
from typing import Type

from uqal_core.module_interface import UQALModule
from uqal_core.registry.module_registry import ModuleRegistry
from uqal_core.types import CoreType

_BUILTIN_MODULES_PATH = Path(__file__).parent / "modules"


class ModuleLoadError(Exception):
    """
    Raised when a module cannot be loaded due to missing dependencies,
    failed validation, or an invalid implementation.
    """
    pass


class ModuleLoader:
    """
    Discovers and loads UQAL modules via entry points or the built-in
    modules/ fallback directory.

    Usage:
        loader = ModuleLoader(registry=ModuleRegistry())
        loader.load(["postgresql", "postgis"])
    """

    def __init__(self, registry: ModuleRegistry) -> None:
        self._registry = registry
        self._discovered: dict[str, Type[UQALModule]] = {}

    # ---- Public API ----

    def load(self, module_names: list[str]) -> None:
        """
        Loads the given modules plus all transitive dependencies in
        the correct order determined by topological sort.
        """
        self._run_discovery()
        to_load = self._resolve_with_dependencies(module_names)

        dependency_graph: dict[str, set[str]] = {}
        for name in to_load:
            cls = self._get_discovered(name)
            manifest = cls().get_manifest()
            dependency_graph[name] = set(manifest.requires)

        load_order = list(TopologicalSorter(dependency_graph).static_order())

        for module_name in load_order:
            if module_name not in to_load:
                continue
            cls = self._get_discovered(module_name)
            instance = cls()
            self._validate(instance)
            self._registry.register_module(instance)

    def list_available(self) -> list[str]:
        """
        Returns all module names currently discoverable without
        loading any of them. Used by "uqal list-modules".
        """
        self._run_discovery()
        return sorted(self._discovered.keys())

    # ---- Discovery ----

    def _run_discovery(self) -> None:
        self._discover_from_entry_points()
        self._discover_from_builtin_path()

    def _discover_from_entry_points(self) -> None:
        """
        Stage 1: finds all packages installed in the current
        environment that registered themselves under the
        "uqal.modules" entry point group.

        A module package registers itself by adding this to its
        pyproject.toml:

            [project.entry-points."uqal.modules"]
            postgresql = "uqal_postgresql.module:PostgreSQLModule"
        """
        eps = entry_points(group="uqal.modules")
        for ep in eps:
            if ep.name in self._discovered:
                continue
            try:
                cls = ep.load()
                if inspect.isclass(cls) and issubclass(cls, UQALModule):
                    self._discovered[ep.name] = cls
            except Exception as exc:
                raise ModuleLoadError(
                    f"Failed to load entry point '{ep.name}' "
                    f"from '{ep.value}': {exc}"
                ) from exc

    def _discover_from_builtin_path(self) -> None:
        """
        Stage 2: walks src/uqal_core/modules/ looking for
        subdirectories that contain a module.py with a UQALModule
        subclass.

        Expected structure:
            src/uqal_core/modules/
                standard/
                    postgresql/
                        module.py
                community/
                    postgis/
                        module.py
        """
        if not _BUILTIN_MODULES_PATH.exists():
            return

        for module_py in _BUILTIN_MODULES_PATH.rglob("module.py"):
            module_name = self._path_to_name(module_py)
            if module_name in self._discovered:
                continue
            cls = self._load_class_from_file(module_py, module_name)
            if cls is not None:
                self._discovered[module_name] = cls

    def _path_to_name(self, module_py: Path) -> str:
        """
        Converts a file path relative to modules/ into a dot-notation
        name, e.g.:
            .../modules/standard/postgresql/module.py -> standard.postgresql
        """
        relative = module_py.parent.relative_to(_BUILTIN_MODULES_PATH)
        return str(relative).replace("\\", "/").replace("/", ".")

    def _load_class_from_file(
        self, path: Path, module_name: str
    ) -> Type[UQALModule] | None:
        spec = importlib.util.spec_from_file_location(
            f"uqal_builtin.{module_name}", path
        )
        if spec is None or spec.loader is None:
            return None

        py_module = importlib.util.module_from_spec(spec)
        sys.modules[f"uqal_builtin.{module_name}"] = py_module

        try:
            spec.loader.exec_module(py_module)
        except Exception as exc:
            raise ModuleLoadError(
                f"Failed to import module '{module_name}' "
                f"from '{path}': {exc}"
            ) from exc

        for _, obj in inspect.getmembers(py_module, inspect.isclass):
            if issubclass(obj, UQALModule) and obj is not UQALModule:
                return obj

        return None

    # ---- Dependency resolution ----

    def _resolve_with_dependencies(
        self, requested: list[str]
    ) -> set[str]:
        to_load: set[str] = set()
        queue = list(requested)

        while queue:
            name = queue.pop()
            if name in to_load:
                continue
            to_load.add(name)
            cls = self._get_discovered(name)
            for dep in cls().get_manifest().requires:
                if dep not in to_load:
                    queue.append(dep)

        return to_load

    def _get_discovered(self, module_name: str) -> Type[UQALModule]:
        if module_name not in self._discovered:
            raise ModuleLoadError(
                f"Module '{module_name}' was not found via entry "
                f"points or in the built-in modules/ directory. "
                f"Available modules: {sorted(self._discovered.keys())}. "
                f"Install it with 'uv add uqal-{module_name}' or use "
                f"'uqal add-module <path>' to add it manually."
            )
        return self._discovered[module_name]

    # ---- Validation ----

    def _validate(self, instance: UQALModule) -> None:
        manifest = instance.get_manifest()
        self._validate_type_mapping(instance, manifest.name)
        self._validate_dependencies_loaded(manifest)

    def _validate_type_mapping(
        self, instance: UQALModule, module_name: str
    ) -> None:
        mapping = instance.get_type_mapping()
        missing = [
            t.value for t in CoreType
            if t.value not in mapping
        ]
        if missing:
            raise ModuleLoadError(
                f"Module '{module_name}' is missing type mappings "
                f"for: {missing}. Every module must provide a mapping "
                f"for all core base types: {[t.value for t in CoreType]}."
            )

    def _validate_dependencies_loaded(
        self, manifest: "ModuleManifest"
    ) -> None:
        for dep in manifest.requires:
            if not self._registry.has_module(dep):
                raise ModuleLoadError(
                    f"Module '{manifest.name}' requires '{dep}' to be "
                    f"loaded first, but '{dep}' is not yet in the registry."
                )