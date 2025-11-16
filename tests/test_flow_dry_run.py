from types import SimpleNamespace

from releaser.bump.flow import run as run_bump


def test_flow_manual_dry_run_no_changes(tmp_path, monkeypatch):
    # Create a minimal pyproject.toml so Poetry provider detects
    py = tmp_path / "pyproject.toml"
    py.write_text(
        """
[project]
name = "demo"
version = "0.1.0"
""".strip()
        + "\n"
    )

    # Run from that directory
    monkeypatch.chdir(tmp_path)

    # Prepare args to avoid interactive prompts and avoid writes
    args = SimpleNamespace(
        manual="0.2.0",
        type=None,
        pre=False,
        finalize=False,
        dry_run=True,
        push=False,
        no_commit=True,
        no_tag=True,
        config=None,
        notes=None,
        notes_file=None,
        changelog=False,
        changelog_file=None,
    )

    # Capture original content
    original = py.read_text()

    rc = run_bump(args)
    assert rc == 0

    # Ensure file unchanged on dry-run
    assert py.read_text() == original
