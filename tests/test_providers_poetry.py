from pathlib import Path

from releaser.bump.providers import PoetryProvider


def write_pyproject_project(tmp_path: Path, version: str) -> Path:
    content = f"""
[project]
name = "demo"
version = "{version}"
"""
    p = tmp_path / "pyproject.toml"
    p.write_text(content.strip() + "\n")
    return p


def write_pyproject_tool_poetry(tmp_path: Path, version: str) -> Path:
    content = f"""
[tool.poetry]
name = "demo"
version = "{version}"
"""
    p = tmp_path / "pyproject.toml"
    p.write_text(content.strip() + "\n")
    return p


def test_poetry_provider_detect_and_read_project(tmp_path: Path):
    write_pyproject_project(tmp_path, "0.1.0")
    prov = PoetryProvider(str(tmp_path))
    assert prov.detect() is True
    assert prov.read_version() == "0.1.0"


def test_poetry_provider_write_project(tmp_path: Path):
    write_pyproject_project(tmp_path, "0.1.0")
    prov = PoetryProvider(str(tmp_path))
    path = prov.write_version("0.2.0", use_native=False)
    assert Path(path).exists()
    # Re-read
    assert prov.read_version() == "0.2.0"


def test_poetry_provider_detect_tool_poetry(tmp_path: Path):
    write_pyproject_tool_poetry(tmp_path, "0.3.0")
    prov = PoetryProvider(str(tmp_path))
    assert prov.detect() is True
    assert prov.read_version() == "0.3.0"
