"""Data collector for AI release notes generation.

This module provides functions to intelligently gather commit history and
code diffs from a git repository for AI-powered release notes generation.

Key features:
- Extract commits between two git references (tags, commits, branches)
- Smart diff selection based on commit importance
- Token limit awareness to prevent API quota issues
- Support for conventional commits parsing
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Any


def collect_commits_and_diffs(
    *,
    repo_path: str | Path,
    from_ref: str,
    to_ref: str = "HEAD",
    include_diffs: bool = True,
    max_commits: int = 200,
    max_diff_size: int = 5000,
    always_diff_types: list[str] | None = None,
) -> dict[str, Any]:
    """Collect commits and smartly selected diffs from a git repository.

    This is the main entry point for gathering data for AI release notes.
    It extracts commit history and selectively includes diffs for important
    commits to provide context without overwhelming the AI with data.

    Args:
        repo_path: Path to the git repository
        from_ref: Starting git reference (tag, commit, branch)
        to_ref: Ending git reference (default: HEAD)
        include_diffs: Whether to include code diffs for important commits
        max_commits: Maximum number of commits to include
        max_diff_size: Maximum characters per diff to avoid token limits
        always_diff_types: List of commit types that always include diffs
                          Examples: ["feat", "fix", "breaking", "security", "perf"]

    Returns:
        Dictionary with structure:
        {
            "commits": [
                {
                    "hash": str,
                    "message": str,
                    "author": str,
                    "date": str
                },
                ...
            ],
            "diffs": {
                "commit_hash": "diff_text",
                ...
            }
        }

    Example:
        >>> data = collect_commits_and_diffs(
        ...     repo_path="/path/to/repo",
        ...     from_ref="v1.0.0",
        ...     to_ref="HEAD",
        ...     include_diffs=True,
        ...     max_commits=100,
        ...     always_diff_types=["feat", "breaking"]
        ... )
        >>> print(f"Found {len(data['commits'])} commits")
        >>> print(f"Including diffs for {len(data['diffs'])} important commits")
    """
    repo_path = Path(repo_path)

    # Get commit log
    commits = get_commit_log(
        repo_path=repo_path,
        from_ref=from_ref,
        to_ref=to_ref,
        max_commits=max_commits,
    )

    # Smart diff selection
    diffs = {}
    if include_diffs and commits:
        important_commits = identify_important_commits(
            commits, always_diff_types=always_diff_types
        )

        for commit in important_commits:
            try:
                diff = get_commit_diff(
                    repo_path=repo_path,
                    commit_hash=commit["hash"],
                    max_size=max_diff_size,
                )
                if diff:
                    diffs[commit["hash"]] = diff
            except Exception:
                # If diff extraction fails, skip this commit
                continue

    return {
        "commits": commits,
        "diffs": diffs,
    }


def get_commit_log(
    *,
    repo_path: Path,
    from_ref: str,
    to_ref: str,
    max_commits: int,
) -> list[dict[str, str]]:
    """Extract commit history between two git references.

    Uses git log with custom format to extract structured commit data.

    Args:
        repo_path: Path to git repository
        from_ref: Starting reference
        to_ref: Ending reference
        max_commits: Maximum commits to retrieve

    Returns:
        List of commit dictionaries with hash, message, author, date

    Raises:
        subprocess.CalledProcessError: If git command fails
    """
    # Git log format: hash|author|date|message
    # Using %x00 (null char) as delimiter to handle messages with special chars
    git_format = "%H%x00%an <%ae>%x00%ai%x00%s"

    try:
        result = subprocess.run(
            [
                "git",
                "-C",
                str(repo_path),
                "log",
                f"{from_ref}..{to_ref}",
                f"--max-count={max_commits}",
                f"--format={git_format}",
                "--no-merges",  # Skip merge commits
            ],
            capture_output=True,
            text=True,
            check=True,
        )
    except subprocess.CalledProcessError as e:
        raise ValueError(f"Failed to get git log: {e.stderr}") from e

    commits = []
    for line in result.stdout.strip().split("\n"):
        if not line:
            continue

        parts = line.split("\x00")
        if len(parts) != 4:
            continue

        commit_hash, author, date, message = parts
        commits.append(
            {
                "hash": commit_hash,
                "author": author,
                "date": date.split()[0],  # Extract date only (YYYY-MM-DD)
                "message": message,
            }
        )

    return commits


def get_commit_diff(
    *,
    repo_path: Path,
    commit_hash: str,
    max_size: int,
) -> str:
    """Get the diff for a specific commit.

    Args:
        repo_path: Path to git repository
        commit_hash: Commit hash to get diff for
        max_size: Maximum diff size in characters (truncate if larger)

    Returns:
        Diff text (potentially truncated)

    Raises:
        subprocess.CalledProcessError: If git command fails
    """
    try:
        result = subprocess.run(
            [
                "git",
                "-C",
                str(repo_path),
                "show",
                commit_hash,
                "--format=",  # Don't show commit message
                "--unified=3",  # 3 lines of context
            ],
            capture_output=True,
            text=True,
            check=True,
        )
    except subprocess.CalledProcessError as e:
        raise ValueError(f"Failed to get diff for {commit_hash}: {e.stderr}") from e

    diff = result.stdout.strip()

    # Truncate if too large
    if len(diff) > max_size:
        diff = (
            diff[:max_size]
            + f"\n\n... (diff truncated, original size: {len(diff)} chars)"
        )

    return diff


def identify_important_commits(
    commits: list[dict[str, str]],
    always_diff_types: list[str] | None = None,
) -> list[dict[str, str]]:
    """Identify commits that need diff context for better understanding.

    Uses heuristics to determine which commits would benefit from
    having their code diffs included in the AI prompt.

    Selection criteria (in priority order):
    0. Configured types (if always_diff_types is set)
    1. Breaking changes (! suffix or BREAKING CHANGE in message)
    2. Security-related commits
    3. Commits without conventional commit prefixes (unclear intent)
    4. Major features with vague descriptions

    Args:
        commits: List of commit dictionaries
        always_diff_types: List of commit types that always include diffs
                          Examples: ["feat", "fix", "breaking", "security", "perf"]

    Returns:
        Filtered list of important commits that should include diffs

    Example:
        >>> commits = [
        ...     {"hash": "abc", "message": "fix!: critical bug"},
        ...     {"hash": "def", "message": "feat: add feature"},
        ...     {"hash": "ghi", "message": "update stuff"},  # Unclear
        ... ]
        >>> important = identify_important_commits(commits, always_diff_types=["feat", "breaking"])
        >>> len(important)  # Should include abc and def
        2
    """
    important = []

    # Conventional commit prefixes
    conventional_prefixes = [
        "feat",
        "fix",
        "docs",
        "style",
        "refactor",
        "perf",
        "test",
        "build",
        "ci",
        "chore",
        "revert",
    ]

    # Keywords that indicate importance
    security_keywords = [
        "security",
        "vulnerability",
        "cve",
        "exploit",
        "xss",
        "injection",
    ]

    # Normalize always_diff_types
    if always_diff_types is None:
        always_diff_types = []
    always_diff_types_lower = [t.lower() for t in always_diff_types]

    for commit in commits:
        msg = commit["message"]
        msg_lower = msg.lower()

        # Priority 0: User-configured types (highest priority)
        if always_diff_types_lower:
            # Check for "breaking" special type
            if "breaking" in always_diff_types_lower:
                if "!" in msg.split(":")[0] or "BREAKING CHANGE" in msg:
                    important.append(commit)
                    continue

            # Check for "security" special type
            if "security" in always_diff_types_lower:
                if any(keyword in msg_lower for keyword in security_keywords):
                    important.append(commit)
                    continue

            # Check for conventional commit types (feat, fix, perf, etc.)
            for diff_type in always_diff_types_lower:
                if diff_type in ["breaking", "security"]:
                    continue  # Already handled above

                # Check if commit starts with this type
                if msg.startswith(f"{diff_type}:") or msg.startswith(f"{diff_type}("):
                    important.append(commit)
                    break  # Found a match, move to next commit
            else:
                # No match found in always_diff_types, continue to heuristics
                pass

            # If we added this commit, skip heuristics
            if commit in important:
                continue

        # Priority 1: Breaking changes (always include)
        if "!" in msg.split(":")[0] or "BREAKING CHANGE" in msg:
            important.append(commit)
            continue

        # Priority 2: Security-related (always include)
        if any(keyword in msg_lower for keyword in security_keywords):
            important.append(commit)
            continue

        # Priority 3: No conventional commit prefix (unclear intent)
        has_prefix = any(
            msg.startswith(f"{prefix}:") or msg.startswith(f"{prefix}(")
            for prefix in conventional_prefixes
        )

        if not has_prefix:
            # But skip very generic merge/revert messages
            if not (msg.startswith("Merge") or msg.startswith("Revert")):
                important.append(commit)
                continue

        # Priority 4: Very short/vague conventional commits
        # e.g., "feat: update" or "fix: changes"
        if has_prefix:
            # Extract the actual message part after the prefix
            parts = msg.split(":", 1)
            if len(parts) == 2:
                actual_msg = parts[1].strip()
                vague_words = [
                    "update",
                    "change",
                    "modify",
                    "fix",
                    "improve",
                    "refactor",
                ]

                # If message is just 1-2 generic words, include diff for clarity
                words = actual_msg.split()
                if len(words) <= 2 and any(
                    vague in actual_msg.lower() for vague in vague_words
                ):
                    important.append(commit)
                    continue

    return important


def is_conventional_commit(message: str) -> bool:
    """Check if a commit message follows conventional commits format.

    Args:
        message: Commit message

    Returns:
        True if message follows conventional commits format

    Example:
        >>> is_conventional_commit("feat: add new feature")
        True
        >>> is_conventional_commit("fix(auth): resolve login bug")
        True
        >>> is_conventional_commit("update readme")
        False
    """
    pattern = r"^(feat|fix|docs|style|refactor|perf|test|build|ci|chore|revert)(\(.+\))?!?:\s.+"
    return bool(re.match(pattern, message))


def parse_conventional_commit(message: str) -> dict[str, str | None]:
    """Parse a conventional commit message into components.

    Args:
        message: Commit message to parse

    Returns:
        Dictionary with keys: type, scope, breaking, description

    Example:
        >>> parse_conventional_commit("feat(auth)!: add OAuth support")
        {
            'type': 'feat',
            'scope': 'auth',
            'breaking': True,
            'description': 'add OAuth support'
        }
    """
    pattern = (
        r"^(?P<type>\w+)(\((?P<scope>.+)\))?(?P<breaking>!)?:\s*(?P<description>.+)"
    )
    match = re.match(pattern, message)

    if not match:
        return {
            "type": None,
            "scope": None,
            "breaking": False,
            "description": message,
        }

    return {
        "type": match.group("type"),
        "scope": match.group("scope"),
        "breaking": match.group("breaking") == "!",
        "description": match.group("description"),
    }


def estimate_token_count(text: str) -> int:
    """Rough estimation of token count for a text.

    Uses a simple heuristic: ~4 characters per token (OpenAI's average).
    This is an approximation; actual tokenization may vary.

    Args:
        text: Text to estimate tokens for

    Returns:
        Estimated token count

    Example:
        >>> estimate_token_count("Hello, world!")
        4
    """
    return len(text) // 4


def truncate_diffs_to_budget(
    diffs: dict[str, str],
    token_budget: int = 4000,
) -> dict[str, str]:
    """Truncate diffs to fit within a token budget.

    Useful when you have many important commits but need to stay
    within API token limits.

    Args:
        diffs: Dictionary of commit_hash -> diff_text
        token_budget: Maximum tokens to use for all diffs

    Returns:
        Truncated diffs dictionary (may have fewer entries)

    Example:
        >>> diffs = {"abc": "x" * 10000, "def": "y" * 5000}
        >>> truncated = truncate_diffs_to_budget(diffs, token_budget=1000)
        >>> estimate_token_count(truncated["abc"]) < 1000
        True
    """
    if not diffs:
        return {}

    total_tokens = sum(estimate_token_count(diff) for diff in diffs.values())

    if total_tokens <= token_budget:
        return diffs

    # Need to truncate - distribute budget proportionally
    truncated = {}
    items = list(diffs.items())

    # Calculate proportion for each diff
    per_diff_budget = token_budget // len(items)

    for commit_hash, diff_text in items:
        max_chars = per_diff_budget * 4  # Convert tokens back to chars

        if len(diff_text) > max_chars:
            truncated[commit_hash] = (
                diff_text[:max_chars] + "\n\n... (diff truncated to fit token budget)"
            )
        else:
            truncated[commit_hash] = diff_text

    return truncated
