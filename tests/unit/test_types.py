"""Tests for uqal_core.types"""
import pytest
from uqal_core.types import CoreType, get_core_type, is_core_type_name, python_value_matches

pytestmark = pytest.mark.unit


def test_all_core_types_exist():
    expected = {"integer", "float", "string", "boolean", "datetime", "list"}
    actual = {t.value for t in CoreType}
    assert actual == expected


def test_is_core_type_name_valid():
    assert is_core_type_name("integer") is True
    assert is_core_type_name("string") is True
    assert is_core_type_name("boolean") is True


def test_is_core_type_name_invalid():
    assert is_core_type_name("postgis.geo") is False
    assert is_core_type_name("varchar") is False
    assert is_core_type_name("") is False


def test_get_core_type_valid():
    assert get_core_type("integer") == CoreType.INTEGER
    assert get_core_type("string") == CoreType.STRING


def test_get_core_type_invalid():
    with pytest.raises(ValueError, match="not a core base type"):
        get_core_type("postgis.geo")


def test_python_value_matches_integer():
    assert python_value_matches(CoreType.INTEGER, 5) is True
    assert python_value_matches(CoreType.INTEGER, "hello") is False
    # bool is a subclass of int but must NOT match INTEGER
    assert python_value_matches(CoreType.INTEGER, True) is False


def test_python_value_matches_string():
    assert python_value_matches(CoreType.STRING, "hello") is True
    assert python_value_matches(CoreType.STRING, 5) is False


def test_python_value_matches_boolean():
    assert python_value_matches(CoreType.BOOLEAN, True) is True
    assert python_value_matches(CoreType.BOOLEAN, False) is True
    assert python_value_matches(CoreType.BOOLEAN, 1) is False


def test_python_value_matches_list():
    assert python_value_matches(CoreType.LIST, [1, 2, 3]) is True
    assert python_value_matches(CoreType.LIST, "not a list") is False
