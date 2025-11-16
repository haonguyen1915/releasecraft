"""Integration tests for data collector using real git repository.

These tests use the actual releasecraft git repository to verify
the data collector works with real git data.
"""

import subprocess
from pathlib import Path

import pytest

from releaser.ai.data_collector import collect_commits_and_diffs


@pytest.fixture
def repo_root():
    """Get the repository root path."""
    return Path(__file__).parent.parent.parent


def get_latest_tag(repo_path: Path) -> str:
    """Get the latest git tag."""
    try:
        result = subprocess.run(
            ["git", "-C", str(repo_path), "describe", "--tags", "--abbrev=0"],
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.strip()
    except subprocess.CalledProcessError:
        # No tags exist, use first commit
        result = subprocess.run(
            ["git", "-C", str(repo_path), "rev-list", "--max-parents=0", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.strip()


def test_collect_from_real_repo(repo_root):
    """Test collecting commits from the actual repository."""
    # Get the latest tag
    try:
        latest_tag = get_latest_tag(repo_root)
    except Exception as e:
        pytest.skip(f"Could not get git tag: {e}")

    print(f"\nCollecting commits from {latest_tag} to HEAD")

    # Collect data
    data = collect_commits_and_diffs(
        repo_path=repo_root,
        from_ref=latest_tag,
        to_ref="HEAD",
        include_diffs=False,  # Don't include diffs for speed
        max_commits=50,
    )

    # Basic assertions
    assert "commits" in data
    assert "diffs" in data
    assert isinstance(data["commits"], list)
    assert isinstance(data["diffs"], dict)

    print(f"Found {len(data['commits'])} commits")

    if data["commits"]:
        print("\nSample commits:")
        for commit in data["commits"][:5]:
            print(f"  {commit['hash'][:8]} - {commit['message']}")


def test_collect_with_diffs_from_real_repo(repo_root):
    """Test collecting commits with diffs from actual repository."""
    try:
        latest_tag = get_latest_tag(repo_root)
    except Exception as e:
        pytest.skip(f"Could not get git tag: {e}")

    print(f"\nCollecting commits with smart diff selection from {latest_tag} to HEAD")

    # Collect data with diffs
    data = collect_commits_and_diffs(
        repo_path=repo_root,
        from_ref=latest_tag,
        to_ref="HEAD",
        include_diffs=True,
        max_commits=20,
        max_diff_size=2000,  # Limit diff size
    )

    assert "commits" in data
    assert "diffs" in data

    print(f"Found {len(data['commits'])} commits")
    print(f"Including diffs for {len(data['diffs'])} important commits")

    if data["diffs"]:
        print("\nCommits with diffs (important):")
        for commit_hash in data["diffs"].keys():
            # Find the commit message
            commit = next(
                (c for c in data["commits"] if c["hash"] == commit_hash), None
            )
            if commit:
                print(f"  {commit_hash[:8]} - {commit['message']}")
                print(f"    Diff size: {len(data['diffs'][commit_hash])} chars")


def test_collect_last_5_commits(repo_root):
    """Test collecting just the last 5 commits."""
    # Use HEAD~5 as from_ref to get last 5 commits
    try:
        # Check if we have at least 5 commits
        result = subprocess.run(
            ["git", "-C", str(repo_root), "rev-list", "--count", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
        )
        commit_count = int(result.stdout.strip())

        if commit_count < 5:
            pytest.skip("Repository has fewer than 5 commits")

        from_ref = "HEAD~5"
    except Exception as e:
        pytest.skip(f"Could not determine commit history: {e}")

    print("\nCollecting last 5 commits")

    data = collect_commits_and_diffs(
        repo_path=repo_root,
        from_ref=from_ref,
        to_ref="HEAD",
        include_diffs=True,
        max_commits=10,
    )

    assert len(data["commits"]) <= 5

    print(f"\nCommits ({len(data['commits'])}):")
    for commit in data["commits"]:
        print(f"  {commit['hash'][:8]} - {commit['message']}")
        print(f"    Author: {commit['author']}")
        print(f"    Date: {commit['date']}")

        if commit["hash"] in data["diffs"]:
            print(f"    ✓ Has diff ({len(data['diffs'][commit['hash']])} chars)")


def test_collect_with_token_budget(repo_root):
    """Test collecting with token budget constraint."""
    try:
        latest_tag = get_latest_tag(repo_root)
    except Exception as e:
        pytest.skip(f"Could not get git tag: {e}")

    # Collect with very small diff size to simulate token budget
    data = collect_commits_and_diffs(
        repo_path=repo_root,
        from_ref=latest_tag,
        to_ref="HEAD",
        include_diffs=True,
        max_commits=10,
        max_diff_size=500,  # Very small to test truncation
    )

    print("\nCollecting with max_diff_size=500")
    print(f"Found {len(data['commits'])} commits")
    print(f"Including diffs for {len(data['diffs'])} important commits")

    # Verify all diffs are within size limit
    for commit_hash, diff in data["diffs"].items():
        assert (
            len(diff) <= 700
        ), f"Diff for {commit_hash} exceeds size limit (with truncation message)"
        print(f"  {commit_hash[:8]}: {len(diff)} chars")


def test_conventional_commits_in_real_repo(repo_root):
    """Test that conventional commits are properly identified."""
    try:
        latest_tag = get_latest_tag(repo_root)
    except Exception as e:
        pytest.skip(f"Could not get git tag: {e}")

    data = collect_commits_and_diffs(
        repo_path=repo_root,
        from_ref=latest_tag,
        to_ref="HEAD",
        include_diffs=False,
        max_commits=20,
    )

    if not data["commits"]:
        pytest.skip("No commits found")

    conventional_commits = [
        c
        for c in data["commits"]
        if any(
            c["message"].startswith(f"{prefix}:")
            or c["message"].startswith(f"{prefix}(")
            for prefix in [
                "feat",
                "fix",
                "docs",
                "chore",
                "refactor",
                "test",
                "build",
                "ci",
            ]
        )
    ]

    print(f"\nConventional commits: {len(conventional_commits)}/{len(data['commits'])}")

    if conventional_commits:
        print("\nExamples:")
        for commit in conventional_commits[:5]:
            print(f"  {commit['message']}")
