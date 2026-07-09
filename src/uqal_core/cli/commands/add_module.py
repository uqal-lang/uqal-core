"""
CLI command: uqal add-module <path>

Scans a given path for a valid UQAL module, validates it, and copies
it into src/uqal_core/modules/community/ so the ModuleLoader can
find it automatically on the next run.

The original path is never modified - only a copy is made.
"""

from __future__ import annotations

import importlib.util
import inspect
import shutil
import sys
from pathlib import Path

import click

from uqal_core.module_interface import UQALModule
from uqal_core.module_loader import ModuleLoadError, _BUILTIN_MODULES_PATH
from uqal_core.types import CoreType

# Always relative to the installed package - never an absolute user path.
_COMMUNITY_PATH = _BUILTIN_MODULES_PATH / "community"


def _load_module_class(path: Path) -> type[UQALModule] | None:
    """
    Tries to import module.py from the given path and returns the
    first UQALModule subclass found, or None if none exists.
    """
    module_py = path / "module.py"
    if not module_py.exists():
        return None

    spec = importlib.util.spec_from_file_location(
        f"uqal_scan.{path.name}", module_py
    )
    if spec is None or spec.loader is None:
        return None

    py_module = importlib.util.module_from_spec(spec)
    sys.modules[f"uqal_scan.{path.name}"] = py_module

    try:
        spec.loader.exec_module(py_module)
    except Exception as exc:
        raise ModuleLoadError(
            f"Failed to import '{module_py}': {exc}"
        ) from exc

    for _, obj in inspect.getmembers(py_module, inspect.isclass):
        if issubclass(obj, UQALModule) and obj is not UQALModule:
            return obj

    return None


def _validate_class(cls: type[UQALModule]) -> list[str]:
    """
    Runs pre-copy validation. Returns a list of error strings - empty
    list means the module is valid and safe to copy.
    """
    errors: list[str] = []

    try:
        instance = cls()
    except Exception as exc:
        errors.append(f"Could not instantiate module class: {exc}")
        return errors

    # Manifest
    try:
        manifest = instance.get_manifest()
        if not manifest.name:
            errors.append("Manifest name is empty.")
        if not manifest.version:
            errors.append("Manifest version is empty.")
    except Exception as exc:
        errors.append(f"get_manifest() raised an error: {exc}")

    # Type mapping
    try:
        mapping = instance.get_type_mapping()
        missing = [
            t.value for t in CoreType
            if t.value not in mapping
        ]
        if missing:
            errors.append(
                f"get_type_mapping() is missing entries for: {missing}. "
                f"All core base types must be covered: "
                f"{[t.value for t in CoreType]}."
            )
    except Exception as exc:
        errors.append(f"get_type_mapping() raised an error: {exc}")

    # Capabilities
    try:
        instance.get_capabilities()
    except Exception as exc:
        errors.append(f"get_capabilities() raised an error: {exc}")

    # Grammar extension (allowed to return empty string, must not crash)
    try:
        instance.get_grammar_extension()
    except Exception as exc:
        errors.append(f"get_grammar_extension() raised an error: {exc}")

    return errors


@click.command("add-module")
@click.argument("path", type=click.Path(exists=True, file_okay=False))
@click.option(
    "--name",
    default=None,
    help=(
        "Override the module name used as the target folder name. "
        "Defaults to the source folder name."
    ),
)
@click.option(
    "--force",
    is_flag=True,
    default=False,
    help="Overwrite if a module with the same name already exists.",
)
def add_module(path: str, name: str | None, force: bool) -> None:
    """
    Scan PATH for a valid UQAL module and copy it into the community
    modules directory so the ModuleLoader can find it automatically.

    PATH must be a directory containing a module.py file with a class
    that inherits from UQALModule.

    Examples:

        uqal add-module ./my_custom_module

        uqal add-module ./my_custom_module --name my_db

        uqal add-module ./my_custom_module --force
    """
    source = Path(path).resolve()
    module_name = name or source.name

    click.echo(f"Scanning '{source}' ...")

    # Step 1: find module.py
    if not (source / "module.py").exists():
        click.echo(
            click.style(
                f"Error: No module.py found in '{source}'. "
                f"A valid UQAL module directory must contain a module.py "
                f"with a class that inherits from UQALModule.",
                fg="red",
            )
        )
        raise SystemExit(1)

    # Step 2: load the class
    try:
        cls = _load_module_class(source)
    except ModuleLoadError as exc:
        click.echo(click.style(f"Error: {exc}", fg="red"))
        raise SystemExit(1)