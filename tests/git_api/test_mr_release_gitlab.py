from types import SimpleNamespace

from releaser.drafter import mr_release as mr


class FakeGitLabAPI:
    def __init__(self, remote_url, token):
        self.remote_url = remote_url
        self.token = token
        self.created = False

    def create_merge_request(self, source_branch, target_branch, title, description):
        self.created = True
        return {"web_url": "https://gitlab.example.com/group/proj/-/merge_requests/1"}


def test_create_gitlab_mr(monkeypatch):
    monkeypatch.setattr("releaser.drafter.utils.get_remote_url", lambda: "https://gitlab.example.com/group/proj.git")
    monkeypatch.setattr(mr, "GitLabAPI", FakeGitLabAPI)
    ok = mr.create_gitlab_mr(
        branch_name="release/v1.0.0",
        version="1.0.0",
        changelog_preview="- ...",
        mr_target_branch="main",
        changelog_file="CHANGELOG.md",
        pyproject_file="pyproject.toml",
        gitlab_token="TOKEN",
        dry_run=False,
        logger=None,
    )
    assert ok is True

