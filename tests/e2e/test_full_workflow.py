"""End-to-end workflow tests: full CLI round-trip via CliRunner."""
import json
import pytest
from click.testing import CliRunner
from pathlib import Path

from uqal_core.cli.main import cli

pytestmark = pytest.mark.e2e


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def isolated_config(tmp_path, monkeypatch):
    """Redirect all ConfigManager file I/O to a temporary directory."""
    monkeypatch.setattr(
        "uqal_core.config.config_manager._get_config_dir",
        lambda: tmp_path,
    )
    return tmp_path


def test_full_connection_workflow(runner, isolated_config):
    """
    Complete round-trip:
      add-connection → list-connections → run script → remove-connection
    """
    tmp_path = isolated_config

    # Step 1: add-connection with dummy module (no interactive prompts needed)
    result = runner.invoke(
        cli,
        [
            "add-connection", "testdb", "standard.dummy",
            "--module", "standard.dummy",
            "--no-interactive",
        ],
    )
    assert result.exit_code == 0, f"add-connection failed:\n{result.output}"
    assert "testdb" in result.output

    # Verify uqal_config.json was written correctly
    config = json.loads((tmp_path / "uqal_config.json").read_text())
    assert "testdb" in config["connections"]
    assert config["connections"]["testdb"]["module_type"] == "standard.dummy"

    # Step 2: list-connections shows the new connection
    result = runner.invoke(cli, ["list-connections"])
    assert result.exit_code == 0, f"list-connections failed:\n{result.output}"
    assert "testdb" in result.output

    # Step 3: run a simple UQAL script (no DB access required)
    result = runner.invoke(cli, ["run", "let a = 5"])
    assert result.exit_code == 0, f"run failed:\n{result.output}"
    assert "Done" in result.output

    # Step 4: remove-connection
    result = runner.invoke(cli, ["remove-connection", "testdb"])
    assert result.exit_code == 0, f"remove-connection failed:\n{result.output}"
    assert "testdb" in result.output

    # Verify connection is gone from config
    config = json.loads((tmp_path / "uqal_config.json").read_text())
    assert "testdb" not in config["connections"]

    # Step 5: list-connections now shows empty state
    result = runner.invoke(cli, ["list-connections"])
    assert result.exit_code == 0
    assert "No connections registered" in result.output


def test_secret_not_in_config_workflow(runner, isolated_config):
    """Secrets added via --secret must only appear in .env, not uqal_config.json."""
    tmp_path = isolated_config

    runner.invoke(
        cli,
        [
            "add-connection", "secdb", "standard.dummy",
            "--secret", "password", "s3cret",
            "--no-interactive",
        ],
    )

    config_text = (tmp_path / "uqal_config.json").read_text()
    assert "s3cret" not in config_text
    assert "password" not in config_text

    env_text = (tmp_path / ".env").read_text()
    assert "UQAL_SECDB_PASSWORD=s3cret" in env_text


def test_update_connection_workflow(runner, isolated_config):
    """add → update host → list confirms new host."""
    runner.invoke(
        cli,
        [
            "add-connection", "db1", "standard.dummy",
            "--host", "old-host", "--no-interactive",
        ],
    )

    result = runner.invoke(cli, ["update-connection", "db1", "--host", "new-host"])
    assert result.exit_code == 0, f"update-connection failed:\n{result.output}"

    result = runner.invoke(cli, ["list-connections"])
    assert "new-host" in result.output
    assert "old-host" not in result.output


def test_run_with_module_flag(runner, isolated_config):
    """uqal run --module standard.dummy 'list modules' should succeed."""
    result = runner.invoke(cli, ["run", "--module", "standard.dummy", "list modules"])
    assert result.exit_code == 0, f"run with module failed:\n{result.output}"
    assert "Done" in result.output
