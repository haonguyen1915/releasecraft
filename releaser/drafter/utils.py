"""
Utility functions for git operations, version parsing, and commit analysis.
"""

import re
import subprocess
from collections import Counter
from typing import Dict, List, Tuple


def run_command(
    command: List[str], capture_output: bool = True
) -> subprocess.CompletedProcess:
    """Run a shell command and return the result."""
    try:
        return subprocess.run(
            command, capture_output=capture_output, text=True, check=True
        )
    except subprocess.CalledProcessError as e:
        if not capture_output:
            raise
        return e


def get_current_branch() -> str:
    """Get current git branch name."""
    try:
        result = run_command(["git", "branch", "--show-current"])
        return result.stdout.strip() if result.returncode == 0 else ""
    except subprocess.CalledProcessError:
        return ""


def get_remote_type() -> str:
    """Detect if we're using GitHub or GitLab."""
    try:
        result = run_command(["git", "remote", "get-url", "origin"])
        remote_url = result.stdout.strip()

        if "github.com" in remote_url:
            return "github"
        elif "gitlab" in remote_url:
            return "gitlab"
        else:
            return "unknown"
    except subprocess.CalledProcessError:
        return "unknown"


def get_remote_url() -> str:
    """Get the remote origin URL."""
    try:
        result = run_command(["git", "remote", "get-url", "origin"])
        return result.stdout.strip()
    except subprocess.CalledProcessError:
        return ""


def get_latest_tag() -> str:
    """Get the latest git tag, preferring remote tags."""
    try:
        # First fetch remote tags to ensure we have the latest
        run_command(["git", "fetch", "--tags"])

        # Get all tags sorted by version (newest first)
        result = run_command(["git", "tag", "-l", "--sort=-version:refname"])
        if result.returncode == 0 and result.stdout.strip():
            all_tags = result.stdout.strip().split("\n")
            latest_tag = all_tags[0] if all_tags else ""
            if latest_tag:
                return latest_tag
    except subprocess.CalledProcessError:
        pass

    # Fallback to local tags if remote fetch fails
    try:
        result = run_command(["git", "describe", "--tags", "--abbrev=0"])
        return result.stdout.strip() if result.returncode == 0 else ""
    except subprocess.CalledProcessError:
        return ""


def get_pyproject_version(pyproject_file: str) -> str:
    """Get version from pyproject.toml."""
    try:
        with open(pyproject_file, "r") as f:
            content = f.read()

        # Match version field with single or double quotes
        match = re.search(r'^version\s*=\s*["\']([^"\']*)["\']', content, re.MULTILINE)
        return match.group(1) if match else ""
    except Exception:
        return ""


def get_commits_since_tag(tag: str) -> List[str]:
    """Get commits since the last tag."""
    cmd = ["git", "log", "--format=%h|%s|%an", "--no-merges"]
    if tag:
        cmd.insert(2, f"{tag}..HEAD")

    try:
        result = run_command(cmd)
        return result.stdout.strip().split("\n") if result.stdout.strip() else []
    except subprocess.CalledProcessError:
        return []


def get_contributors(tag: str) -> str:
    """Get all contributors since last tag."""
    cmd = ["git", "log", "--format=%an", "--no-merges"]
    if tag:
        cmd.insert(2, f"{tag}..HEAD")

    try:
        result = run_command(cmd)
        if result.stdout.strip():
            contributors = list(set(result.stdout.strip().split("\n")))
            return ", ".join([f"@{name}" for name in sorted(contributors)])
        return ""
    except subprocess.CalledProcessError:
        return ""


def get_repo_url() -> str:
    """Get repository URL for comparison links."""
    try:
        result = run_command(["git", "remote", "get-url", "origin"])
        remote_url = result.stdout.strip()

        # Convert SSH to HTTPS
        if remote_url.startswith("git@"):
            match = re.match(r"git@([^:]+):(.+)\.git$", remote_url)
            if match:
                return f"https://{match.group(1)}/{match.group(2)}"
        elif remote_url.startswith("https://"):
            return (
                remote_url.replace(".git", "")
                if remote_url.endswith(".git")
                else remote_url
            )

        return remote_url
    except subprocess.CalledProcessError:
        return ""


