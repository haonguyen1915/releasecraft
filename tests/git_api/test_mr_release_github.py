from types import SimpleNamespace

from releaser.drafter import mr_release as mr


def test_create_github_pr_dry_run(monkeypatch):
    # Dry run returns True without requiring gh
    ok = mr.create_github_pr(
        branch_name="release/v1.0.0",
        version="1.0.0",
        changelog_preview="- ...",
        mr_target_branch="main",
        changelog_file="CHANGELOG.md",
        pyproject_file="pyproject.toml",
        dry_run=True,
        logger=None,
    )
    assert ok is True


def test_create_github_pr_invokes_gh(monkeypatch):
    calls = []

    def fake_run(cmd, capture_output=True):
        calls.append(cmd)
        return SimpleNamespace(stdout="", returncode=0)

    monkeypatch.setattr("releaser.drafter.utils.run_command", fake_run)
    ok = mr.create_github_pr(
        branch_name="release/v1.0.0",
        version="1.0.0",
        changelog_preview="- ...",
        mr_target_branch="main",
        changelog_file="CHANGELOG.md",
        pyproject_file="pyproject.toml",
        dry_run=False,
        logger=None,
    )
    assert ok is True
    # Expect gh --version check and gh pr create
    assert any(c[:2] == ["gh", "--version"] for c in calls)
    assert any(c[:3] == ["gh", "pr", "create"] for c in calls)

