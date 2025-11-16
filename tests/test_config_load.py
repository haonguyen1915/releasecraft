import os
from pathlib import Path

from releaser.config.load import load_config


def test_load_config_repo_local(tmp_path, monkeypatch):
    # Create repo config
    cfg_text = """
[project]
type = "poetry"
tag_prefix = "v"
use_native = true

[defaults]
commit = true
tag = true
push = false

[pre_release]
enabled = true
default_channel = "rc"
apply = ["release/*"]
block = ["main"]
"""
    (tmp_path / ".releaser.toml").write_text(cfg_text.strip() + "\n")
    monkeypatch.chdir(tmp_path)

    cfg = load_config()
    assert cfg.project.type == "poetry"
    assert cfg.project.tag_prefix == "v"
    assert cfg.defaults.commit is True and cfg.defaults.push is False
    assert cfg.pre_release.enabled is True
    assert cfg.pre_release.default_channel == "rc"
    assert cfg.pre_release.apply == ["release/*"]
    assert cfg.pre_release.block == ["main"]

