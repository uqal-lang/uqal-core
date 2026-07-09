"""
PostgreSQL native query validator.

Two-stage validation for native SQL passed via db1.sql("..."):
  1. Security check (Core-level patterns, blocks dangerous SQL)
  2. Syntax check (via PostgreSQL's own parser through psycopg2)
"""

from __future__ import annotations

import re

# Patterns that are always blocked regardless of context.
# These indicate SQL injection attempts or destructive operations
# without proper safeguards.
_BLOCKED_PATTERNS: list[tuple[str, str]] = [
    (r";\s*DROP\s+",
     "DROP after semicolon is not allowed."),
    (r";\s*TRUNCATE\s+",
     "TRUNCATE after semicolon is not allowed."),
    (r";\s*DELETE\s+FROM\s+\w+\s*;?\s*$",
     "DELETE without WHERE is not allowed."),
    (r"--",
     "SQL comments (--) are not allowed in native queries."),
    (r"/\*.*?\*/",
     "Block comments (/* */) are not allowed in native queries."),
    (r"\bxp_cmdshell\b",
     "xp_cmdshell is not allowed."),
    (r"\bEXEC\s*\(",
     "EXEC() is not allowed."),
]

_COMPILED_PATTERNS = [
    (re.compile(pattern, re.IGNORECASE | re.DOTALL), message)
    for pattern, message in _BLOCKED_PATTERNS
]


def security_check(query: str) -> list[str]:
    """
    Checks a native SQL string for dangerous patterns.
    Returns a list of error messages - empty means safe.
    """
    errors = []
    for pattern, message in _COMPILED_PATTERNS:
        if pattern.search(query):
            errors.append(f"Security violation: {message}")
    return errors


def syntax_check(query: str, connection) -> list[str]:
    """
    Validates SQL syntax without executing it.
    DDL statements (DROP, CREATE, ALTER) cannot use EXPLAIN
    so they skip syntax check and only get security check.
    """
    if connection is None:
        return []

    # DDL statements cannot be wrapped in EXPLAIN
    ddl_keywords = (
        "DROP", "CREATE", "ALTER", "TRUNCATE",
        "GRANT", "REVOKE", "COMMENT",
    )
    stripped = query.strip().upper()
    if any(stripped.startswith(kw) for kw in ddl_keywords):
        return []  # Skip syntax check for DDL

    try:
        cursor = connection.cursor()
        cursor.execute(f"EXPLAIN {query}")
        cursor.close()
        return []
    except Exception as exc:
        return [f"SQL syntax error: {exc}"]


def validate(query: str, connection=None) -> list[str]:
    """
    Full validation pipeline: security check + syntax check.
    Syntax check is skipped if no connection is available.
    """
    errors = security_check(query)
    if errors:
        return errors
    return syntax_check(query, connection)