from releaser.config.model import AppConfig
from releaser.bump.rules import (
    check_bump_allowed,
    check_prerelease_allowed,
)


def _cfg() -> AppConfig:
    return AppConfig()


def test_bump_rules_allow_default(monkeypatch):
    cfg = _cfg()
    # No gating by default
    monkeypatch.setattr("releaser.bump.rules.current_branch", lambda: "feature/x")
    allowed, reason = check_bump_allowed(cfg)
    assert allowed is True and reason is None


def test_bump_rules_block(monkeypatch):
    cfg = _cfg()
    cfg.bump_rules.block = ["main", "master"]
    monkeypatch.setattr("releaser.bump.rules.current_branch", lambda: "main")
    allowed, reason = check_bump_allowed(cfg)
    assert allowed is False
    assert "bump_rules.block" in (reason or "")


def test_prerelease_rules_apply_and_channel_map(monkeypatch):
    cfg = _cfg()
    cfg.release.pre_release.enabled = True
    cfg.release.pre_release.apply = ["develop", "release/*"]
    # Note: channel_map is not in the new schema, testing default channel instead

    monkeypatch.setattr("releaser.bump.rules.current_branch", lambda: "develop")
    allowed, reason, channel = check_prerelease_allowed(cfg)
    assert allowed is True and channel == cfg.release.pre_release.default_channel

    monkeypatch.setattr("releaser.bump.rules.current_branch", lambda: "feature/x")
    allowed, reason, _ = check_prerelease_allowed(cfg)
    assert allowed is False
