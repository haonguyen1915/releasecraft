from releaser.config.load import load_config


def test_load_config_repo_local(tmp_path, monkeypatch):
    # Create repo config using new format
    cfg_text = """
[project]
type = "poetry"
tag_prefix = "v"
use_native = true

[release]
create_commit = true
create_tag = true
push = false
version_targets = ["pkg/__init__.py:__version__"]
change_log_file = "CHANGELOG.md"
allow_dirty = false

[release.version]
strategy = "auto"
since = ""
to = "HEAD"

[release.pre_release]
enabled = true
default_channel = "rc"
auto_increment = true
reset_on_bump = true
apply = ["release/*"]
block = ["main"]

[release.change_log]
enabled = true
file = "CHANGELOG.md"
mode = "auto"

[release.auto_gen_notes]
enabled = false
include_diff = false
always_diff_types = []
max_commits = 200
mode = "auto"

[llm-config]
enabled = false
provider = "openai"
model = "gpt-4o-mini"
api_key_env = "OPENAI_API_KEY"
temperature = 0.2
max_tokens = 800
cache = true
accept_automatically = false
fail_on_error = false
"""
    (tmp_path / ".releaser.toml").write_text(cfg_text.strip() + "\n")
    monkeypatch.chdir(tmp_path)

    cfg = load_config()
    # Test project settings
    assert cfg.project.type == "poetry"
    assert cfg.project.tag_prefix == "v"
    assert cfg.project.use_native is True

    # Test release settings
    assert cfg.release.create_commit is True
    assert cfg.release.create_tag is True
    assert cfg.release.push is False
    assert cfg.release.version_targets == ["pkg/__init__.py:__version__"]
    assert cfg.release.allow_dirty is False

    # Test pre-release settings
    assert cfg.release.pre_release.enabled is True
    assert cfg.release.pre_release.default_channel == "rc"
    assert cfg.release.pre_release.apply == ["release/*"]
    assert cfg.release.pre_release.block == ["main"]

    # Test backward compatibility properties
    assert cfg.defaults.commit is True
    assert cfg.defaults.push is False
    assert cfg.pre_release.enabled is True
    assert cfg.files == ["pkg/__init__.py:__version__"]
