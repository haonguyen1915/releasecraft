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

    # Default to enabling pre-release; can be toggled later if needed
    pre_enabled = True
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
        # Minimal interactive prompts only (keep CLI minimal, config full by default)
        project_type = prompt_choice(
            "Project type", ["auto", "poetry", "setuptools", "npm"], default=project_type
        )
        tag_prefix = prompt_input("Tag prefix", default=tag_prefix)
        use_native = prompt_confirmation("Use native tooling when available?", default=True)

        pre_enabled = prompt_confirmation("Enable pre-release?", default=True)
        if pre_enabled:
            pre_channel = prompt_choice(
                "Default pre-release channel", ["alpha", "beta", "rc", "custom"], default=pre_channel
            )
            if pre_channel == "custom":
                pre_channel = prompt_input("Enter custom channel", default="rc").strip() or "rc"

        files_str = prompt_input(
            "Version file targets (comma, PATH:selector) [optional]", default=""
        ).strip()
        files_flag = _parse_csv_list(files_str)

    # Build config document (minimal by default)
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
        "changelog": {
            "enabled": True,
            "file": "CHANGELOG.md",
            "mode": "auto",
        },
        "safety": {
            "allow_dirty": False,
        },
        "ai": {
            "enabled": False,
            "provider": "openai",
            "model": "gpt-4o-mini",
            "api_key_env": "OPENAI_API_KEY",
            "temperature": 0.2,
            "max_tokens": 800,
            "include_diff": False,
            "max_commits": 200,
            "cache": True,
            "accept_automatically": False,
            "fail_on_error": False,
            # Prompt paths are optional; include as commented documentation
            # "prompt_release_notes_file": ".releaser/prompts/release_notes.md.j2",
            # "system_prompt_file": ".releaser/prompts/system.md.j2",
        },
    }

    if files_flag:
        doc["version_targets"] = files_flag

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

    # Always include full template (all supported sections) so config is self-documenting
    doc.setdefault("version_targets", doc.get("version_targets", []))
    doc.setdefault("version", {"strategy": "auto", "since": "", "to": "HEAD"})
    # Include bump_rules even if empty
    doc.setdefault("bump_rules", {"apply": [], "block": []})
    # Ensure pre_release has all keys
    pr = doc.get("pre_release", {})  # type: ignore[assignment]
    if isinstance(pr, dict):
        pr.setdefault("apply", [])
        pr.setdefault("block", [])
        pr.setdefault("channel_map", {})
        doc["pre_release"] = pr
    # Hooks
    doc.setdefault("hooks", {"pre_bump": [], "post_bump": []})
    # Provider sections – include only the selected provider for clarity.
    provider_all = {
        "poetry": {"prefer_command": True},
        "setuptools": {"version_file": "pkg/__init__.py"},
        "npm": {"prefer_command": True, "workspace": False},
    }
    if project_type in ("poetry", "setuptools", "npm"):
        doc["provider"] = {project_type: provider_all[project_type]}
    else:
        # auto: include all provider stubs so users can tweak later
        doc["provider"] = provider_all

    _ensure_parent_dir(cfg_path)
    if cfg_path.exists() and not yes:
        if not prompt_confirmation(f"{cfg_path} exists. Overwrite?", default=False):
            logger.warning("Init cancelled; file not overwritten")
            return 1

    with cfg_path.open("w") as f:
        toml.dump(doc, f)

    logger.success(f"Wrote config to {cfg_path}")
    return 0
