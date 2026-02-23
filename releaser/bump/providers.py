from __future__ import annotations

import json
import shutil
import subprocess
from abc import ABC, abstractmethod
from pathlib import Path
from typing import List, Optional

import toml


class ProviderError(Exception):
    pass


class BaseProvider(ABC):
    """Abstract base class for version providers."""

    name: str = ""

    @abstractmethod
    def detect(self) -> bool:
        """Return True if this provider's version file exists in the project."""

    @abstractmethod
    def read_version(self) -> str:
        """Read the current version string from the project file."""

    @abstractmethod
    def write_version(self, new_version: str, use_native: bool = True) -> List[str]:
        """Write a new version and return the paths of updated files."""


class PoetryProvider(BaseProvider):
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

    def write_version(self, new_version: str, use_native: bool = True) -> List[str]:
        """Write version using poetry when available; fallback to file edit.

        Returns the paths of updated files for staging.
        """
        updated = False
        if use_native:
            updated = self._write_version_native(new_version)
        if not updated:
            self._write_version_file(new_version)
        return [str(self.pyproject)]


class NpmProvider(BaseProvider):
    name = "npm"

    def __init__(self, cwd: str = ".") -> None:
        self.cwd = cwd
        self.package_json = Path(self.cwd) / "package.json"

    def detect(self) -> bool:
        if not self.package_json.exists():
            return False
        try:
            with open(self.package_json, "r", encoding="utf-8") as f:
                data = json.load(f)
            return "version" in data
        except Exception:
            return False

    def read_version(self) -> str:
        if not self.package_json.exists():
            raise ProviderError("package.json not found")
        with open(self.package_json, "r", encoding="utf-8") as f:
            data = json.load(f)
        v = data.get("version")
        if v:
            return str(v)
        return "0.0.0"

    def _write_version_file(self, new_version: str) -> List[str]:
        """Update version in package.json and package-lock.json if present.

        Returns list of updated file paths.
        """
        updated = []
        with open(self.package_json, "r", encoding="utf-8") as f:
            data = json.load(f)
        data["version"] = new_version
        with open(self.package_json, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
            f.write("\n")
        updated.append(str(self.package_json))

        lock_file = Path(self.cwd) / "package-lock.json"
        if lock_file.exists():
            try:
                with open(lock_file, "r", encoding="utf-8") as f:
                    lock_data = json.load(f)
                if "version" in lock_data:
                    lock_data["version"] = new_version
                # Also update the root package entry in "packages".""
                if "packages" in lock_data and "" in lock_data["packages"]:
                    lock_data["packages"][""]["version"] = new_version
                with open(lock_file, "w", encoding="utf-8") as f:
                    json.dump(lock_data, f, indent=2)
                    f.write("\n")
                updated.append(str(lock_file))
            except Exception:
                pass  # Don't fail the release over lock file issues

        return updated

    def _write_version_native(self, new_version: str) -> bool:
        npm = shutil.which("npm")
        if not npm:
            return False
        try:
            subprocess.run(
                [npm, "version", new_version, "--no-git-tag-version"],
                cwd=self.cwd,
                check=True,
            )
            return True
        except subprocess.CalledProcessError:
            return False

    def write_version(self, new_version: str, use_native: bool = True) -> List[str]:
        """Write version using npm when available; fallback to file edit.

        Returns the paths of updated files for staging.
        """
        if use_native and self._write_version_native(new_version):
            # npm version updates both package.json and package-lock.json
            files = [str(self.package_json)]
            lock_file = Path(self.cwd) / "package-lock.json"
            if lock_file.exists():
                files.append(str(lock_file))
            return files
        return self._write_version_file(new_version)


class CargoProvider(BaseProvider):
    name = "cargo"

    def __init__(self, cwd: str = ".") -> None:
        self.cwd = cwd
        # Prefer root Cargo.toml; fall back to src-tauri/Cargo.toml
        root = Path(self.cwd) / "Cargo.toml"
        tauri = Path(self.cwd) / "src-tauri" / "Cargo.toml"
        if root.exists():
            self.cargo_toml = root
        elif tauri.exists():
            self.cargo_toml = tauri
        else:
            self.cargo_toml = root  # default path for detection to fail gracefully

        # Tauri conf paths to check
        self._tauri_conf_candidates = [
            Path(self.cwd) / "src-tauri" / "tauri.conf.json",
            Path(self.cwd) / "tauri.conf.json",
        ]

    def detect(self) -> bool:
        if not self.cargo_toml.exists():
            return False
        try:
            data = toml.load(str(self.cargo_toml))
            return "package" in data and "version" in data.get("package", {})
        except Exception:
            return False

    def read_version(self) -> str:
        if not self.cargo_toml.exists():
            raise ProviderError("Cargo.toml not found")
        data = toml.load(str(self.cargo_toml))
        v = data.get("package", {}).get("version")
        if v:
            return str(v)
        return "0.0.0"

    def _find_tauri_conf(self) -> Optional[Path]:
        """Return the first existing tauri.conf.json path, or None."""
        for candidate in self._tauri_conf_candidates:
            if candidate.exists():
                return candidate
        return None

    def _write_tauri_conf(self, conf_path: Path, new_version: str) -> None:
        """Update version in tauri.conf.json (supports Tauri v1 and v2)."""
        with open(conf_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        # Tauri v2: top-level "version"
        if "version" in data:
            data["version"] = new_version
        # Tauri v1: "package.version"
        elif "package" in data and isinstance(data["package"], dict):
            data["package"]["version"] = new_version
        else:
            # Default to top-level for new Tauri projects
            data["version"] = new_version
        with open(conf_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
            f.write("\n")

    def write_version(self, new_version: str, use_native: bool = True) -> List[str]:
        """Write version to Cargo.toml and tauri.conf.json if present.

        Returns the paths of all updated files for staging.
        """
        data = toml.load(str(self.cargo_toml))
        data.setdefault("package", {})["version"] = new_version
        with open(self.cargo_toml, "w", encoding="utf-8") as f:
            toml.dump(data, f)

        updated_files = [str(self.cargo_toml)]

        # Also update tauri.conf.json if it exists
        tauri_conf = self._find_tauri_conf()
        if tauri_conf:
            self._write_tauri_conf(tauri_conf, new_version)
            updated_files.append(str(tauri_conf))

        return updated_files


# Detection order: Poetry → NPM → Cargo
PROVIDER_CLASSES = [PoetryProvider, NpmProvider, CargoProvider]


def detect_providers(
    cwd: str = ".", project_type: str = "auto"
) -> List[BaseProvider]:
    """Detect version providers in the project.

    Args:
        cwd: Working directory to scan.
        project_type: "auto" returns ALL matching providers;
                      a specific name (e.g. "npm") returns only that provider if detected.

    Returns:
        List of detected provider instances (may be empty).
    """
    if project_type == "auto":
        results: List[BaseProvider] = []
        for cls in PROVIDER_CLASSES:
            p = cls(cwd)
            if p.detect():
                results.append(p)
        return results

    # Specific provider requested
    cls_map = {cls.name: cls for cls in PROVIDER_CLASSES}
    cls = cls_map.get(project_type)
    if cls is None:
        return []
    p = cls(cwd)
    if p.detect():
        return [p]
    return []


def detect_provider(cwd: str = ".") -> Optional[BaseProvider]:
    """Backward-compatible wrapper: returns the first detected provider or None."""
    found = detect_providers(cwd)
    return found[0] if found else None
