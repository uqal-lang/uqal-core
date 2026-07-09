"""
Configuration manager.

Handles two separate files:
  uqal_config.json  - non-secret configuration (connections, modules)
  .env              - secrets only (passwords, tokens, certificates)

Default location for both is the current working directory.
Can be overridden globally via 'uqal set-config-path <path>',
which stores the override in ~/.uqal/settings.json.

Environment variable naming convention:
  UQAL_<CONNECTION_NAME_UPPER>_<KEY_UPPER>
  e.g. UQAL_DB1_PASSWORD, UQAL_DB1_USER
"""

from __future__ import annotations

import json
import os
from pathlib import Path


_GLOBAL_SETTINGS_PATH = Path.home() / ".uqal" / "settings.json"
_CONFIG_FILENAME = "uqal_config.json"
_ENV_FILENAME = ".env"


def _get_config_dir() -> Path:
    """
    Returns the directory where uqal_config.json and .env are stored.

    Priority:
      1. Override stored in ~/.uqal/settings.json
      2. Current working directory (default)
    """
    if _GLOBAL_SETTINGS_PATH.exists():
        try:
            settings = json.loads(_GLOBAL_SETTINGS_PATH.read_text())
            override = settings.get("config_path")
            if override:
                return Path(override)
        except (json.JSONDecodeError, KeyError):
            pass
    return Path.cwd()


def set_config_path(path: str | Path) -> None:
    """
    Globally overrides the config directory.
    Stored in ~/.uqal/settings.json so it persists across sessions.
    """
    _GLOBAL_SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    settings = {}
    if _GLOBAL_SETTINGS_PATH.exists():
        try:
            settings = json.loads(_GLOBAL_SETTINGS_PATH.read_text())
        except json.JSONDecodeError:
            pass
    settings["config_path"] = str(Path(path).resolve())
    _GLOBAL_SETTINGS_PATH.write_text(
        json.dumps(settings, indent=2), encoding="utf-8"
    )


def get_config_path() -> Path:
    """Returns the current config directory path."""
    return _get_config_dir()


class ConfigManager:
    """
    Reads and writes uqal_config.json and .env for connection management.
    """

    def __init__(self, config_dir: Path | None = None) -> None:
        self._dir = config_dir or _get_config_dir()
        self._config_file = self._dir / _CONFIG_FILENAME
        self._env_file = self._dir / _ENV_FILENAME

    # ---- Config file (uqal_config.json) ----

    def load_config(self) -> dict:
        if not self._config_file.exists():
            return {"connections": {}}
        try:
            return json.loads(
                self._config_file.read_text(encoding="utf-8")
            )
        except json.JSONDecodeError:
            return {"connections": {}}

    def save_config(self, config: dict) -> None:
        self._config_file.write_text(
            json.dumps(config, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def add_connection(
        self,
        connection_name: str,
        module_type: str,
        modules: list[str],
        host: str | None = None,
        port: int | None = None,
        database: str | None = None,
    ) -> None:
        """
        Adds or replaces a connection in uqal_config.json.
        Only non-secret values are stored here.
        """
        config = self.load_config()
        config.setdefault("connections", {})[connection_name] = {
            k: v for k, v in {
                "module_type": module_type,
                "modules": modules,
                "host": host,
                "port": port,
                "database": database,
            }.items() if v is not None
        }
        self.save_config(config)

    def update_connection(
        self,
        connection_name: str,
        module_type: str | None = None,
        modules: list[str] | None = None,
        host: str | None = None,
        port: int | None = None,
        database: str | None = None,
    ) -> bool:
        """
        Updates individual fields of an existing connection.
        Only provided (non-None) fields are changed.
        Returns False if the connection does not exist.
        """
        config = self.load_config()
        connections = config.get("connections", {})

        if connection_name not in connections:
            return False

        existing = connections[connection_name]

        if module_type is not None:
            existing["module_type"] = module_type
        if modules is not None:
            existing["modules"] = modules
        if host is not None:
            existing["host"] = host
        if port is not None:
            existing["port"] = port
        if database is not None:
            existing["database"] = database

        self.save_config(config)
        return True

    def remove_connection(self, connection_name: str) -> bool:
        """
        Removes a connection from config. Returns True if it existed.
        """
        config = self.load_config()
        if connection_name not in config.get("connections", {}):
            return False
        del config["connections"][connection_name]
        self.save_config(config)
        return True

    def list_connections(self) -> dict[str, dict]:
        return self.load_config().get("connections", {})

    # ---- Env file (.env) ----

    def load_env(self) -> dict[str, str]:
        """Parses the .env file into a dict."""
        if not self._env_file.exists():
            return {}
        result = {}
        for line in self._env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            result[key.strip()] = value.strip()
        return result

    def save_env(self, env: dict[str, str]) -> None:
        """Writes the full env dict to .env."""
        lines = [
            "# UQAL secrets - DO NOT COMMIT THIS FILE",
            "",
        ]
        lines.extend(f"{k}={v}" for k, v in sorted(env.items()))
        self._env_file.write_text(
            "\n".join(lines) + "\n", encoding="utf-8"
        )

    def add_secret(
        self, connection_name: str, key: str, value: str
    ) -> None:
        """
        Adds or updates a secret for a connection in .env.
        Key format: UQAL_<CONNECTION_UPPER>_<KEY_UPPER>
        Creates .env if it does not exist yet.
        """
        env_key = f"UQAL_{connection_name.upper()}_{key.upper()}"
        env = self.load_env()
        env[env_key] = value
        self.save_env(env)

    def remove_secrets(self, connection_name: str) -> int:
        """
        Removes all secrets for a connection from .env.
        Returns the number of removed entries.
        """
        prefix = f"UQAL_{connection_name.upper()}_"
        env = self.load_env()
        keys_to_remove = [k for k in env if k.startswith(prefix)]
        for k in keys_to_remove:
            del env[k]
        if keys_to_remove:
            self.save_env(env)
        return len(keys_to_remove)

    def get_secrets(self, connection_name: str) -> dict[str, str]:
        """
        Returns all secrets for a given connection, with the
        UQAL_<NAME>_ prefix stripped from the keys.

        Also checks os.environ so secrets set as real environment
        variables (e.g. in CI/CD) are picked up automatically.
        os.environ takes priority over .env file.
        """
        prefix = f"UQAL_{connection_name.upper()}_"
        env = {**self.load_env(), **os.environ}
        return {
            k[len(prefix):].lower(): v
            for k, v in env.items()
            if k.startswith(prefix)
        }

    def connection_config_path(self) -> Path:
        return self._config_file

    def env_path(self) -> Path:
        return self._env_file