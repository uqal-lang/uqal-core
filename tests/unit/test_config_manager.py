"""Unit tests for uqal_core.config.config_manager.ConfigManager"""
import json
import os
import pytest
from pathlib import Path

from uqal_core.config.config_manager import ConfigManager

pytestmark = pytest.mark.unit


@pytest.fixture
def manager(tmp_path: Path) -> ConfigManager:
    return ConfigManager(config_dir=tmp_path)


# ---- add_connection ----

class TestAddConnection:
    def test_writes_to_config_file(self, manager, tmp_path):
        manager.add_connection("db1", "dummy", ["standard.dummy"])
        config = json.loads((tmp_path / "uqal_config.json").read_text())
        assert "db1" in config["connections"]

    def test_stores_module_type(self, manager):
        manager.add_connection("db1", "postgresql", ["standard.postgresql"])
        conn = manager.list_connections()["db1"]
        assert conn["module_type"] == "postgresql"

    def test_stores_optional_fields(self, manager):
        manager.add_connection(
            "db1", "postgresql", ["standard.postgresql"],
            host="localhost", port=5432, database="mydb"
        )
        conn = manager.list_connections()["db1"]
        assert conn["host"] == "localhost"
        assert conn["port"] == 5432
        assert conn["database"] == "mydb"

    def test_omits_none_fields(self, manager):
        manager.add_connection("db1", "dummy", ["standard.dummy"])
        conn = manager.list_connections()["db1"]
        assert "host" not in conn
        assert "port" not in conn

    def test_overwrites_existing_connection(self, manager):
        manager.add_connection("db1", "dummy", ["standard.dummy"], host="old")
        manager.add_connection("db1", "postgresql", ["standard.postgresql"], host="new")
        conn = manager.list_connections()["db1"]
        assert conn["host"] == "new"
        assert conn["module_type"] == "postgresql"

    def test_multiple_connections(self, manager):
        manager.add_connection("db1", "dummy", ["standard.dummy"])
        manager.add_connection("db2", "postgresql", ["standard.postgresql"])
        connections = manager.list_connections()
        assert "db1" in connections
        assert "db2" in connections


# ---- update_connection ----

class TestUpdateConnection:
    def test_updates_only_specified_field(self, manager):
        manager.add_connection("db1", "dummy", ["standard.dummy"], host="old", port=5432)
        manager.update_connection("db1", host="new")
        conn = manager.list_connections()["db1"]
        assert conn["host"] == "new"
        assert conn["port"] == 5432

    def test_returns_true_when_found(self, manager):
        manager.add_connection("db1", "dummy", ["standard.dummy"])
        assert manager.update_connection("db1", host="x") is True

    def test_returns_false_when_not_found(self, manager):
        assert manager.update_connection("nonexistent", host="x") is False

    def test_updates_module_type(self, manager):
        manager.add_connection("db1", "dummy", ["standard.dummy"])
        manager.update_connection("db1", module_type="postgresql")
        assert manager.list_connections()["db1"]["module_type"] == "postgresql"

    def test_no_change_when_all_none(self, manager):
        manager.add_connection("db1", "dummy", ["standard.dummy"], host="kept")
        manager.update_connection("db1")
        assert manager.list_connections()["db1"]["host"] == "kept"


# ---- remove_connection ----

class TestRemoveConnection:
    def test_removes_existing_connection(self, manager):
        manager.add_connection("db1", "dummy", ["standard.dummy"])
        result = manager.remove_connection("db1")
        assert result is True
        assert "db1" not in manager.list_connections()

    def test_returns_false_for_nonexistent(self, manager):
        assert manager.remove_connection("nonexistent") is False

    def test_does_not_affect_other_connections(self, manager):
        manager.add_connection("db1", "dummy", ["standard.dummy"])
        manager.add_connection("db2", "dummy", ["standard.dummy"])
        manager.remove_connection("db1")
        assert "db2" in manager.list_connections()

    def test_config_file_updated_on_disk(self, manager, tmp_path):
        manager.add_connection("db1", "dummy", ["standard.dummy"])
        manager.remove_connection("db1")
        config = json.loads((tmp_path / "uqal_config.json").read_text())
        assert "db1" not in config["connections"]