def parse_commit_type(commit_or_message: str) -> str:
    """Parse commit type from conventional commit format.
    
    Args:
        commit_or_message: Either a full commit line (sha + message) or just the message
    """
    # Remove SHA prefix if present (for backwards compatibility)
    message = re.sub(r"^[a-f0-9]+ ", "", commit_or_message).strip()

    # Check for conventional commit format
    conv_match = re.match(r"^([a-z]+)(\([^\)]+\))?: ", message)
    if conv_match:
        return conv_match.group(1)

    # Check for keywords
    if re.search(r"[Ff]eat|[Aa]dd", message):
        return "feat"
    elif re.search(r"[Ff]ix|[Bb]ug", message):
        return "fix"
    elif re.search(r"[Dd]oc", message):
        return "docs"
    elif re.search(r"[Bb]reak|BREAKING", message):
        return "breaking"
    elif re.search(r"[Ii]mprove|[Oo]ptimize|[Ee]nhance", message):
        return "improve"
    else:
        return "chore"


def extract_pr_number(message: str) -> str:
    """Extract PR number from commit message."""
    match = re.search(r"\(#(\d+)\)", message)
    return f"(#{match.group(1)})" if match else ""


def check_duplicate_commits(tag: str = "") -> Dict[str, List[Tuple[str, str]]]:
    """Check for duplicate commit messages and return them grouped."""
    cmd = ["git", "log", "--format=%H|%s", "--no-merges"]
    if tag:
        cmd.insert(2, f"{tag}..HEAD")

    try:
        result = run_command(cmd)
        if not result.stdout.strip():
            return {}

        # Parse commits: SHA|message
        commits = []
        for line in result.stdout.strip().split("\n"):
            if "|" in line:
                sha, message = line.split("|", 1)
                commits.append((sha.strip(), message.strip()))

        # Count message occurrences
        message_counts = Counter(message for _, message in commits)

        # Find duplicates
        duplicates = {}
        for message, count in message_counts.items():
            if count > 1:
                # Get all commits with this message
                duplicate_commits = [
                    (sha, msg) for sha, msg in commits if msg == message
                ]
                duplicates[message] = duplicate_commits

        return duplicates

    except subprocess.CalledProcessError:
        return {}


def is_git_repository() -> bool:
    """Check if we're in a git repository."""
    try:
        run_command(["git", "rev-parse", "--git-dir"])
        return True
    except subprocess.CalledProcessError:
        return False


def has_uncommitted_changes() -> bool:
    """Check for uncommitted changes."""
    try:
        result = run_command(["git", "diff-index", "--quiet", "HEAD", "--"])
        return result.returncode != 0
    except subprocess.CalledProcessError:
        return True


def bump_version(current_version: str, bump_type: str, tag_prefix: str = "v") -> str:
    """Bump version based on type."""
    if not current_version:
        return f"{tag_prefix}0.0.1"

    # Remove tag prefix
    version = (
        current_version[len(tag_prefix) :]
        if current_version.startswith(tag_prefix)
        else current_version
    )

    # Skip version format validation - accept any format
    try:
        parts = version.split(".")
        if len(parts) >= 3:
            major, minor, patch = int(parts[0]), int(parts[1]), int(parts[2])

            if bump_type == "major":
                return f"{major + 1}.0.0"
            elif bump_type == "minor":
                return f"{major}.{minor + 1}.0"
            elif bump_type == "patch":
                return f"{major}.{minor}.{patch + 1}"
    except (ValueError, IndexError):
        pass

    return version


def determine_version_bump(commits: List[str]) -> str:
    """Determine version bump type."""
    has_breaking = False
    has_feature = False

    for commit in commits:
        if not commit.strip():
            continue

        commit_type = parse_commit_type(commit)

        if commit_type in ["breaking", "BREAKING"]:
            has_breaking = True
        elif commit_type in ["feat", "feature"]:
            has_feature = True

    if has_breaking:
        return "major"
    elif has_feature:
        return "minor"
    else:
        return "patch"
