from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, Optional

import toml

from .model import AppConfig, BumpRulesConfig, DefaultsConfig, PreReleaseConfig, ProjectConfig, ChangelogConfig


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

    changelog = data.get("changelog", {}) or {}
    if changelog:
        if "enabled" in changelog:
            cfg.changelog.enabled = bool(changelog.get("enabled"))
        if "file" in changelog:
            cfg.changelog.file = str(changelog.get("file"))
        if "mode" in changelog:
            cfg.changelog.mode = str(changelog.get("mode"))

    safety = data.get("safety", {}) or {}
    if safety:
        if "allow_dirty" in safety:
            cfg.safety.allow_dirty = bool(safety.get("allow_dirty"))

    # Prefer new key 'version_targets', but support legacy 'files' for backward compatibility
    files = data.get("version_targets")
    if files is None:
        files = data.get("files")
    if not files:
        # Some configs may place files under sections; accept project/pre_release placements
        pre = data.get("pre_release", {}) or {}
        files = pre.get("version_targets") or pre.get("files")
    if not files:
        proj = data.get("project", {}) or {}
        files = proj.get("version_targets") or proj.get("files")
    if files:
        cfg.files = list(files or [])

    # AI block (optional)
    ai = data.get("ai", {}) or {}
    if ai:
        if "enabled" in ai:
            cfg.ai.enabled = bool(ai.get("enabled"))
        if "provider" in ai:
            cfg.ai.provider = str(ai.get("provider")) or "openai"
        if "model" in ai:
            cfg.ai.model = str(ai.get("model")) or "gpt-4o-mini"
        if "api_key_env" in ai:
            cfg.ai.api_key_env = str(ai.get("api_key_env")) or "OPENAI_API_KEY"
        if "temperature" in ai:
            try:
                cfg.ai.temperature = float(ai.get("temperature"))
            except Exception:
                pass
        if "max_tokens" in ai:
            try:
                cfg.ai.max_tokens = int(ai.get("max_tokens"))
            except Exception:
                pass
        if "prompt_release_notes_file" in ai:
            cfg.ai.prompt_release_notes_file = ai.get("prompt_release_notes_file")
        if "system_prompt_file" in ai:
            cfg.ai.system_prompt_file = ai.get("system_prompt_file")
        if "include_diff" in ai:
            cfg.ai.include_diff = bool(ai.get("include_diff"))
        if "max_commits" in ai:
            try:
                cfg.ai.max_commits = int(ai.get("max_commits"))
            except Exception:
                pass
        if "always_diff_types" in ai:
            try:
                cfg.ai.always_diff_types = list(ai.get("always_diff_types") or [])
            except Exception:
                cfg.ai.always_diff_types = []
        if "cache" in ai:
            cfg.ai.cache = bool(ai.get("cache"))
        if "accept_automatically" in ai:
            cfg.ai.accept_automatically = bool(ai.get("accept_automatically"))
        if "fail_on_error" in ai:
            cfg.ai.fail_on_error = bool(ai.get("fail_on_error"))
        if "always_diff_types" in ai:
            cfg.ai.always_diff_types = list(ai.get("always_diff_types") or [])

    # Commit lint block (optional)
    cl = data.get("commit_lint", {}) or {}
    if cl:
        if "enabled" in cl:
            cfg.commit_lint.enabled = bool(cl.get("enabled"))
        if "types" in cl:
            cfg.commit_lint.types = list(cl.get("types") or [])
        if "require_scope" in cl:
            cfg.commit_lint.require_scope = bool(cl.get("require_scope"))
        if "scopes" in cl:
            cfg.commit_lint.scopes = list(cl.get("scopes") or [])
        if "scope_pattern" in cl:
            cfg.commit_lint.scope_pattern = cl.get("scope_pattern") or None
        if "subject_max_length" in cl:
            try:
                cfg.commit_lint.subject_max_length = int(cl.get("subject_max_length"))
            except Exception:
                pass
        if "allow_bang" in cl:
            cfg.commit_lint.allow_bang = bool(cl.get("allow_bang"))
        if "allow_breaking_footer" in cl:
            cfg.commit_lint.allow_breaking_footer = bool(cl.get("allow_breaking_footer"))
        if "require_ticket" in cl:
            cfg.commit_lint.require_ticket = bool(cl.get("require_ticket"))
        if "ticket_pattern" in cl:
            cfg.commit_lint.ticket_pattern = cl.get("ticket_pattern") or None
        if "skip_merge_commits" in cl:
            cfg.commit_lint.skip_merge_commits = bool(cl.get("skip_merge_commits"))
        if "skip_revert_commits" in cl:
            cfg.commit_lint.skip_revert_commits = bool(cl.get("skip_revert_commits"))

    # Commit gen block (optional)
    cg = data.get("commit_gen", {}) or {}
    if cg:
        if "history_commits" in cg:
            try:
                cfg.commit_gen.history_commits = int(cg.get("history_commits"))
            except Exception:
                pass
        if "demote_feat_if_similar" in cg:
            cfg.commit_gen.demote_feat_if_similar = bool(cg.get("demote_feat_if_similar"))
        if "allow_scope" in cg:
            cfg.commit_gen.allow_scope = bool(cg.get("allow_scope"))

    # New schema: [llm] mirrors AI settings
    llm = data.get("llm", {}) or {}
    if llm:
        if "enabled" in llm:
            cfg.ai.enabled = bool(llm.get("enabled"))
        if "model" in llm:
            cfg.ai.model = str(llm.get("model") or cfg.ai.model)
        if "api_key_env" in llm:
            cfg.ai.api_key_env = str(llm.get("api_key_env") or cfg.ai.api_key_env)
        if "temperature" in llm:
            try:
                cfg.ai.temperature = float(llm.get("temperature"))
            except Exception:
                pass
        if "max_tokens" in llm:
            try:
                cfg.ai.max_tokens = int(llm.get("max_tokens"))
            except Exception:
                pass

    # New schema alias: [llm-config]
    llmc = data.get("llm-config", {}) or {}
    if llmc:
        if "enabled" in llmc:
            cfg.ai.enabled = bool(llmc.get("enabled"))
        if "model" in llmc:
            cfg.ai.model = str(llmc.get("model") or cfg.ai.model)
        if "api_key_env" in llmc:
            cfg.ai.api_key_env = str(llmc.get("api_key_env") or cfg.ai.api_key_env)
        if "temperature" in llmc:
            try:
                cfg.ai.temperature = float(llmc.get("temperature"))
            except Exception:
                pass
        if "max_tokens" in llmc:
            try:
                cfg.ai.max_tokens = int(llmc.get("max_tokens"))
            except Exception:
                pass
        if "prompt_release_notes_file" in llmc:
            cfg.ai.prompt_release_notes_file = llmc.get("prompt_release_notes_file")
        if "system_prompt_file" in llmc:
            cfg.ai.system_prompt_file = llmc.get("system_prompt_file")
        if "include_diff" in llmc:
            cfg.ai.include_diff = bool(llmc.get("include_diff"))
        if "max_commits" in llmc:
            try:
                cfg.ai.max_commits = int(llmc.get("max_commits"))
            except Exception:
                pass
        if "always_diff_types" in llmc:
            try:
                cfg.ai.always_diff_types = list(llmc.get("always_diff_types") or [])
            except Exception:
                cfg.ai.always_diff_types = []
        if "cache" in llmc:
            cfg.ai.cache = bool(llmc.get("cache"))
        if "accept_automatically" in llmc:
            cfg.ai.accept_automatically = bool(llmc.get("accept_automatically"))
        if "fail_on_error" in llmc:
            cfg.ai.fail_on_error = bool(llmc.get("fail_on_error"))

    # New schema: [release] aggregates defaults/changelog/safety
    rel = data.get("release", {}) or {}
    if rel:
        if "create_commit" in rel:
            cfg.defaults.commit = bool(rel.get("create_commit"))
        if "create_tag" in rel:
            cfg.defaults.tag = bool(rel.get("create_tag"))
        if "push" in rel:
            cfg.defaults.push = bool(rel.get("push"))
        if "change_log_file" in rel:
            cfg.changelog.file = str(rel.get("change_log_file") or cfg.changelog.file)
        if "allow_dirty" in rel:
            cfg.safety.allow_dirty = bool(rel.get("allow_dirty"))
        # strategy is currently informational; range is still derived from tags

        # Nested: [release.pre_release]
        rpre = rel.get("pre_release", {}) or {}
        if rpre:
            if "enabled" in rpre:
                cfg.pre_release.enabled = bool(rpre.get("enabled"))
            if "default_channel" in rpre:
                cfg.pre_release.default_channel = str(rpre.get("default_channel") or cfg.pre_release.default_channel)
            if "auto_increment" in rpre:
                cfg.pre_release.auto_increment = bool(rpre.get("auto_increment"))
            if "reset_on_bump" in rpre:
                cfg.pre_release.reset_on_bump = bool(rpre.get("reset_on_bump"))

        # Nested: [release.auto_gen_notes]
        rn = rel.get("auto_gen_notes", {}) or {}
        if rn:
            if "enabled" in rn:
                cfg.changelog.enabled = bool(rn.get("enabled"))
            if "include_diff" in rn:
                cfg.ai.include_diff = bool(rn.get("include_diff"))
            if "max_commits" in rn:
                try:
                    cfg.ai.max_commits = int(rn.get("max_commits"))
                except Exception:
                    pass
            if "mode" in rn:
                cfg.changelog.mode = str(rn.get("mode") or cfg.changelog.mode)

    # New schema: [auto_gen_commit] mirrors commit_gen
    agc = data.get("auto_gen_commit", {}) or {}
    if agc:
        if "history_commits" in agc:
            try:
                cfg.commit_gen.history_commits = int(agc.get("history_commits"))
            except Exception:
                pass
        if "demote_feat_if_similar" in agc:
            cfg.commit_gen.demote_feat_if_similar = bool(agc.get("demote_feat_if_similar"))


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
