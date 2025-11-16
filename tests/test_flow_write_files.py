from types import SimpleNamespace

from releaser.bump.flow import run as run_bump


def test_flow_writes_pyproject_and_init(tmp_path, monkeypatch):
    # Create minimal poetry project
    (tmp_path / "pyproject.toml").write_text(
        """
[project]
name = "demo"
version = "0.1.0"
""".strip()
        + "\n"
    )
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    init_py = pkg / "__init__.py"
    init_py.write_text("__version__ = '0.1.0'\n")

    # Config specifying files and disabling native poetry
    (tmp_path / ".releaser.toml").write_text(
        """
[project]
type = "poetry"
use_native = false

version_targets = [
  "pkg/__init__.py:__version__",
]
""".strip()
        + "\n"
    )

    monkeypatch.chdir(tmp_path)

    args = SimpleNamespace(
        manual="0.2.0",
        type=None,
        pre=False,
        finalize=False,
        dry_run=False,
        push=False,
        no_commit=True,
        no_tag=True,
        config=None,
        notes=None,
        notes_file=None,
        changelog=False,
        changelog_file=None,
    )

    rc = run_bump(args)
    assert rc == 0

    # Verify pyproject and __init__ updated
    assert 'version = "0.2.0"' in (tmp_path / "pyproject.toml").read_text()
    assert (pkg / "__init__.py").read_text().strip().endswith("__version__ = '0.2.0'")
