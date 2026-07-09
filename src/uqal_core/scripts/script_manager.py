"""
Script manager.

Manages UQAL script files (.uqal) in the project's .uqal/scripts/
directory. Scripts are plain text files containing UQAL statements.

Discovery is automatic - any .uqal file placed in the scripts
directory is immediately available as a named command, no
registration needed.
"""

from __future__ import annotations

from pathlib import Path


def _get_scripts_dir() -> Path:
    """
    Returns the scripts directory relative to the current working
    directory. Creates it if it does not exist.
    """
    scripts_dir = Path.cwd() / ".uqal" / "scripts"
    scripts_dir.mkdir(parents=True, exist_ok=True)
    return scripts_dir


class ScriptManager:
    """
    Manages UQAL script files in .uqal/scripts/.

    Scripts are identified by name (without .uqal extension).
    Any .uqal file placed manually in the directory is automatically
    discoverable - no explicit registration required.
    """

    def __init__(self, scripts_dir: Path | None = None) -> None:
        self._dir = scripts_dir or _get_scripts_dir()

    def script_path(self, name: str) -> Path:
        """Returns the full path for a script name."""
        return self._dir / f"{name}.uqal"

    def exists(self, name: str) -> bool:
        return self.script_path(name).exists()

    def list_scripts(self) -> list[str]:
        """
        Returns all available script names, sorted alphabetically.
        Includes any .uqal files placed manually in the directory.
        """
        return sorted(
            p.stem for p in self._dir.glob("*.uqal")
        )

    def read(self, name: str) -> str:
        """Reads and returns the content of a script."""
        path = self.script_path(name)
        if not path.exists():
            raise FileNotFoundError(
                f"Script '{name}' not found. "
                f"Use 'uqal script edit {name}' to create it."
            )
        return path.read_text(encoding="utf-8")

    def write(self, name: str, content: str) -> Path:
        """Writes content to a script file. Creates it if needed."""
        path = self.script_path(name)
        path.write_text(content, encoding="utf-8")
        return path

    def delete(self, name: str) -> bool:
        """Deletes a script. Returns False if it did not exist."""
        path = self.script_path(name)
        if not path.exists():
            return False
        path.unlink()
        return True

    def rename(self, old_name: str, new_name: str) -> None:
        """Renames a script."""
        old_path = self.script_path(old_name)
        new_path = self.script_path(new_name)
        if not old_path.exists():
            raise FileNotFoundError(f"Script '{old_name}' not found.")
        if new_path.exists():
            raise FileExistsError(
                f"Script '{new_name}' already exists. "
                f"Delete it first or choose a different name."
            )
        old_path.rename(new_path)

    def scripts_dir(self) -> Path:
        return self._dir