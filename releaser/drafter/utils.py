from __future__ import annotations

import os
import re
import subprocess
from typing import Iterable, Optional

"""Lightweight git utilities used by bump flow and rules.

This module intentionally avoids external dependencies and provides
best-effort implementations that are resilient to non-git directories.
"""


def _run_git(
    args: list[str], cwd: str | None = None, check: bool = False
) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(
            ["git", *args],
            cwd=cwd,
            capture_output=True,
            text=True,
            check=check,
        )
    except Exception as e:
        # Return an object with empty stdout/stderr on failure
        cp = subprocess.CompletedProcess(["git", *args], returncode=1)
        cp.stdout = ""
        cp.stderr = str(e)
        return cp


def is_git_repository(cwd: str = ".") -> bool:
    if os.path.isdir(os.path.join(cwd, ".git")):
        return True
    cp = _run_git(["rev-parse", "--is-inside-work-tree"], cwd)
    return cp.returncode == 0 and cp.stdout.strip() == "true"


def get_current_branch(cwd: str = ".") -> str:
    if not is_git_repository(cwd):
        return ""
    cp = _run_git(["rev-parse", "--abbrev-ref", "HEAD"], cwd)
    return cp.stdout.strip() if cp.returncode == 0 else ""


def has_uncommitted_changes(cwd: str = ".") -> bool:
    if not is_git_repository(cwd):
        return False
    cp = _run_git(["status", "--porcelain"], cwd)
    return bool(cp.stdout.strip())


def get_repo_url(cwd: str = ".") -> str:
    if not is_git_repository(cwd):
        return ""
    cp = _run_git(["config", "--get", "remote.origin.url"], cwd)
    return cp.stdout.strip() if cp.returncode == 0 else ""


def get_latest_tag(cwd: str = ".") -> str:
    """Return latest tag name (most recent by creator date)."""
    if not is_git_repository(cwd):
        return ""
    cp = _run_git(["tag", "--list", "--sort=-creatordate"], cwd)
    if cp.returncode != 0:
        return ""
    tags = [t.strip() for t in cp.stdout.splitlines() if t.strip()]
    return tags[0] if tags else ""


def _semver_key(tag: str, prefix: str = "v"):
    # Extract numeric x.y.z from optional prefix
    version = tag
    if prefix and version.startswith(prefix):
        version = version[len(prefix) :]
    m = re.match(r"^(\d+)\.(\d+)\.(\d+)(?:-.+)?(?:\+.+)?$", version)
    if not m:
        return (-1, -1, -1, 1)  # non-matching tags sort last
    major, minor, patch = (int(m.group(1)), int(m.group(2)), int(m.group(3)))
    # Stable > pre-release (approx by presence of '-')
    is_stable = 0 if ("-" in version) else 1
    return (major, minor, patch, is_stable)


def get_latest_remote_tag(
    cwd: str = ".", remote: str = "origin", prefix: Optional[str] = None
) -> str:
    """Return latest tag name found on remote, best-effort.

    Uses `git ls-remote --tags` and selects highest semantic version (optionally by prefix).
    """
    if not is_git_repository(cwd):
        return ""
    cp = _run_git(["ls-remote", "--tags", remote], cwd)
    if cp.returncode != 0:
        return ""
    tags: list[str] = []
    for line in cp.stdout.splitlines():
        # line format: <hash>\trefs/tags/<tag> or refs/tags/<tag>^{}
        if "refs/tags/" not in line:
            continue
        ref = line.split("\t", 1)[-1].strip()
        if ref.endswith("^{}"):
            ref = ref[:-3]
        tag = ref.split("refs/tags/")[-1]
        # Optional prefix filter
        if prefix and not tag.startswith(prefix):
            continue
        tags.append(tag)
    if not tags:
        return ""
    # Choose max by semver-like key (using provided prefix or default 'v')
    pref = prefix if prefix is not None else "v"
    tags.sort(key=lambda t: _semver_key(t, pref))
    return tags[-1]


def get_commits_since_tag(tag: str, cwd: str = ".") -> list[str]:
    if not is_git_repository(cwd):
        return []
    range_ref = f"{tag}..HEAD" if tag else "HEAD"
    fmt = "%H|%s"
    cp = _run_git(["log", "--pretty=format:%s".replace("%s", fmt), range_ref], cwd)
    if cp.returncode != 0:
        return []
    return [line for line in cp.stdout.splitlines() if line.strip()]


def parse_commit_type(subject: str) -> str:
    # Extract conventional commit type before ':'; fallback to 'other'
    head = (subject or "").split(":", 1)[0]
    head = head.split("(", 1)[0]
    head = head.strip().lower()
    return head if head else "other"


def determine_version_bump(commits: Iterable[str]) -> str:
    # Input lines are either "sha|subject" or raw subject
    has_breaking = False
    has_feat = False
    for line in commits or []:
        subject = line.split("|", 1)[-1] if "|" in line else line
        if "BREAKING CHANGE" in subject or subject.split(":", 1)[0].endswith("!"):
            has_breaking = True
            break
        ctype = parse_commit_type(subject)
        if ctype == "feat":
            has_feat = True
    if has_breaking:
        return "major"
    if has_feat:
        return "minor"
    return "patch"


def get_contributors(since_tag: str | None, cwd: str = ".") -> str:
    if not is_git_repository(cwd):
        return ""
    range_ref = f"{since_tag}..HEAD" if since_tag else "HEAD"
    cp = _run_git(["shortlog", "-sne", range_ref], cwd)
    if cp.returncode != 0:
        return ""
    names: list[str] = []
    for line in cp.stdout.splitlines():
        # format: "  10  Name <email>"
        parts = line.strip().split("\t", 1)
        text = parts[-1] if parts else line.strip()
        name = text.split(" <", 1)[0]
        if name:
            names.append(f"@{name}")
    return ", ".join(names)
