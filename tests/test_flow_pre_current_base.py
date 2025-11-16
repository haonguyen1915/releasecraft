from types import SimpleNamespace

from releaser.bump.flow import run as run_bump


def test_pre_release_uses_current_base(tmp_path, monkeypatch):
    # Project with current version 0.1.0
    (tmp_path / "pyproject.toml").write_text(
        """
[project]
name = "demo"
version = "0.1.0"
""".strip()
        + "\n"
    )
    # Enable pre-release in config
    (tmp_path / ".releaser.toml").write_text(
        """
[pre_release]
enabled = true
default_channel = "rc"
""".strip()
        + "\n"
    )
    monkeypatch.chdir(tmp_path)

    args = SimpleNamespace(
        manual=None,
        type=None,
        pre=True,
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
    # pyproject should now be 0.1.0-rc.1 applied to current base, not bumped
    txt = (tmp_path / "pyproject.toml").read_text()
    assert 'version = "0.1.0-rc.1"' in txt
