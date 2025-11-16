from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, Optional

import toml

from .model import AppConfig, BumpRulesConfig, DefaultsConfig, PreReleaseConfig, ProjectConfig


def _merge_into_config(cfg: AppConfig, data: Dict[str, Any]) -> None:
    project = data.get("project", {}) or {}
    if project:
        cfg.project.type = str(project.get("type", cfg.project.type))
        cfg.project.tag_prefix = str(project.get("tag_prefix", cfg.project.tag_prefix))
        if "use_native" in project:
            cfg.project.use_native = bool(project.get("use_native"))

    defaults = data.get("defaults", {}) or {}
    if defaults:
        if "commit" in defaults:
            cfg.defaults.commit = bool(defaults.get("commit"))
        if "tag" in defaults:
            cfg.defaults.tag = bool(defaults.get("tag"))
        if "push" in defaults:
            cfg.defaults.push = bool(defaults.get("push"))

    pre = data.get("pre_release", {}) or {}
    if pre:
        if "enabled" in pre:
            cfg.pre_release.enabled = bool(pre.get("enabled"))
        if "default_channel" in pre:
            cfg.pre_release.default_channel = str(pre.get("default_channel"))
        if "auto_increment" in pre:
            cfg.pre_release.auto_increment = bool(pre.get("auto_increment"))
        if "reset_on_bump" in pre:
            cfg.pre_release.reset_on_bump = bool(pre.get("reset_on_bump"))
        if "apply" in pre:
            cfg.pre_release.apply = list(pre.get("apply") or [])
        if "block" in pre:
            cfg.pre_release.block = list(pre.get("block") or [])
        if "channel_map" in pre:
            cfg.pre_release.channel_map = dict(pre.get("channel_map") or {})

    bump_rules = data.get("bump_rules", {}) or {}
    if bump_rules:
        if "apply" in bump_rules:
            cfg.bump_rules.apply = list(bump_rules.get("apply") or [])
        if "block" in bump_rules:
            cfg.bump_rules.block = list(bump_rules.get("block") or [])

    files = data.get("files", []) or []
    if files:
        cfg.files = list(files)


def load_config(config_path: Optional[str] = None) -> AppConfig:
    """Load configuration with precedence: explicit path > repo > home > defaults.

    Recognized locations:
      - explicit: config_path
      - repo: ./.releaser.toml or ./.releaser/config.toml
      - home: ~/.releaser/config.toml
    """
    cfg = AppConfig()

    tried: list[str] = []

    def _try(p: Path) -> bool:
        try:
            if p.exists():
                data = toml.load(str(p))
                _merge_into_config(cfg, data)
                cfg.config_path = str(p)
                return True
        except Exception:
            # Best effort - ignore malformed files
            pass
        return False

    # 1) explicit
    if config_path:
        _try(Path(config_path))
        return cfg

    # 2) repo
    repo_paths = [
        Path(".releaser.toml"),
        Path(".releaser/config.toml"),
    ]
    for p in repo_paths:
        if _try(p):
            return cfg

    # 3) home
    home = Path(os.path.expanduser("~"))
    _try(home / ".releaser/config.toml")
    return cfg

