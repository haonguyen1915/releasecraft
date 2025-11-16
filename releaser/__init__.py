"""
Releaser - A CLI tool for generating releases and changelogs.

This package provides command-line tools for automating the release process,
including changelog generation, version bumping, and merge request creation.
"""

try:
    # Try to get version from installed package metadata (standard approach)
    from importlib.metadata import version, PackageNotFoundError

    try:
        __version__ = version("releaser")
    except PackageNotFoundError:
        # Package is not installed, try to get from pyproject.toml
        import toml
        from pathlib import Path

        package_dir = Path(__file__).parent.parent
        pyproject_path = package_dir / "pyproject.toml"

        if pyproject_path.exists():
            with open(pyproject_path, "r", encoding="utf-8") as f:
                data = toml.load(f)
                __version__ = data.get("project", {}).get("version", "0.0.0")
        else:
            __version__ = "0.0.0"
except ImportError:
    # Fallback for Python < 3.8
    try:
        import pkg_resources

        __version__ = pkg_resources.get_distribution("releaser").version
    except Exception:
        __version__ = "0.0.0"


# Lazy import to avoid circular dependencies
def cli_main():
    """Entrypoint for the `releaser` console script."""
    from .cli import main

    return main()


__all__ = ["cli_main", "__version__"]
