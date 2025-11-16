from types import SimpleNamespace

from releaser.drafter import mr_release as mr


def test_create_merge_request_dispatch_github(monkeypatch):
    calls = {}
    monkeypatch.setattr("releaser.drafter.utils.get_remote_type", lambda: "github")
    monkeypatch.setattr(
        mr, "create_github_pr", lambda *a, **k: calls.setdefault("gh", True)
    )
    ok = mr.create_merge_request(
        branch_name="release/v1.0.0",
        version="1.0.0",
        changelog_preview="- ...",
        mr_target_branch="main",
        changelog_file="CHANGELOG.md",
        pyproject_file="pyproject.toml",
        gitlab_token="",
        dry_run=True,
        logger=None,
    )
    assert ok is True and calls.get("gh") is True


def test_create_merge_request_dispatch_gitlab(monkeypatch):
    calls = {}
    monkeypatch.setattr("releaser.drafter.utils.get_remote_type", lambda: "gitlab")
    monkeypatch.setattr(
        mr, "create_gitlab_mr", lambda *a, **k: calls.setdefault("gl", True)
    )
    ok = mr.create_merge_request(
        branch_name="release/v1.0.0",
        version="1.0.0",
        changelog_preview="- ...",
        mr_target_branch="main",
        changelog_file="CHANGELOG.md",
        pyproject_file="pyproject.toml",
        gitlab_token="dummy",
        dry_run=True,
        logger=None,
    )
    assert ok is True and calls.get("gl") is True

