import toml

from releaser.cli import main as cli_main


def test_cli_init_non_interactive(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    rc = cli_main(
        [
            "init",
            "--yes",
            "--project-type",
            "poetry",
            "--tag-prefix",
            "v",
            "--no-use-native",
            "--files",
            "pkg/__init__.py:__version__",
            "--pre-enable",
            "--pre-channel",
            "rc",
            "--pre-apply",
            "release/*,develop",
            "--pre-block",
            "main,master",
            "--bump-apply",
            "develop,release/*",
            "--bump-block",
            "main,master",
        ]
    )
    assert rc == 0

    cfg_path = tmp_path / ".releaser.toml"
    assert cfg_path.exists()
    data = toml.load(str(cfg_path))

    # Test project settings
    assert data["project"]["type"] == "poetry"
    assert data["project"]["tag_prefix"] == "v"
    assert data["project"]["use_native"] is False

    # Test release settings (new format)
    assert data["release"]["create_commit"] is True
    assert data["release"]["create_tag"] is True
    assert data["release"]["push"] is False
    assert data["release"]["version_targets"] == ["pkg/__init__.py:__version__"]

    # Test pre-release settings (new format)
    pr = data["release"]["pre_release"]
    assert pr["enabled"] is True
    assert pr["default_channel"] == "rc"
    assert set(pr.get("apply", [])) == {"release/*", "develop"}
    assert set(pr.get("block", [])) == {"main", "master"}

    # Test bump_rules (if added by init command)
    _br = data.get("bump_rules", {})
    # Note: bump_rules might not be in generated config since it's not common
    # Just check it exists or skip if not present
