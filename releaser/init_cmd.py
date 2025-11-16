from __future__ import annotations

import os
from pathlib import Path
from typing import Dict, List, Optional

import toml

from .console import logger, prompt_choice, prompt_confirmation, prompt_input


def _parse_csv_list(s: Optional[str]) -> List[str]:
    if not s:
        return []
    return [item.strip() for item in s.split(",") if item.strip()]


def _parse_channel_map(s: Optional[str]) -> Dict[str, str]:
    # Format: branch:channel,branch2:channel2
    entries: Dict[str, str] = {}
    for part in _parse_csv_list(s):
        if ":" in part:
            k, v = part.split(":", 1)
            k = k.strip()
            v = v.strip()
            if k and v:
                entries[k] = v
    return entries


def _default_path(global_flag: bool, path_opt: Optional[str]) -> Path:
    if path_opt:
        return Path(path_opt)
    if global_flag:
        return Path(os.path.expanduser("~/.releaser/config.toml"))
    return Path(".releaser.toml")


def _ensure_parent_dir(p: Path) -> None:
    parent = p.parent
    if not parent.exists():
        parent.mkdir(parents=True, exist_ok=True)


def _yes_to_bool(val: Optional[str], default: bool) -> bool:
    if val is None:
        return default
    v = val.strip().lower()
    return v in ("y", "yes", "true", "1")


def run(args) -> int:
    # Pre-filled values from flags
    project_type = getattr(args, "project_type", None) or "auto"
    tag_prefix = getattr(args, "tag_prefix", None) or "v"
    use_native = True
    if hasattr(args, "use_native") and args.use_native is not None:
        use_native = bool(args.use_native)

    files_flag = getattr(args, "files", None) or []

    commit = not getattr(args, "no_commit", False)
    tag = not getattr(args, "no_tag", False)
    push = bool(getattr(args, "push", False))

    pre_enabled = bool(getattr(args, "pre_enable", False))
    pre_channel = getattr(args, "pre_channel", None) or "rc"
    pre_apply = _parse_csv_list(getattr(args, "pre_apply", ""))
    pre_block = _parse_csv_list(getattr(args, "pre_block", ""))
    pre_channel_map = _parse_channel_map(getattr(args, "pre_channel_map", ""))

    bump_apply = _parse_csv_list(getattr(args, "bump_apply", ""))
    bump_block = _parse_csv_list(getattr(args, "bump_block", ""))

    yes = bool(getattr(args, "yes", False))
    global_flag = bool(getattr(args, "global_cfg", False))
    cfg_path = _default_path(global_flag, getattr(args, "path", None))

    if not yes:
        # Interactive prompts
        project_type = prompt_choice(
            "Project type", ["auto", "poetry", "setuptools", "npm"], default=project_type
        )
        tag_prefix = prompt_input("Tag prefix", default=tag_prefix)
        use_native = prompt_confirmation("Use native tooling when available?", default=True)

        files_str = prompt_input(
            "Version file targets (comma, PATH:selector) [optional]", default=""
        ).strip()
        files_flag = _parse_csv_list(files_str)

        commit = prompt_confirmation("Default commit after bump?", default=True)
        tag = prompt_confirmation("Default create tag?", default=True)
        push = prompt_confirmation("Default push after tag?", default=False)

        pre_enabled = prompt_confirmation("Enable pre-release by default?", default=False)
        pre_channel = prompt_choice(
            "Default pre-release channel", ["alpha", "beta", "rc", "custom"], default=pre_channel
        )
        if pre_channel == "custom":
            pre_channel = prompt_input("Enter custom channel", default="rc").strip() or "rc"

        pre_apply_str = prompt_input(
            "Pre-release allowed branches (comma; glob ok) [optional]", default=""
        )
        pre_apply = _parse_csv_list(pre_apply_str)
        pre_block_str = prompt_input(
            "Pre-release blocked branches (comma; glob ok) [optional]", default=""
        )
        pre_block = _parse_csv_list(pre_block_str)
        pre_map_str = prompt_input(
            "Pre-release channel map (branch:channel, ...) [optional]", default=""
        )
        pre_channel_map = _parse_channel_map(pre_map_str)

        bump_apply_str = prompt_input(
            "Bump allowed branches (comma; glob ok) [optional]", default=""
        )
        bump_apply = _parse_csv_list(bump_apply_str)
        bump_block_str = prompt_input(
            "Bump blocked branches (comma; glob ok) [optional]", default=""
        )
        bump_block = _parse_csv_list(bump_block_str)

    # Build config document
    doc: Dict[str, object] = {
        "project": {
            "type": project_type,
            "tag_prefix": tag_prefix,
            "use_native": use_native,
        },
        "defaults": {"commit": commit, "tag": tag, "push": push},
        "pre_release": {
            "enabled": pre_enabled,
            "default_channel": pre_channel,
            "auto_increment": True,
            "reset_on_bump": True,
        },
    }

    if files_flag:
        doc["files"] = files_flag

    if pre_apply:
        doc["pre_release"]["apply"] = pre_apply  # type: ignore[index]
    if pre_block:
        doc["pre_release"]["block"] = pre_block  # type: ignore[index]
    if pre_channel_map:
        doc["pre_release"]["channel_map"] = pre_channel_map  # type: ignore[index]

    if bump_apply or bump_block:
        br: Dict[str, object] = {}
        if bump_apply:
            br["apply"] = bump_apply
        if bump_block:
            br["block"] = bump_block
        doc["bump_rules"] = br

    _ensure_parent_dir(cfg_path)
    if cfg_path.exists() and not yes:
        if not prompt_confirmation(f"{cfg_path} exists. Overwrite?", default=False):
            logger.warning("Init cancelled; file not overwritten")
            return 1

    with cfg_path.open("w") as f:
        toml.dump(doc, f)

    logger.success(f"Wrote config to {cfg_path}")
    return 0
