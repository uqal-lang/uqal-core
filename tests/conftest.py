"""
pytest configuration: log files, section ordering, and final score.

Run order is always: unit → integration → e2e → uncategorized.
A section header is printed in the terminal whenever the marker group changes.
The terminal summary at the end shows a score (passed/total) and saves to a
timestamped log file so previous results are never overwritten.
"""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

# ---------------------------------------------------------------------------
# Marker ordering
# ---------------------------------------------------------------------------

_MARKER_ORDER: dict[str, int] = {"unit": 0, "integration": 1, "e2e": 2}
_SECTION_LABELS: dict[str, str] = {
    "unit": "UNIT TESTS",
    "integration": "INTEGRATION TESTS",
    "e2e": "END-TO-END TESTS",
    "other": "OTHER TESTS",
}

# Mutable sentinel to track which section is currently being printed.
_current_section: dict[str, str | None] = {"value": None}


def _get_primary_marker(item) -> str:
    for marker in ("unit", "integration", "e2e"):
        if item.get_closest_marker(marker):
            return marker
    return "other"


def pytest_collection_modifyitems(items):
    """Sort collected tests: unit → integration → e2e → other."""
    items.sort(
        key=lambda x: (_MARKER_ORDER.get(_get_primary_marker(x), 99), x.nodeid)
    )


def pytest_runtest_protocol(item, nextitem=None):  # noqa: ARG001
    """Print a bold section separator when the marker group changes."""
    section = _get_primary_marker(item)
    if section != _current_section["value"]:
        _current_section["value"] = section
        tr = item.config.pluginmanager.get_plugin("terminalreporter")
        if tr is not None:
            label = _SECTION_LABELS.get(section, section.upper())
            tr.write_sep("=", label, bold=True, yellow=True)
    return None  # proceed with the default test protocol


# ---------------------------------------------------------------------------
# Log file setup
# ---------------------------------------------------------------------------

def pytest_configure(config):
    """Create a timestamped log file in tests/logs/ for every test run."""
    logs_dir = Path(__file__).parent / "logs"
    logs_dir.mkdir(exist_ok=True)

    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    log_file = logs_dir / f"test_run_{timestamp}.log"

    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(logging.Formatter(
        fmt="%(asctime)s  %(levelname)-8s  %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    ))

    logging.getLogger().addHandler(file_handler)
    logging.getLogger().setLevel(logging.DEBUG)

    config._log_file = log_file


# ---------------------------------------------------------------------------
# Terminal summary with score
# ---------------------------------------------------------------------------

def pytest_terminal_summary(terminalreporter, exitstatus, config):  # noqa: ARG001
    """Print a score banner and save the full summary to the log file."""
    log_file: Path = getattr(config, "_log_file", None)

    stats = terminalreporter.stats
    passed  = len(stats.get("passed",  []))
    failed  = len(stats.get("failed",  []))
    error   = len(stats.get("error",   []))
    skipped = len(stats.get("skipped", []))
    total   = passed + failed + error + skipped

    pct = (passed / total * 100) if total else 0.0
    score_line = f"Score: {passed}/{total} tests passed ({pct:.1f}%)"

    # Always print the score to the terminal
    terminalreporter.write_sep("=", "TEST RESULTS", bold=True)
    terminalreporter.write_line(f"  Passed:  {passed}", green=passed > 0 and failed == 0)
    terminalreporter.write_line(f"  Failed:  {failed}", red=failed > 0)
    terminalreporter.write_line(f"  Errors:  {error}",  red=error > 0)
    terminalreporter.write_line(f"  Skipped: {skipped}")
    terminalreporter.write_sep("-", score_line, bold=True, green=failed == 0 and error == 0)

    if log_file is None:
        return

    # Build log content
    lines = [
        "",
        "=" * 60,
        "TEST SUMMARY",
        "=" * 60,
        f"Total:   {total}",
        f"Passed:  {passed}",
        f"Failed:  {failed}",
        f"Errors:  {error}",
        f"Skipped: {skipped}",
        score_line,
        "=" * 60,
    ]

    if failed or error:
        lines.append("\nFAILED TESTS:")
        for report in stats.get("failed", []) + stats.get("error", []):
            lines.append(f"  - {report.nodeid}")
            if hasattr(report, "longreprtext"):
                lines.append(f"    {report.longreprtext[:200]}")

    lines.append(f"\nFull log: {log_file}")

    with open(log_file, "a", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    terminalreporter.write_sep("-", f"log saved to: {log_file}")
