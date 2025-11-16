from types import SimpleNamespace

from releaser.bump.flow import run as run_bump


def test_dirty_working_tree_aborts(tmp_path, monkeypatch):
    # Minimal poetry project
    (tmp_path / "pyproject.toml").write_text(
        """
[project]
name = "demo"
version = "0.1.0"
""".strip()
        + "\n"
    )
    monkeypatch.chdir(tmp_path)

    # Simulate git repo and dirty tree
    (tmp_path / ".git").mkdir()
    monkeypatch.setattr("releaser.bump.flow.git_utils.is_git_repository", lambda: True)
    monkeypatch.setattr(
        "releaser.bump.flow.git_utils.has_uncommitted_changes", lambda: True
    )

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
    assert rc == 1
