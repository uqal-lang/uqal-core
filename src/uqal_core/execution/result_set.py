"""
Unified result format.

Every module wraps whatever it gets back from its native database
(SQL rows, Mongo documents, Neo4j records, ...) into these two classes
before returning it from UQALModule.execute().

This is what makes the scripting language's iteration syntax
identical regardless of the data source (see language specification,
chapter 4 "Return types"):

    for row in a:
        row.amount
        row.value("amount")
"""

from __future__ import annotations

from typing import Any, Iterator


class ResultRow:
    """
    A single row/record/document, normalized into a flat field->value
    mapping regardless of where it came from.
    """

    def __init__(self, data: dict[str, Any]) -> None:
        self._data = data

    def value(self, field_name: str) -> Any:
        if field_name not in self._data:
            raise KeyError(
                f"Field '{field_name}' is not present on this row. "
                f"Available fields: {sorted(self._data.keys())}."
            )
        return self._data[field_name]

    def __getattr__(self, field_name: str) -> Any:
        # Enables the short form: row.amount instead of row.value("amount")
        # __getattr__ is only called when normal attribute lookup fails,
        # so this never shadows real attributes/methods of ResultRow.
        try:
            return self._data[field_name]
        except KeyError:
            raise AttributeError(
                f"Field '{field_name}' is not present on this row. "
                f"Available fields: {sorted(self._data.keys())}."
            ) from None

    def as_dict(self) -> dict[str, Any]:
        return dict(self._data)

    def __repr__(self) -> str:
        return f"ResultRow({self._data!r})"


class ResultSet:
    """
    A collection of rows returned from a "get_table"-style query, plus
    the special case of a single scalar value for "get_value".

    source_module is kept for debugging/error messages only - the
    core never branches its behavior based on it, to stay database
    agnostic (see specification chapter 14.1).
    """

    def __init__(
        self,
        rows: list[dict[str, Any]],
        source_module: str,
    ) -> None:
        self._rows = rows
        self.source_module = source_module

    def row(self, index: int) -> ResultRow:
        return ResultRow(self._rows[index])

    def __iter__(self) -> Iterator[ResultRow]:
        return (ResultRow(r) for r in self._rows)

    def __len__(self) -> int:
        return len(self._rows)

    def is_empty(self) -> bool:
        return len(self._rows) == 0

    @classmethod
    def single_value(cls, value: Any, field_name: str, source_module: str) -> "ResultSet":
        """
        Convenience constructor for get_value-style results, which are
        internally still represented as a one-row, one-field ResultSet
        so that the same class can be used everywhere.
        """
        return cls(rows=[{field_name: value}], source_module=source_module)
    
    def __str__(self) -> str:
        if not self._rows:
            return "(empty)"

        # _rows enthält rohe dicts - direkt nutzen
        rows = self._rows

        if len(rows) == 1 and len(rows[0]) == 1:
            # Single value - zeige nur den Wert
            return str(list(rows[0].values())[0])

        headers = list(rows[0].keys())
        col_widths = {h: len(str(h)) for h in headers}

        for row in rows:
            for h in headers:
                val = str(row.get(h, ""))
                col_widths[h] = max(col_widths[h], len(val))

        header_line = "  ".join(
            str(h).ljust(col_widths[h]) for h in headers
        )
        sep_line = "  ".join(
            "-" * col_widths[h] for h in headers
        )
        row_lines = [
            "  ".join(
                str(row.get(h, "")).ljust(col_widths[h])
                for h in headers
            )
            for row in rows
        ]

        return "\n".join([header_line, sep_line] + row_lines)
    
    def to_dict(self) -> list[dict]:
        """Returns all rows as a list of dicts."""
        return list(self._rows)

    def to_json(self, indent: int = 2) -> str:
        """Returns all rows as a JSON string."""
        import json
        return json.dumps(self._rows, indent=indent, default=str)

    def to_csv(self) -> str:
        """Returns all rows as CSV string."""
        if not self._rows:
            return ""
        import csv
        import io
        output = io.StringIO()
        headers = list(self._rows[0].keys())
        writer = csv.DictWriter(output, fieldnames=headers)
        writer.writeheader()
        writer.writerows(self._rows)
        return output.getvalue()

    def __repr__(self) -> str:
        return f"ResultSet(rows={len(self._rows)}, source={self.source_module!r})"