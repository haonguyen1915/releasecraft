from types import SimpleNamespace

import types

import releaser.bump.flow as flow


class DummyResponse:
    def __init__(self, status_code: int = 200, text: str = "") -> None:
        self.status_code = status_code
        self.text = text


def test_parse_repo_slug_supports_common_git_urls():
    cases = {
        "git@gitlab.com:group/project.git": "group/project",
        "git@github.com:owner/repo.git": "owner/repo",
        "ssh://git@gitlab.com/group/project.git": "group/project",
        "https://github.com/owner/repo.git": "owner/repo",
        "https://gitlab.com/group/project": "group/project",
    }
    for url, expected in cases.items():
        assert flow._parse_repo_slug(url) == expected


def test_create_github_draft_release_best_effort(monkeypatch):
    calls = []

    def fake_get_repo_url() -> str:
        return "https://github.com/owner/repo.git"

    def fake_post(url, headers=None, json=None, timeout=None):  # type: ignore[override]
        calls.append(
            {
                "url": url,
                "headers": headers or {},
                "json": json or {},
                "timeout": timeout,
            }
        )
        return DummyResponse(201, "created")

    monkeypatch.setenv("GITHUB_TOKEN", "dummy-token")
    monkeypatch.setenv("GITHUB_API_URL", "https://api.github.com")
    monkeypatch.setattr(flow.git_utils, "get_repo_url", fake_get_repo_url)
    monkeypatch.setattr(flow.requests, "post", fake_post)

    flow._create_github_draft_release("v1.2.3", "body-text")

    assert calls, "Expected at least one HTTP call for GitHub release"
    payload = calls[0]["json"]
    assert payload["tag_name"] == "v1.2.3"
    assert payload["name"] == "v1.2.3"
    assert payload["body"] == "body-text"
    assert payload["draft"] is True


def test_create_gitlab_release_best_effort(monkeypatch):
    calls = []

    def fake_get_repo_url() -> str:
        return "https://gitlab.com/group/project.git"

    def fake_post(url, headers=None, json=None, timeout=None):  # type: ignore[override]
        calls.append(
            {
                "url": url,
                "headers": headers or {},
                "json": json or {},
                "timeout": timeout,
            }
        )
        return DummyResponse(201, "created")

    monkeypatch.setenv("GITLAB_TOKEN", "dummy-token")
    monkeypatch.setenv("GITLAB_API_URL", "https://gitlab.com/api/v4")
    monkeypatch.setattr(flow.git_utils, "get_repo_url", fake_get_repo_url)
    monkeypatch.setattr(flow.requests, "post", fake_post)

    flow._create_gitlab_release("v1.2.3", "body-text")

    assert calls, "Expected at least one HTTP call for GitLab release"
    payload = calls[0]["json"]
    assert payload["tag_name"] == "v1.2.3"
    assert payload["name"] == "v1.2.3"
    assert payload["description"] == "body-text"
