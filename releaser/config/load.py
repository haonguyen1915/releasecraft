from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, Optional

import toml

from .model import (
    AppConfig,
)


def _merge_into_config(cfg: AppConfig, data: Dict[str, Any]) -> None:
    """Merge TOML data into AppConfig using new schema format."""

    # [project] section
    project = data.get("project", {}) or {}
    if project:
        cfg.project.type = str(project.get("type", cfg.project.type))
        cfg.project.tag_prefix = str(project.get("tag_prefix", cfg.project.tag_prefix))
        if "use_native" in project:
            cfg.project.use_native = bool(project.get("use_native"))

    # [release] section
    rel = data.get("release", {}) or {}
    if rel:
        if "create_commit" in rel:
            cfg.release.create_commit = bool(rel.get("create_commit"))
        if "create_tag" in rel:
            cfg.release.create_tag = bool(rel.get("create_tag"))
        if "push" in rel:
            cfg.release.push = bool(rel.get("push"))
        if "version_targets" in rel:
            cfg.release.version_targets = list(rel.get("version_targets") or [])
        if "change_log_file" in rel:
            cfg.release.change_log_file = str(
                rel.get("change_log_file") or cfg.release.change_log_file
            )
        if "allow_dirty" in rel:
            cfg.release.allow_dirty = bool(rel.get("allow_dirty"))

        # [release.version] subsection
        rver = rel.get("version", {}) or {}
        if rver:
            if "strategy" in rver:
                cfg.release.version.strategy = str(
                    rver.get("strategy") or cfg.release.version.strategy
                )
            if "since" in rver:
                cfg.release.version.since = str(
                    rver.get("since") or cfg.release.version.since
                )
            if "to" in rver:
                cfg.release.version.to = str(rver.get("to") or cfg.release.version.to)
            if "source" in rver:
                try:
                    src = str(rver.get("source") or cfg.release.version.source)
                    if src in {"file", "local_tag", "remote_tag", "auto"}:
                        cfg.release.version.source = src
                except Exception:
                    pass

        # [release.pre_release] subsection
        rpre = rel.get("pre_release", {}) or {}
        if rpre:
            if "enabled" in rpre:
                cfg.release.pre_release.enabled = bool(rpre.get("enabled"))
            if "default_channel" in rpre:
                cfg.release.pre_release.default_channel = str(
                    rpre.get("default_channel")
                    or cfg.release.pre_release.default_channel
                )
            if "auto_increment" in rpre:
                cfg.release.pre_release.auto_increment = bool(
                    rpre.get("auto_increment")
                )
            if "reset_on_bump" in rpre:
                cfg.release.pre_release.reset_on_bump = bool(rpre.get("reset_on_bump"))
            if "apply" in rpre:
                cfg.release.pre_release.apply = list(rpre.get("apply") or [])
            if "block" in rpre:
                cfg.release.pre_release.block = list(rpre.get("block") or [])

        # [release.change_log] subsection
        rcl = rel.get("change_log", {}) or {}
        if rcl:
            if "enabled" in rcl:
                cfg.release.change_log.enabled = bool(rcl.get("enabled"))
            if "file" in rcl:
                cfg.release.change_log.file = str(
                    rcl.get("file") or cfg.release.change_log.file
                )
            if "mode" in rcl:
                cfg.release.change_log.mode = str(
                    rcl.get("mode") or cfg.release.change_log.mode
                )

        # [release.auto_gen_notes] subsection
        rn = rel.get("auto_gen_notes", {}) or {}
        if rn:
            if "enabled" in rn:
                cfg.release.auto_gen_notes.enabled = bool(rn.get("enabled"))
            if "include_diff" in rn:
                cfg.release.auto_gen_notes.include_diff = bool(rn.get("include_diff"))
            if "always_diff_types" in rn:
                cfg.release.auto_gen_notes.always_diff_types = list(
                    rn.get("always_diff_types") or []
                )
            if "max_commits" in rn:
                try:
                    cfg.release.auto_gen_notes.max_commits = int(rn.get("max_commits"))
                except Exception:
                    pass
            if "mode" in rn:
                cfg.release.auto_gen_notes.mode = str(
                    rn.get("mode") or cfg.release.auto_gen_notes.mode
                )

    # [llm] or [llm-config] section
    llm = data.get("llm", {}) or data.get("llm-config", {}) or {}
    if llm:
        if "enabled" in llm:
            cfg.llm.enabled = bool(llm.get("enabled"))
        if "provider" in llm:
            cfg.llm.provider = str(llm.get("provider") or cfg.llm.provider)
        if "model" in llm:
            cfg.llm.model = str(llm.get("model") or cfg.llm.model)
        if "api_key_env" in llm:
            cfg.llm.api_key_env = str(llm.get("api_key_env") or cfg.llm.api_key_env)
        if "temperature" in llm:
            try:
                cfg.llm.temperature = float(llm.get("temperature"))
            except Exception:
                pass
        if "max_tokens" in llm:
            try:
                cfg.llm.max_tokens = int(llm.get("max_tokens"))
            except Exception:
                pass
        if "cache" in llm:
            cfg.llm.cache = bool(llm.get("cache"))
        if "accept_automatically" in llm:
            cfg.llm.accept_automatically = bool(llm.get("accept_automatically"))
        if "fail_on_error" in llm:
            cfg.llm.fail_on_error = bool(llm.get("fail_on_error"))
        if "prompt_release_notes_file" in llm:
            cfg.llm.prompt_release_notes_file = llm.get("prompt_release_notes_file")
        if "system_prompt_file" in llm:
            cfg.llm.system_prompt_file = llm.get("system_prompt_file")

    # [hooks] section
    hooks = data.get("hooks", {}) or {}
    if hooks:
        if "pre_bump" in hooks:
            cfg.hooks.pre_bump = list(hooks.get("pre_bump") or [])
        if "post_bump" in hooks:
            cfg.hooks.post_bump = list(hooks.get("post_bump") or [])

    # [commit_lint] section
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
            cfg.commit_lint.allow_breaking_footer = bool(
                cl.get("allow_breaking_footer")
            )
        if "require_ticket" in cl:
            cfg.commit_lint.require_ticket = bool(cl.get("require_ticket"))
        if "ticket_pattern" in cl:
            cfg.commit_lint.ticket_pattern = cl.get("ticket_pattern") or None
        if "skip_merge_commits" in cl:
            cfg.commit_lint.skip_merge_commits = bool(cl.get("skip_merge_commits"))
        if "skip_revert_commits" in cl:
            cfg.commit_lint.skip_revert_commits = bool(cl.get("skip_revert_commits"))

    # [commit_gen] section
    cg = data.get("commit_gen", {}) or {}
    if cg:
        if "history_commits" in cg:
            try:
                cfg.commit_gen.history_commits = int(cg.get("history_commits"))
            except Exception:
                pass
        if "demote_feat_if_similar" in cg:
            cfg.commit_gen.demote_feat_if_similar = bool(
                cg.get("demote_feat_if_similar")
            )
        if "allow_scope" in cg:
            cfg.commit_gen.allow_scope = bool(cg.get("allow_scope"))

    # [bump_rules] section
    br = data.get("bump_rules", {}) or {}
    if br:
        if "apply" in br:
            cfg.bump_rules.apply = list(br.get("apply") or [])
        if "block" in br:
            cfg.bump_rules.block = list(br.get("block") or [])

    # [provider] section
    provider = data.get("provider", {}) or {}
    if provider:
        if "poetry" in provider:
            cfg.provider.poetry = dict(provider.get("poetry") or {})
        if "npm" in provider:
            cfg.provider.npm = dict(provider.get("npm") or {})
        if "setuptools" in provider:
            cfg.provider.setuptools = dict(provider.get("setuptools") or {})


def load_config(config_path: Optional[str] = None) -> AppConfig:
    """Load configuration with precedence: explicit path > repo > home > defaults.

    Recognized locations:
      - explicit: config_path
      - repo: ./.releaser.toml or ./.releaser/config.toml
      - home: ~/.releaser/config.toml
    """
    cfg = AppConfig()

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