# ---- add_secret ----

class TestAddSecret:
    def test_writes_env_file(self, manager, tmp_path):
        manager.add_secret("db1", "password", "geheim")
        assert (tmp_path / ".env").exists()

    def test_key_format(self, manager, tmp_path):
        manager.add_secret("db1", "password", "geheim")
        content = (tmp_path / ".env").read_text()
        assert "UQAL_DB1_PASSWORD=geheim" in content

    def test_uppercases_connection_and_key(self, manager, tmp_path):
        manager.add_secret("MyDb", "api_key", "secret123")
        content = (tmp_path / ".env").read_text()
        assert "UQAL_MYDB_API_KEY=secret123" in content

    def test_multiple_secrets(self, manager, tmp_path):
        manager.add_secret("db1", "password", "pw1")
        manager.add_secret("db1", "user", "admin")
        content = (tmp_path / ".env").read_text()
        assert "UQAL_DB1_PASSWORD=pw1" in content
        assert "UQAL_DB1_USER=admin" in content

    def test_overwrites_existing_secret(self, manager, tmp_path):
        manager.add_secret("db1", "password", "old")
        manager.add_secret("db1", "password", "new")
        content = (tmp_path / ".env").read_text()
        assert "UQAL_DB1_PASSWORD=new" in content
        assert "UQAL_DB1_PASSWORD=old" not in content


# ---- get_secrets ----

class TestGetSecrets:
    def test_reads_from_env_file(self, manager):
        manager.add_secret("db1", "password", "geheim")
        secrets = manager.get_secrets("db1")
        assert secrets["password"] == "geheim"

    def test_strips_prefix(self, manager):
        manager.add_secret("db1", "password", "x")
        manager.add_secret("db1", "user", "y")
        secrets = manager.get_secrets("db1")
        assert set(secrets.keys()) == {"password", "user"}

    def test_does_not_return_other_connections(self, manager):
        manager.add_secret("db1", "password", "pw1")
        manager.add_secret("db2", "password", "pw2")
        secrets = manager.get_secrets("db1")
        assert "password" in secrets
        assert len(secrets) == 1

    def test_reads_from_os_environ(self, manager, monkeypatch):
        monkeypatch.setenv("UQAL_DB1_TOKEN", "env_token")
        secrets = manager.get_secrets("db1")
        assert secrets["token"] == "env_token"

    def test_os_environ_takes_priority_over_env_file(self, manager, monkeypatch):
        manager.add_secret("db1", "password", "from_file")
        monkeypatch.setenv("UQAL_DB1_PASSWORD", "from_env")
        secrets = manager.get_secrets("db1")
        assert secrets["password"] == "from_env"

    def test_empty_when_no_secrets(self, manager):
        secrets = manager.get_secrets("db1")
        assert secrets == {}


# ---- secrets NOT in config file ----

class TestSecretsNotInConfigFile:
    def test_secret_absent_from_uqal_config(self, manager, tmp_path):
        manager.add_connection("db1", "dummy", ["standard.dummy"])
        manager.add_secret("db1", "password", "geheim")
        config = json.loads((tmp_path / "uqal_config.json").read_text())
        conn = config["connections"]["db1"]
        assert "password" not in conn
        assert "UQAL_DB1_PASSWORD" not in str(conn)

    def test_no_secret_keys_in_config_at_all(self, manager, tmp_path):
        manager.add_connection("db1", "dummy", ["standard.dummy"])
        manager.add_secret("db1", "token", "abc")
        manager.add_secret("db1", "api_key", "xyz")
        config_text = (tmp_path / "uqal_config.json").read_text()
        assert "token" not in config_text
        assert "api_key" not in config_text
