"""Integration tests for the UQAL CLI (add/update/remove/list-connections)."""
import json
import pytest
from click.testing import CliRunner
from pathlib import Path

from uqal_core.cli.main import cli

pytestmark = pytest.mark.integration


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def isolated_config(tmp_path, monkeypatch):
    """Redirect all ConfigManager calls to a temporary directory."""
    monkeypatch.setattr(
        "uqal_core.config.config_manager._get_config_dir",
        lambda: tmp_path,
    )
    return tmp_path


# ---- list-connections ----

def test_list_connections_empty(runner, isolated_config):
    result = runner.invoke(cli, ["list-connections"])
    assert result.exit_code == 0
    assert "No connections registered" in result.output


# ---- add-connection ----

def test_add_connection_creates_entry(runner, isolated_config):
    result = runner.invoke(
        cli,
        ["add-connection", "db1", "standard.dummy", "--no-interactive"],
    )
    assert result.exit_code == 0, result.output
    config = json.loads((isolated_config / "uqal_config.json").read_text())
    assert "db1" in config["connections"]


def test_add_connection_success_message(runner, isolated_config):
    result = runner.invoke(
        cli,
        ["add-connection", "mydb", "standard.dummy", "--no-interactive"],
    )
    assert "mydb" in result.output


def test_add_connection_with_host(runner, isolated_config):
    result = runner.invoke(
        cli,
        [
            "add-connection", "db1", "standard.dummy",
            "--host", "localhost", "--no-interactive",
        ],
    )
    assert result.exit_code == 0, result.output
    config = json.loads((isolated_config / "uqal_config.json").read_text())
    assert config["connections"]["db1"]["host"] == "localhost"


# ---- list-connections after add ----

def test_list_connections_shows_added(runner, isolated_config):
    runner.invoke(
        cli,
        ["add-connection", "db1", "standard.dummy", "--no-interactive"],
    )
    result = runner.invoke(cli, ["list-connections"])
    assert result.exit_code == 0
    assert "db1" in result.output


# ---- update-connection ----

def test_update_connection_changes_host(runner, isolated_config):
    runner.invoke(
        cli,
        ["add-connection", "db1", "standard.dummy",
         "--host", "old", "--no-interactive"],
    )
    result = runner.invoke(cli, ["update-connection", "db1", "--host", "new"])
    assert result.exit_code == 0, result.output
    config = json.loads((isolated_config / "uqal_config.json").read_text())
    assert config["connections"]["db1"]["host"] == "new"


def test_update_connection_not_found(runner, isolated_config):
    result = runner.invoke(cli, ["update-connection", "ghost", "--host", "x"])
    assert result.exit_code != 0
    assert "not found" in result.output


# ---- remove-connection ----

def test_remove_connection_removes_entry(runner, isolated_config):
    runner.invoke(
        cli,
        ["add-connection", "db1", "standard.dummy", "--no-interactive"],
    )
    result = runner.invoke(cli, ["remove-connection", "db1"])
    assert result.exit_code == 0, result.output
    config = json.loads((isolated_config / "uqal_config.json").read_text())
    assert "db1" not in config["connections"]


def test_remove_connection_not_found(runner, isolated_config):
    result = runner.invoke(cli, ["remove-connection", "ghost"])
    assert result.exit_code != 0
    assert "not found" in result.output


def test_remove_connection_also_removes_secrets(runner, isolated_config):
    runner.invoke(
        cli,
        ["add-connection", "db1", "standard.dummy",
         "--secret", "password", "pw123", "--no-interactive"],
    )
    result = runner.invoke(cli, ["remove-connection", "db1", "--secrets"])
    assert result.exit_code == 0, result.output
    assert "secret" in result.output.lower()
