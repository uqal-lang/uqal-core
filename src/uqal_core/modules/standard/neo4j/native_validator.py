"""Neo4j native Cypher validator."""

from __future__ import annotations

import re

_BLOCKED_PATTERNS = [
    (r"\bLOAD\s+CSV\b",     "LOAD CSV is not allowed."),
    (r"\bCALL\s+\{",         "Subquery CALL is not allowed."),
    (r"\bDROP\s+",           "DROP is not allowed in native queries."),
    (r"\bCREATE\s+INDEX\b",  "CREATE INDEX is not allowed."),
    (r"\bCREATE\s+CONSTRAINT\b", "CREATE CONSTRAINT is not allowed."),
    (r"\bAPOC\.",             "APOC procedures require explicit permission."),
]

_COMPILED = [
    (re.compile(p, re.IGNORECASE | re.DOTALL), msg)
    for p, msg in _BLOCKED_PATTERNS
]


def security_check(query: str) -> list[str]:
    errors = []
    for pattern, message in _COMPILED:
        if pattern.search(query):
            errors.append(f"Security violation: {message}")
    return errors


def syntax_check(query: str, session=None) -> list[str]:
    """
    Validates Cypher syntax using EXPLAIN if session is available.
    """
    if session is None:
        return []
    try:
        session.run(f"EXPLAIN {query}")
        return []
    except Exception as exc:
        return [f"Cypher syntax error: {exc}"]


def validate(query: str, session=None) -> list[str]:
    errors = security_check(query)
    if errors:
        return errors
    return syntax_check(query, session)