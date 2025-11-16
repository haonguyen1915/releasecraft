from types import SimpleNamespace

from releaser.drafter import git_operations as go


class Runner:
    def __init__(self):
        self.calls = []

    def run(self, cmd, capture_output=True, text=True, check=True):  # signature similar to utils.run_command
        self.calls.append(list(cmd))
        # Emulate a simple return object with stdout
        return SimpleNamespace(returncode=0, stdout="\n".join(["v0.1.0"]))


def test_create_and_push_tag(monkeypatch):
    runner = Runner()
    monkeypatch.setattr("releaser.drafter.utils.run_command", runner.run)

    # Create tag should succeed and call git tag -a
    assert go.create_git_tag("0.2.0", tag_prefix="v", dry_run=False, logger=None) is True
    assert any(cmd[:3] == ["git", "tag", "-a"] for cmd in runner.calls)

    # Push tag should call git push origin v0.2.0
    runner.calls.clear()
    assert go.push_git_tag("0.2.0", tag_prefix="v", dry_run=False, logger=None) is True
    assert ["git", "push", "origin", "v0.2.0"] in runner.calls


def test_push_tag_dry_run(monkeypatch):
    runner = Runner()
    monkeypatch.setattr("releaser.drafter.utils.run_command", runner.run)
    # Dry-run should not call git
    assert go.push_git_tag("0.3.0", tag_prefix="v", dry_run=True, logger=None) is True
    assert runner.calls == []

