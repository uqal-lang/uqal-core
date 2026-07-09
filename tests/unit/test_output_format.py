"""Tests for ResultSet output formats (to_json, to_csv, to_dict) and _parse_pipe."""
import csv
import io
import json
import pytest
from uqal_core.execution.result_set import ResultSet
from uqal_core.cli.commands.repl import _parse_pipe

pytestmark = pytest.mark.unit

_SAMPLE_ROWS = [
    {"id": 1, "name": "Alice", "amount": 100.0},
    {"id": 2, "name": "Bob", "amount": 200.5},
]


# ---- ResultSet.to_dict() ----

def test_to_dict_returns_list():
    rs = ResultSet(rows=_SAMPLE_ROWS, source_module="test")
    assert isinstance(rs.to_dict(), list)


def test_to_dict_length():
    rs = ResultSet(rows=_SAMPLE_ROWS, source_module="test")
    assert len(rs.to_dict()) == 2


def test_to_dict_preserves_values():
    rs = ResultSet(rows=_SAMPLE_ROWS, source_module="test")
    result = rs.to_dict()
    assert result[0] == {"id": 1, "name": "Alice", "amount": 100.0}
    assert result[1]["name"] == "Bob"


def test_to_dict_empty():
    rs = ResultSet(rows=[], source_module="test")
    assert rs.to_dict() == []


def test_to_dict_returns_new_list():
    rows = [{"x": 1}]
    rs = ResultSet(rows=rows, source_module="test")
    result = rs.to_dict()
    assert result is not rows  # new list object


# ---- ResultSet.to_json() ----

def test_to_json_returns_string():
    rs = ResultSet(rows=_SAMPLE_ROWS, source_module="test")
    assert isinstance(rs.to_json(), str)


def test_to_json_is_valid_json():
    rs = ResultSet(rows=_SAMPLE_ROWS, source_module="test")
    parsed = json.loads(rs.to_json())
    assert isinstance(parsed, list)


def test_to_json_length():
    rs = ResultSet(rows=_SAMPLE_ROWS, source_module="test")
    parsed = json.loads(rs.to_json())
    assert len(parsed) == 2


def test_to_json_preserves_values():
    rs = ResultSet(rows=[{"id": 42, "name": "Alice"}], source_module="test")
    parsed = json.loads(rs.to_json())
    assert parsed[0]["id"] == 42
    assert parsed[0]["name"] == "Alice"


def test_to_json_empty():
    rs = ResultSet(rows=[], source_module="test")
    assert json.loads(rs.to_json()) == []


def test_to_json_default_indent_produces_multiline():
    rs = ResultSet(rows=[{"x": 1}], source_module="test")
    assert "\n" in rs.to_json()


def test_to_json_custom_indent():
    rs = ResultSet(rows=[{"x": 1}], source_module="test")
    # larger indent → more total characters in the output
    assert len(rs.to_json(indent=4)) > len(rs.to_json(indent=2))


# ---- ResultSet.to_csv() ----

def test_to_csv_returns_string():
    rs = ResultSet(rows=_SAMPLE_ROWS, source_module="test")
    assert isinstance(rs.to_csv(), str)


def test_to_csv_has_header_row():
    rs = ResultSet(rows=_SAMPLE_ROWS, source_module="test")
    first_line = rs.to_csv().splitlines()[0]
    assert "id" in first_line
    assert "name" in first_line
    assert "amount" in first_line


def test_to_csv_correct_data_rows():
    rs = ResultSet(rows=_SAMPLE_ROWS, source_module="test")
    reader = csv.DictReader(io.StringIO(rs.to_csv()))
    rows = list(reader)
    assert len(rows) == 2
    assert rows[0]["name"] == "Alice"
    assert rows[1]["name"] == "Bob"


def test_to_csv_empty_result_set():
    rs = ResultSet(rows=[], source_module="test")
    assert rs.to_csv() == ""


def test_to_csv_single_row():
    rs = ResultSet(rows=[{"key": "value"}], source_module="test")
    reader = csv.DictReader(io.StringIO(rs.to_csv()))
    rows = list(reader)
    assert len(rows) == 1
    assert rows[0]["key"] == "value"


# ---- _parse_pipe() ----

def test_parse_pipe_json():
    query, fmt = _parse_pipe("testdb.orders.get_table() | json")
    assert fmt == "json"
    assert query == "testdb.orders.get_table()"


def test_parse_pipe_csv():
    query, fmt = _parse_pipe("testdb.users.get_table() | csv")
    assert fmt == "csv"
    assert query == "testdb.users.get_table()"


def test_parse_pipe_table():
    query, fmt = _parse_pipe("testdb.products.get_table() | table")
    assert fmt == "table"


def test_parse_pipe_unknown_format_ignored():
    line = "testdb.orders.get_table() | xml"
    query, fmt = _parse_pipe(line)
    assert fmt == ""
    assert query == line


def test_parse_pipe_no_pipe_returns_unchanged():
    line = "testdb.orders.get_table()"
    query, fmt = _parse_pipe(line)
    assert query == line
    assert fmt == ""


def test_parse_pipe_uppercase_format_normalized():
    query, fmt = _parse_pipe("testdb.orders.get_table() | JSON")
    assert fmt == "json"


def test_parse_pipe_mixed_case_format():
    query, fmt = _parse_pipe("let x = 5 | Csv")
    assert fmt == "csv"


def test_parse_pipe_strips_format_whitespace():
    query, fmt = _parse_pipe("let x = 5 |  csv  ")
    assert fmt == "csv"


def test_parse_pipe_returns_stripped_query():
    query, fmt = _parse_pipe("  let x = 5  | json")
    assert fmt == "json"
    assert query == "let x = 5"


def test_parse_pipe_empty_string():
    query, fmt = _parse_pipe("")
    assert query == ""
    assert fmt == ""


def test_parse_pipe_only_pipe_no_format():
    line = "query | "
    query, fmt = _parse_pipe(line)
    assert fmt == ""
