from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Optional

import toml


class ProviderError(Exception):
    pass


class PoetryProvider:
    name = "poetry"

    def __init__(self, cwd: str = ".") -> None:
        self.cwd = cwd
        self.pyproject = Path(self.cwd) / "pyproject.toml"

    def detect(self) -> bool:
        if not self.pyproject.exists():
            return False
        try:
            data = toml.load(str(self.pyproject))
            # Either PEP 621 [project] or legacy [tool.poetry]
            return "project" in data or ("tool" in data and "poetry" in data["tool"])
        except Exception:
            return False

    def read_version(self) -> str:
        if not self.pyproject.exists():
            raise ProviderError("pyproject.toml not found")
        data = toml.load(str(self.pyproject))
        if "project" in data and isinstance(data["project"], dict):
            v = data["project"].get("version")
            if v:
                return str(v)
        # Fallback: tool.poetry.version
        v = data.get("tool", {}).get("poetry", {}).get("version")
        if v:
            return str(v)
        # Default if not found
        return "0.0.0"

    def _write_version_file(self, new_version: str) -> None:
        data = toml.load(str(self.pyproject))
        if "project" in data and isinstance(data["project"], dict):
            data.setdefault("project", {})["version"] = new_version
        elif "tool" in data and "poetry" in data["tool"]:
            data.setdefault("tool", {}).setdefault("poetry", {})[
                "version"
            ] = new_version
        else:
            # Create PEP 621 section if absent
            data.setdefault("project", {})["version"] = new_version
        with open(self.pyproject, "w", encoding="utf-8") as f:
            toml.dump(data, f)

    def _write_version_native(self, new_version: str) -> bool:
        poetry = shutil.which("poetry")
        if not poetry:
            return False
        try:
            subprocess.run([poetry, "version", new_version], cwd=self.cwd, check=True)
            return True
        except subprocess.CalledProcessError:
            return False

    def write_version(self, new_version: str, use_native: bool = True) -> str:
        """Write version using poetry when available; fallback to file edit.

        Returns the path of the updated file for staging.
        """
        updated = False
        if use_native:
            updated = self._write_version_native(new_version)
        if not updated:
            self._write_version_file(new_version)
        return str(self.pyproject)


def detect_provider(cwd: str = ".") -> Optional[PoetryProvider]:
    p = PoetryProvider(cwd)
    if p.detect():
        return p
    return None
