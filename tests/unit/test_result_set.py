"""Tests for uqal_core.execution.result_set"""
import pytest
from uqal_core.execution.result_set import ResultRow, ResultSet

pytestmark = pytest.mark.unit


def test_result_row_value():
    row = ResultRow({"id": 1, "name": "test"})
    assert row.value("id") == 1
    assert row.value("name") == "test"


def test_result_row_attr_access():
    row = ResultRow({"id": 1, "name": "test"})
    assert row.id == 1
    assert row.name == "test"


def test_result_row_unknown_field():
    row = ResultRow({"id": 1})
    with pytest.raises(KeyError):
        row.value("nonexistent")


def test_result_row_unknown_attr():
    row = ResultRow({"id": 1})
    with pytest.raises(AttributeError):
        _ = row.nonexistent


def test_result_row_as_dict():
    data = {"id": 1, "name": "test"}
    row = ResultRow(data)
    assert row.as_dict() == data


def test_result_set_iteration():
    rs = ResultSet(
        rows=[{"id": 1}, {"id": 2}, {"id": 3}],
        source_module="test"
    )
    ids = [row.id for row in rs]
    assert ids == [1, 2, 3]


def test_result_set_row_by_index():
    rs = ResultSet(rows=[{"id": 1}, {"id": 2}], source_module="test")
    assert rs.row(0).id == 1
    assert rs.row(1).id == 2


def test_result_set_len():
    rs = ResultSet(rows=[{"id": 1}, {"id": 2}], source_module="test")
    assert len(rs) == 2


def test_result_set_is_empty():
    empty = ResultSet(rows=[], source_module="test")
    assert empty.is_empty() is True

    non_empty = ResultSet(rows=[{"id": 1}], source_module="test")
    assert non_empty.is_empty() is False


def test_result_set_single_value():
    rs = ResultSet.single_value(42, "amount", "test_module")
    assert len(rs) == 1
    assert rs.row(0).value("amount") == 42
