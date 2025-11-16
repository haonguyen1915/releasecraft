from pathlib import Path
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

    assert data["project"]["type"] == "poetry"
    assert data["project"]["tag_prefix"] == "v"
    assert data["project"]["use_native"] is False

    assert data["defaults"]["commit"] is True
    assert data["defaults"]["tag"] is True
    assert data["defaults"]["push"] is False

    assert data["files"] == ["pkg/__init__.py:__version__"]

    pr = data["pre_release"]
    assert pr["enabled"] is True
    assert pr["default_channel"] == "rc"
    assert set(pr.get("apply", [])) == {"release/*", "develop"}
    assert set(pr.get("block", [])) == {"main", "master"}

    br = data.get("bump_rules", {})
    assert set(br.get("apply", [])) == {"develop", "release/*"}
    assert set(br.get("block", [])) == {"main", "master"}

