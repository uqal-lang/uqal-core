"""MongoDB native query validator."""

from __future__ import annotations

import json
import re

_BLOCKED_PATTERNS = [
    (r"\$where",       "The $where operator is not allowed."),
    (r"\$function",    "The $function operator is not allowed."),
    (r"\$accumulator", "The $accumulator operator is not allowed."),
]

_COMPILED = [
    (re.compile(p, re.IGNORECASE), msg)
    for p, msg in _BLOCKED_PATTERNS
]


def security_check(query: str) -> list[str]:
    errors = []
    for pattern, message in _COMPILED:
        if pattern.search(query):
            errors.append(f"Security violation: {message}")
    return errors


def syntax_check(query: str) -> list[str]:
    try:
        json.loads(query)
        return []
    except json.JSONDecodeError as e:
        return [f"Invalid JSON: {e}"]


def validate(query: str) -> list[str]:
    errors = security_check(query)
    if errors:
        return errors
    return syntax_check(query)