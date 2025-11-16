from __future__ import annotations

import os
from pathlib import Path
from typing import Dict, List, Optional


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
    _pre_channel_map = _parse_channel_map(getattr(args, "pre_channel_map", ""))

    _bump_apply = _parse_csv_list(getattr(args, "bump_apply", ""))
    _bump_block = _parse_csv_list(getattr(args, "bump_block", ""))

    yes = bool(getattr(args, "yes", False))
    global_flag = bool(getattr(args, "global_cfg", False))
    cfg_path = _default_path(global_flag, getattr(args, "path", None))

    if not yes:
        # Minimal interactive prompts only (keep CLI minimal, config full by default)
        # Show defaults explicitly in the prompt text for clarity
        project_type = prompt_choice(
            f"Project type [default: {project_type}]",
            ["auto", "poetry", "setuptools", "npm"],
            default=project_type,
        )
        tag_prefix = prompt_input(
            f"Tag prefix [default: {tag_prefix}]", default=tag_prefix
        )
        use_native = prompt_confirmation(
            f"Use native tooling when available? [default: {'Yes' if True else 'No'}]",
            default=True,
        )

        pre_enabled = prompt_confirmation(
            f"Enable pre-release? [default: {'Yes' if True else 'No'}]", default=True
        )
        if pre_enabled:
            pre_channel = prompt_choice(
                f"Default pre-release channel [default: {pre_channel}]",
                ["alpha", "beta", "rc", "custom"],
                default=pre_channel,
            )
            if pre_channel == "custom":
                pre_channel = (
                    prompt_input(
                        "Enter custom channel [default: rc]", default="rc"
                    ).strip()
                    or "rc"
                )

        files_str = prompt_input(
            "Version file targets (comma, PATH:selector) [default: none]",
            default="",
        ).strip()
        files_flag = _parse_csv_list(files_str)

    # Build config document using new schema format
    doc: Dict[str, object] = {
        "project": {
            "type": project_type,
            "tag_prefix": tag_prefix,
            "use_native": use_native,
        },
        "release": {
            "create_commit": commit,
            "create_tag": tag,
            "push": push,
            "version_targets": files_flag,
            "change_log_file": "CHANGELOG.md",
            "allow_dirty": False,
            "version": {
                "strategy": "auto",
                "since": "",
                "to": "HEAD",
                "source": "file",
            },
            "pre_release": {
                "enabled": pre_enabled,
                "default_channel": pre_channel,
                "auto_increment": True,
                "reset_on_bump": True,
                "apply": pre_apply,
                "block": pre_block,
            },
            "change_log": {
                "enabled": True,
                "file": "CHANGELOG.md",
                "mode": "auto",
            },
            "auto_gen_notes": {
                "enabled": False,
                "include_diff": False,
                "always_diff_types": [],
                "max_commits": 200,
                "mode": "auto",
            },
        },
        "llm-config": {
            "enabled": False,
            "provider": "openai",
            "model": "gpt-4o-mini",
            "api_key_env": "OPENAI_API_KEY",
            "temperature": 0.2,
            "max_tokens": 2500,
            "cache": True,
            "accept_automatically": False,
            "fail_on_error": False,
        },
        "hooks": {
            "pre_bump": [],
            "post_bump": [],
        },
    }

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

    # Render a fully commented, self-documenting configuration file
    content = _render_full_config(doc)
    with cfg_path.open("w", encoding="utf-8") as f:
        f.write(content)

    logger.success(f"Wrote config to {cfg_path}")
    return 0


