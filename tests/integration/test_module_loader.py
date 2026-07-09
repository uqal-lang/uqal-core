"""Integration tests for uqal_core.module_loader"""
import pytest
from uqal_core.module_loader import ModuleLoadError, ModuleLoader
from uqal_core.registry.module_registry import ModuleRegistry

pytestmark = pytest.mark.integration


def make_loader() -> tuple[ModuleLoader, ModuleRegistry]:
    registry = ModuleRegistry()
    loader = ModuleLoader(registry=registry)
    return loader, registry


def test_list_available_includes_dummy():
    loader, _ = make_loader()
    available = loader.list_available()
    assert "standard.dummy" in available


def test_load_dummy_module():
    loader, registry = make_loader()
    loader.load(["standard.dummy"])
    assert "standard.dummy" in registry.list_modules()


def test_load_unknown_module_raises():
    loader, _ = make_loader()
    with pytest.raises(ModuleLoadError, match="not found"):
        loader.load(["nonexistent.module"])


def test_loaded_module_has_valid_type_mapping():
    loader, registry = make_loader()
    loader.load(["standard.dummy"])
    module = registry.get_module("standard.dummy")
    mapping = module.get_type_mapping()
    from uqal_core.types import CoreType
    for core_type in CoreType:
        assert core_type.value in mapping, (
            f"Missing type mapping for {core_type.value}"
        )


def test_loaded_module_has_schema():
    loader, registry = make_loader()
    loader.load(["standard.dummy"])
    module = registry.get_module("standard.dummy")
    schema = module.get_schema_store()
    assert "dummy_table" in schema.list_tables()


def test_loader_caches_discovery():
    loader, _ = make_loader()
    first = loader.list_available()
    second = loader.list_available()
    assert first == second
