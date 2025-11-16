from pathlib import Path

from releaser.config.load import load_config


def test_ai_config_loader(tmp_path, monkeypatch):
    cfg_text = """
[ai]
enabled = true
provider = "openai"
model = "gpt-4o-mini"
api_key_env = "OPENAI_API_KEY"
temperature = 0.5
max_tokens = 1234
include_diff = true
max_commits = 50
cache = false
accept_automatically = true
fail_on_error = true
"""
    (tmp_path / ".releaser.toml").write_text(cfg_text.strip() + "\n")
    monkeypatch.chdir(tmp_path)

    cfg = load_config()
    assert cfg.ai.enabled is True
    assert cfg.ai.provider == "openai"
    assert cfg.ai.model == "gpt-4o-mini"
    assert cfg.ai.api_key_env == "OPENAI_API_KEY"
    assert cfg.ai.temperature == 0.5
    assert cfg.ai.max_tokens == 1234
    assert cfg.ai.include_diff is True
    assert cfg.ai.max_commits == 50
    assert cfg.ai.cache is False
    assert cfg.ai.accept_automatically is True
    assert cfg.ai.fail_on_error is True

