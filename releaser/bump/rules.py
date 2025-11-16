from __future__ import annotations

import fnmatch
from typing import Optional, Tuple

from releaser.drafter import utils as git_utils
from releaser.config.model import AppConfig


def _match_any(name: str, patterns: list[str]) -> bool:
    for pat in patterns:
        if fnmatch.fnmatch(name, pat):
            return True
    return False


def current_branch() -> str:
    b = git_utils.get_current_branch()
    return b or ""


def check_bump_allowed(cfg: AppConfig) -> Tuple[bool, Optional[str]]:
    branch = current_branch()
    # Block has priority
    if cfg.bump_rules.block and _match_any(branch, cfg.bump_rules.block):
        return False, f"Bump is disabled on branch '{branch}' by bump_rules.block rule"
    if cfg.bump_rules.apply:
        if not _match_any(branch, cfg.bump_rules.apply):
            return (
                False,
                f"Bump is disabled on branch '{branch}' (not in bump_rules.apply)",
            )
    return True, None


def check_prerelease_allowed(cfg: AppConfig) -> Tuple[bool, Optional[str], str]:
    """Return (allowed, reason, channel)."""
    if not cfg.release.pre_release.enabled:
        return (
            False,
            "Pre-release disabled by config",
            cfg.release.pre_release.default_channel,
        )

    branch = current_branch()
    if cfg.release.pre_release.block and _match_any(
        branch, cfg.release.pre_release.block
    ):
        return (
            False,
            f"Pre-release is disabled on branch '{branch}' by pre_release.block rule",
            cfg.release.pre_release.default_channel,
        )

    if cfg.release.pre_release.apply:
        if not _match_any(branch, cfg.release.pre_release.apply):
            return (
                False,
                f"Pre-release is disabled on branch '{branch}' (not in pre_release.apply)",
                cfg.release.pre_release.default_channel,
            )

    # channel map override
    channel = cfg.release.pre_release.default_channel
    # Note: channel_map is not in the new schema, skip for now
    # for pat, ch in (cfg.release.pre_release.channel_map or {}).items():
    #     if fnmatch.fnmatch(branch, pat):
    #         channel = ch
    #         break

    return True, None, channel