def _render_full_config(doc: Dict[str, object]) -> str:
    """Render a full TOML config with explanations and examples in new schema format.

    We serialize all supported options with inline comments so users
    can learn and tweak without reading external docs.
    """

    def b(v: bool) -> str:
        return "true" if v else "false"

    def list_str(items: List[str]) -> str:
        if not items:
            return "[]"
        inner = ", ".join(f'"{x}"' for x in items)
        return f"[{inner}]"

    project = doc.get("project", {}) or {}
    release = doc.get("release", {}) or {}
    version_cfg = release.get("version", {}) if isinstance(release, dict) else {}  # type: ignore
    pre_release = release.get("pre_release", {}) if isinstance(release, dict) else {}  # type: ignore
    change_log = release.get("change_log", {}) if isinstance(release, dict) else {}  # type: ignore
    auto_gen_notes = (
        release.get("auto_gen_notes", {}) if isinstance(release, dict) else {}
    )  # type: ignore
    llm = doc.get("llm-config", {}) or {}
    hooks = doc.get("hooks", {}) or {}
    providers = doc.get("provider", {}) or {}

    lines: List[str] = []
    lines.append("\n")
    lines.append("# --- Core Project Settings ---\n")
    lines.append("[project]\n")
    lines.append("# Provider type: auto|poetry|setuptools|npm\n")
    lines.append(f"type = \"{project.get('type', 'auto')}\"\n")
    lines.append("# Tag prefix for git tags (e.g., v1.2.3)\n")
    lines.append(f"tag_prefix = \"{project.get('tag_prefix', 'v')}\"\n")
    lines.append(
        "# Prefer running native tooling (poetry version / npm version) when available\n"
    )
    lines.append(f"use_native = {b(bool(project.get('use_native', True)))}\n")

    lines.append("\n\n# --- Release Configuration ---\n")
    lines.append("[release]\n")
    lines.append(
        f"create_commit = {b(bool(release.get('create_commit', True)) if isinstance(release, dict) else True)}\n"
    )
    lines.append(
        f"create_tag = {b(bool(release.get('create_tag', True)) if isinstance(release, dict) else True)}\n"
    )
    lines.append(
        f"push = {b(bool(release.get('push', False)) if isinstance(release, dict) else False)}\n"
    )
    version_targets = (
        list(release.get("version_targets", []) or [])
        if isinstance(release, dict)
        else []
    )
    lines.append(f"version_targets = {list_str(version_targets)}\n")
    lines.append(
        f"change_log_file = \"{release.get('change_log_file', 'CHANGELOG.md') if isinstance(release, dict) else 'CHANGELOG.md'}\"\n"
    )
    lines.append(
        f"allow_dirty = {b(bool(release.get('allow_dirty', False)) if isinstance(release, dict) else False)}\n"
    )

    lines.append("\n[release.version]\n")
    lines.append(
        f"strategy = \"{version_cfg.get('strategy', 'auto') if isinstance(version_cfg, dict) else 'auto'}\"\n"
    )
    lines.append(
        f"since = \"{version_cfg.get('since', '') if isinstance(version_cfg, dict) else ''}\"\n"
    )
    lines.append(
        f"to = \"{version_cfg.get('to', 'HEAD') if isinstance(version_cfg, dict) else 'HEAD'}\"\n"
    )
    # How to resolve the current version used as the bump base
    # Options: file|local_tag|remote_tag|auto
    lines.append(
        f"source = \"{version_cfg.get('source', 'file') if isinstance(version_cfg, dict) else 'file'}\"\n"
    )

    lines.append("\n[release.pre_release]\n")
    lines.append(
        f"enabled = {b(bool(pre_release.get('enabled', False)) if isinstance(pre_release, dict) else False)}\n"
    )
    lines.append(
        f"default_channel = \"{pre_release.get('default_channel', 'rc') if isinstance(pre_release, dict) else 'rc'}\"\n"
    )
    lines.append(
        f"auto_increment = {b(bool(pre_release.get('auto_increment', True)) if isinstance(pre_release, dict) else True)}\n"
    )
    lines.append(
        f"reset_on_bump = {b(bool(pre_release.get('reset_on_bump', True)) if isinstance(pre_release, dict) else True)}\n"
    )
    pre_apply = (
        list(
            pre_release.get("apply", ["develop", "release/*"])
            or ["develop", "release/*"]
        )
        if isinstance(pre_release, dict)
        else ["develop", "release/*"]
    )
    pre_block = (
        list(
            pre_release.get("block", ["main", "master", "hotfix/*"])
            or ["main", "master", "hotfix/*"]
        )
        if isinstance(pre_release, dict)
        else ["main", "master", "hotfix/*"]
    )
    lines.append(f"apply = {list_str(pre_apply)}\n")
    lines.append(f"block = {list_str(pre_block)}\n")

    lines.append("\n[release.change_log]\n")
    lines.append(
        "# Auto mode derives sections from commits; 'notes' includes only user notes\n"
    )
    lines.append(
        f"enabled = {b(bool(change_log.get('enabled', True)) if isinstance(change_log, dict) else True)}\n"
    )
    lines.append(
        f"file = \"{change_log.get('file', 'CHANGELOG.md') if isinstance(change_log, dict) else 'CHANGELOG.md'}\"\n"
    )
    lines.append(
        f"mode = \"{change_log.get('mode', 'auto') if isinstance(change_log, dict) else 'auto'}\"\n"
    )

    lines.append("\n[release.auto_gen_notes]\n")
    lines.append("# AI-powered release notes generation\n")
    lines.append(
        f"enabled = {b(bool(auto_gen_notes.get('enabled', False)) if isinstance(auto_gen_notes, dict) else False)}\n"
    )
    lines.append(
        f"include_diff = {b(bool(auto_gen_notes.get('include_diff', True)) if isinstance(auto_gen_notes, dict) else True)}\n"
    )
    always_diff = (
        list(auto_gen_notes.get("always_diff_types", ["feat"]) or ["feat"])
        if isinstance(auto_gen_notes, dict)
        else ["feat"]
    )
    lines.append(f"always_diff_types = {list_str(always_diff)}\n")
    lines.append(
        f"max_commits = {int(auto_gen_notes.get('max_commits', 200)) if isinstance(auto_gen_notes, dict) else 200}\n"
    )
    lines.append(
        f"mode = \"{auto_gen_notes.get('mode', 'auto') if isinstance(auto_gen_notes, dict) else 'auto'}\"\n"
    )

    lines.append("\n\n# --- LLM Configuration ---\n")
    lines.append("[llm-config]\n")
    lines.append(
        "# Advanced LLM configuration for release notes and commit message generation\n"
    )
    lines.append(f"enabled = {b(bool(llm.get('enabled', False)))}\n")
    lines.append(f"provider = \"{llm.get('provider', 'openai')}\"\n")
    lines.append(f"model = \"{llm.get('model', 'gpt-4o-mini')}\"\n")
    lines.append(f"api_key_env = \"{llm.get('api_key_env', 'OPENAI_API_KEY')}\"\n")
    lines.append(f"temperature = {float(llm.get('temperature', 0.2))}\n")
    lines.append(f"max_tokens = {int(llm.get('max_tokens', 2500))}\n")
    lines.append("# Prompt overrides (optional)\n")
    lines.append('# prompt_release_notes_file = "path/to/custom_release_notes.md.j2"\n')
    lines.append('# system_prompt_file = "path/to/custom_system_prompt.md"\n')
    lines.append("# Caching and safety\n")
    lines.append(f"cache = {b(bool(llm.get('cache', True)))}\n")
    lines.append(
        f"accept_automatically = {b(bool(llm.get('accept_automatically', False)))}\n"
    )
    lines.append(f"fail_on_error = {b(bool(llm.get('fail_on_error', False)))}\n")

    lines.append("\n\n# --- Hooks ---\n")
    lines.append("[hooks]\n")
    lines.append("# Shell commands to run before/after bump (optional)\n")
    pre_bump = list(hooks.get("pre_bump", []) or []) if isinstance(hooks, dict) else []
    post_bump = (
        list(hooks.get("post_bump", []) or []) if isinstance(hooks, dict) else []
    )
    lines.append(f"pre_bump = {list_str(pre_bump)}\n")
    lines.append(f"post_bump = {list_str(post_bump)}\n")

    # Only show provider section for the selected project type
    lines.append("\n\n# --- Provider-Specific Configuration ---\n")
    project_type = project.get("type", "auto") if isinstance(project, dict) else "auto"

    if isinstance(providers, dict):
        if project_type == "poetry" and "poetry" in providers:
            lines.append("[provider.poetry]\n")
            lines.append("# Prefer `poetry version` when available\n")
            lines.append("prefer_command = true\n")
            lines.append("\n")
        elif project_type == "setuptools" and "setuptools" in providers:
            lines.append("[provider.setuptools]\n")
            lines.append("# __init__ version file for setuptools projects\n")
            lines.append('version_file = "pkg/__init__.py"\n')
            lines.append("\n")
        elif project_type == "npm" and "npm" in providers:
            lines.append("[provider.npm]\n")
            lines.append("# Prefer `npm version`; workspace is for monorepos\n")
            lines.append("prefer_command = true\n")
            lines.append("workspace = false\n")
            lines.append("\n")
        elif project_type == "auto":
            # For 'auto', show all providers as stubs for reference
            if "poetry" in providers:
                lines.append("[provider.poetry]\n")
                lines.append("# Prefer `poetry version` when available\n")
                lines.append("prefer_command = true\n")
                lines.append("\n")
            if "setuptools" in providers:
                lines.append("[provider.setuptools]\n")
                lines.append("# __init__ version file for setuptools projects\n")
                lines.append('version_file = "pkg/__init__.py"\n')
                lines.append("\n")
            if "npm" in providers:
                lines.append("[provider.npm]\n")
                lines.append("# Prefer `npm version`; workspace is for monorepos\n")
                lines.append("prefer_command = true\n")
                lines.append("workspace = false\n")
                lines.append("\n")

    lines.append("\n# --- Commit Linting ---\n")
    lines.append("[commit_lint]\n")
    lines.append("# Conventional Commit enforcement for commit-msg hook\n")
    lines.append("enabled = true\n")
    lines.append(
        'types = ["feat", "fix", "docs", "chore", "refactor", "perf", "test", "build", "ci", "revert", "style"]\n'
    )
    lines.append("skip_merge_commits = true\n")
    lines.append("skip_revert_commits = true\n")

    lines.append("\n\n# --- Commit Generation ---\n")
    lines.append("[commit_gen]\n")
    lines.append("# Controls `releaser commit-gen` behavior\n")
    lines.append("history_commits = 10\n")
    lines.append("demote_feat_if_similar = true\n")
    lines.append("allow_scope = false\n")

    return "".join(lines)
