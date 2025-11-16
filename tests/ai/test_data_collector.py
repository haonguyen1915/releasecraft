"""Tests for AI data collector module."""

import subprocess
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from releaser.ai.data_collector import (
    collect_commits_and_diffs,
    estimate_token_count,
    get_commit_diff,
    get_commit_log,
    identify_important_commits,
    is_conventional_commit,
    parse_conventional_commit,
    truncate_diffs_to_budget,
)


@pytest.fixture
def sample_commits():
    """Sample commit data for testing."""
    return [
        {
            "hash": "abc123def456",
            "message": "feat: add new feature",
            "author": "Jane Doe <jane@example.com>",
            "date": "2024-01-15"
        },
        {
            "hash": "def456abc123",
            "message": "fix!: resolve critical security issue",
            "author": "John Smith <john@example.com>",
            "date": "2024-01-14"
        },
        {
            "hash": "789abc456def",
            "message": "update dependencies",  # No conventional prefix
            "author": "Alice Johnson <alice@example.com>",
            "date": "2024-01-13"
        },
        {
            "hash": "456def789abc",
            "message": "docs: update README",
            "author": "Bob Wilson <bob@example.com>",
            "date": "2024-01-12"
        },
        {
            "hash": "012abc345def",
            "message": "fix: resolve security vulnerability in auth",
            "author": "Charlie Brown <charlie@example.com>",
            "date": "2024-01-11"
        },
    ]


# Test conventional commit parsing


def test_is_conventional_commit():
    """Test conventional commit detection."""
    assert is_conventional_commit("feat: add feature")
    assert is_conventional_commit("fix: resolve bug")
    assert is_conventional_commit("feat(auth): add OAuth")
    assert is_conventional_commit("fix(api)!: breaking change")
    assert is_conventional_commit("docs: update readme")

    assert not is_conventional_commit("update readme")
    assert not is_conventional_commit("Merge branch 'main'")
    assert not is_conventional_commit("random commit message")


def test_parse_conventional_commit():
    """Test parsing of conventional commit messages."""
    # Simple feature
    result = parse_conventional_commit("feat: add new feature")
    assert result["type"] == "feat"
    assert result["scope"] is None
    assert result["breaking"] is False
    assert result["description"] == "add new feature"

    # With scope
    result = parse_conventional_commit("fix(auth): resolve login issue")
    assert result["type"] == "fix"
    assert result["scope"] == "auth"
    assert result["breaking"] is False
    assert result["description"] == "resolve login issue"

    # Breaking change
    result = parse_conventional_commit("feat(api)!: change response format")
    assert result["type"] == "feat"
    assert result["scope"] == "api"
    assert result["breaking"] is True
    assert result["description"] == "change response format"

    # Non-conventional
    result = parse_conventional_commit("update readme")
    assert result["type"] is None
    assert result["scope"] is None
    assert result["breaking"] is False
    assert result["description"] == "update readme"


# Test important commit identification


def test_identify_important_commits_breaking_changes(sample_commits):
    """Test that breaking changes are always identified as important."""
    important = identify_important_commits(sample_commits)

    # Should include the fix! commit
    breaking_hashes = [c["hash"] for c in important if "!" in c["message"].split(":")[0]]
    assert "def456abc123" in breaking_hashes


def test_identify_important_commits_security(sample_commits):
    """Test that security-related commits are identified as important."""
    important = identify_important_commits(sample_commits)

    # Should include commits with security keywords
    security_hashes = [
        c["hash"] for c in important
        if "security" in c["message"].lower() or "vulnerability" in c["message"].lower()
    ]
    assert "def456abc123" in security_hashes  # fix! with security
    assert "012abc345def" in security_hashes  # fix with vulnerability


def test_identify_important_commits_no_prefix(sample_commits):
    """Test that commits without conventional prefix are identified."""
    important = identify_important_commits(sample_commits)

    # Should include "update dependencies" (no conventional prefix)
    no_prefix_hashes = [c["hash"] for c in important]
    assert "789abc456def" in no_prefix_hashes


def test_identify_important_commits_filters_clear_messages():
    """Test that clear conventional commits are NOT marked as important."""
    commits = [
        {
            "hash": "abc123",
            "message": "feat: add comprehensive OAuth2 authentication system",
            "author": "Dev",
            "date": "2024-01-01"
        },
        {
            "hash": "def456",
            "message": "docs: add API documentation with examples",
            "author": "Dev",
            "date": "2024-01-01"
        },
    ]

    important = identify_important_commits(commits)

    # These clear messages shouldn't need diffs
    assert len(important) == 0


def test_identify_important_commits_vague_messages():
    """Test that vague conventional commits are identified."""
    commits = [
        {
            "hash": "abc123",
            "message": "feat: update",  # Vague
            "author": "Dev",
            "date": "2024-01-01"
        },
        {
            "hash": "def456",
            "message": "fix: changes",  # Vague
            "author": "Dev",
            "date": "2024-01-01"
        },
    ]

    important = identify_important_commits(commits)

    # Should identify both vague commits
    assert len(important) == 2


# Test token estimation


def test_estimate_token_count():
    """Test token count estimation."""
    # Roughly 4 chars per token
    assert estimate_token_count("") == 0
    assert estimate_token_count("Hello, world!") == 3  # 13 chars / 4 = 3
    assert estimate_token_count("a" * 100) == 25  # 100 / 4 = 25
    assert estimate_token_count("test " * 100) == 125  # 500 / 4 = 125


def test_truncate_diffs_to_budget():
    """Test diff truncation to fit token budget."""
    diffs = {
        "abc123": "x" * 8000,  # ~2000 tokens
        "def456": "y" * 12000,  # ~3000 tokens
    }

    # Total: ~5000 tokens, budget: 1000 tokens
    truncated = truncate_diffs_to_budget(diffs, token_budget=1000)

    # Should have both commits
    assert len(truncated) == 2

    # Each should be truncated to roughly 500 tokens (2000 chars)
    for diff in truncated.values():
        assert len(diff) < 3000  # Well under original size
        assert "truncated" in diff


def test_truncate_diffs_no_truncation_needed():
    """Test that diffs within budget are not truncated."""
    diffs = {
        "abc123": "small diff",
        "def456": "another small diff",
    }

    truncated = truncate_diffs_to_budget(diffs, token_budget=1000)

    # Should be unchanged
    assert truncated == diffs


# Test git operations (mocked)


def test_get_commit_log_success(tmp_path, monkeypatch):
    """Test successful commit log extraction."""
    git_output = (
        "abc123def456\x00Jane Doe <jane@example.com>\x00"
        "2024-01-15 10:30:45 -0800\x00feat: add feature\n"
        "def456abc123\x00John Smith <john@example.com>\x00"
        "2024-01-14 09:20:30 -0800\x00fix: resolve bug\n"
    )

    def mock_run(*args, **kwargs):
        result = Mock()
        result.stdout = git_output
        result.returncode = 0
        return result

    monkeypatch.setattr(subprocess, "run", mock_run)

    commits = get_commit_log(
        repo_path=tmp_path,
        from_ref="v1.0.0",
        to_ref="HEAD",
        max_commits=100,
    )

    assert len(commits) == 2
    assert commits[0]["hash"] == "abc123def456"
    assert commits[0]["message"] == "feat: add feature"
    assert commits[0]["author"] == "Jane Doe <jane@example.com>"
    assert commits[0]["date"] == "2024-01-15"

    assert commits[1]["hash"] == "def456abc123"
    assert commits[1]["message"] == "fix: resolve bug"


def test_get_commit_log_git_error(tmp_path, monkeypatch):
    """Test handling of git command errors."""
    def mock_run(*args, **kwargs):
        raise subprocess.CalledProcessError(
            returncode=128,
            cmd=["git", "log"],
            stderr="fatal: bad revision"
        )

    monkeypatch.setattr(subprocess, "run", mock_run)

    with pytest.raises(ValueError, match="Failed to get git log"):
        get_commit_log(
            repo_path=tmp_path,
            from_ref="nonexistent",
            to_ref="HEAD",
            max_commits=100,
        )


def test_get_commit_diff_success(tmp_path, monkeypatch):
    """Test successful diff extraction."""
    diff_output = """diff --git a/file.py b/file.py
index 1234567..abcdefg 100644
--- a/file.py
+++ b/file.py
@@ -1,3 +1,4 @@
+# New line
 def hello():
     print("Hello")
"""

    def mock_run(*args, **kwargs):
        result = Mock()
        result.stdout = diff_output
        result.returncode = 0
        return result

    monkeypatch.setattr(subprocess, "run", mock_run)

    diff = get_commit_diff(
        repo_path=tmp_path,
        commit_hash="abc123",
        max_size=10000,
    )

    assert "diff --git" in diff
    assert "+# New line" in diff


def test_get_commit_diff_truncation(tmp_path, monkeypatch):
    """Test that large diffs are truncated."""
    large_diff = "x" * 10000

    def mock_run(*args, **kwargs):
        result = Mock()
        result.stdout = large_diff
        result.returncode = 0
        return result

    monkeypatch.setattr(subprocess, "run", mock_run)

    diff = get_commit_diff(
        repo_path=tmp_path,
        commit_hash="abc123",
        max_size=1000,
    )

    assert len(diff) < 1200  # Should be truncated
    assert "truncated" in diff


def test_get_commit_diff_git_error(tmp_path, monkeypatch):
    """Test handling of git show errors."""
    def mock_run(*args, **kwargs):
        raise subprocess.CalledProcessError(
            returncode=128,
            cmd=["git", "show"],
            stderr="fatal: bad object"
        )

    monkeypatch.setattr(subprocess, "run", mock_run)

    with pytest.raises(ValueError, match="Failed to get diff"):
        get_commit_diff(
            repo_path=tmp_path,
            commit_hash="invalid",
            max_size=10000,
        )


# Test main collection function


def test_collect_commits_and_diffs_without_diffs(tmp_path, monkeypatch):
    """Test collection without including diffs."""
    git_output = (
        "abc123\x00Jane <jane@example.com>\x00"
        "2024-01-15 10:30:45\x00feat: add feature\n"
    )

    def mock_run(*args, **kwargs):
        result = Mock()
        result.stdout = git_output
        result.returncode = 0
        return result

    monkeypatch.setattr(subprocess, "run", mock_run)

    data = collect_commits_and_diffs(
        repo_path=tmp_path,
        from_ref="v1.0.0",
        to_ref="HEAD",
        include_diffs=False,
        max_commits=100,
    )

    assert len(data["commits"]) == 1
    assert len(data["diffs"]) == 0  # No diffs requested


def test_collect_commits_and_diffs_with_diffs(tmp_path, monkeypatch):
    """Test collection with smart diff selection."""
    # Mock git log
    git_log_output = (
        "abc123\x00Jane <jane@example.com>\x00"
        "2024-01-15 10:30:45\x00fix!: breaking change\n"
        "def456\x00John <john@example.com>\x00"
        "2024-01-14 09:20:30\x00feat: clear feature description\n"
    )

    git_diff_output = "diff --git a/file.py b/file.py\n+changes"

    call_count = [0]

    def mock_run(*args, **kwargs):
        result = Mock()
        result.returncode = 0

        # First call is git log, subsequent calls are git show (diff)
        if call_count[0] == 0:
            result.stdout = git_log_output
        else:
            result.stdout = git_diff_output

        call_count[0] += 1
        return result

    monkeypatch.setattr(subprocess, "run", mock_run)

    data = collect_commits_and_diffs(
        repo_path=tmp_path,
        from_ref="v1.0.0",
        to_ref="HEAD",
        include_diffs=True,
        max_commits=100,
    )

    assert len(data["commits"]) == 2

    # Only breaking change should have diff (important commit)
    assert "abc123" in data["diffs"]
    assert "def456" not in data["diffs"]  # Clear conventional commit, no diff needed


def test_collect_commits_and_diffs_handles_diff_errors(tmp_path, monkeypatch):
    """Test that diff errors don't crash the collection."""
    git_log_output = (
        "abc123\x00Jane <jane@example.com>\x00"
        "2024-01-15 10:30:45\x00fix!: breaking change\n"
    )

    call_count = [0]

    def mock_run(*args, **kwargs):
        result = Mock()
        result.returncode = 0

        if call_count[0] == 0:
            result.stdout = git_log_output
        else:
            # Git show fails
            raise subprocess.CalledProcessError(
                returncode=128,
                cmd=["git", "show"],
                stderr="error"
            )

        call_count[0] += 1
        return result

    monkeypatch.setattr(subprocess, "run", mock_run)

    # Should not raise, just skip the diff
    data = collect_commits_and_diffs(
        repo_path=tmp_path,
        from_ref="v1.0.0",
        to_ref="HEAD",
        include_diffs=True,
        max_commits=100,
    )

    assert len(data["commits"]) == 1
    assert len(data["diffs"]) == 0  # Diff failed but didn't crash

def test_identify_important_commits_with_always_diff_types_feat():
    """Test always_diff_types configuration for feat commits."""
    commits = [
        {"hash": "abc", "message": "feat: add new feature", "author": "Dev", "date": "2024-01-01"},
        {"hash": "def", "message": "fix: resolve bug in parser", "author": "Dev", "date": "2024-01-02"},
        {"hash": "ghi", "message": "docs: add API documentation", "author": "Dev", "date": "2024-01-03"},
    ]

    # Without config, only unclear commits selected by heuristics
    important_default = identify_important_commits(commits)
    assert len(important_default) == 0  # All are clear conventional commits

    # With always_diff_types=["feat"], should include feat commits
    important_feat = identify_important_commits(commits, always_diff_types=["feat"])
    assert len(important_feat) == 1
    assert important_feat[0]["hash"] == "abc"


def test_identify_important_commits_with_always_diff_types_multiple():
    """Test always_diff_types with multiple types."""
    commits = [
        {"hash": "abc", "message": "feat: add user authentication", "author": "Dev", "date": "2024-01-01"},
        {"hash": "def", "message": "fix: resolve memory leak in cache", "author": "Dev", "date": "2024-01-02"},
        {"hash": "ghi", "message": "perf: optimize database queries", "author": "Dev", "date": "2024-01-03"},
        {"hash": "jkl", "message": "docs: add installation guide", "author": "Dev", "date": "2024-01-04"},
    ]

    important = identify_important_commits(commits, always_diff_types=["feat", "fix", "perf"])
    
    assert len(important) == 3
    hashes = [c["hash"] for c in important]
    assert "abc" in hashes  # feat
    assert "def" in hashes  # fix
    assert "ghi" in hashes  # perf
    assert "jkl" not in hashes  # docs not in always_diff_types


def test_identify_important_commits_with_always_diff_types_breaking():
    """Test always_diff_types with special 'breaking' type."""
    commits = [
        {"hash": "abc", "message": "feat!: breaking change", "author": "Dev", "date": "2024-01-01"},
        {"hash": "def", "message": "fix: BREAKING CHANGE: major update", "author": "Dev", "date": "2024-01-02"},
        {"hash": "ghi", "message": "feat: normal feature", "author": "Dev", "date": "2024-01-03"},
    ]

    important = identify_important_commits(commits, always_diff_types=["breaking"])
    
    assert len(important) == 2
    hashes = [c["hash"] for c in important]
    assert "abc" in hashes  # feat!
    assert "def" in hashes  # BREAKING CHANGE
    assert "ghi" not in hashes  # Normal feat


def test_identify_important_commits_with_always_diff_types_security():
    """Test always_diff_types with special 'security' type."""
    commits = [
        {"hash": "abc", "message": "fix: resolve security vulnerability", "author": "Dev", "date": "2024-01-01"},
        {"hash": "def", "message": "feat: add feature with CVE fix", "author": "Dev", "date": "2024-01-02"},
        {"hash": "ghi", "message": "fix: normal bug fix", "author": "Dev", "date": "2024-01-03"},
    ]

    important = identify_important_commits(commits, always_diff_types=["security"])
    
    assert len(important) == 2
    hashes = [c["hash"] for c in important]
    assert "abc" in hashes  # security keyword
    assert "def" in hashes  # CVE keyword
    assert "ghi" not in hashes  # Normal fix


def test_identify_important_commits_with_scoped_commits():
    """Test always_diff_types with scoped commits like feat(api):."""
    commits = [
        {"hash": "abc", "message": "feat(api): add endpoint", "author": "Dev", "date": "2024-01-01"},
        {"hash": "def", "message": "fix(auth): resolve login issue", "author": "Dev", "date": "2024-01-02"},
        {"hash": "ghi", "message": "docs(readme): add usage examples", "author": "Dev", "date": "2024-01-03"},
    ]

    important = identify_important_commits(commits, always_diff_types=["feat", "fix"])
    
    assert len(important) == 2
    hashes = [c["hash"] for c in important]
    assert "abc" in hashes  # feat(api)
    assert "def" in hashes  # fix(auth)
    assert "ghi" not in hashes  # docs not configured


def test_identify_important_commits_case_insensitive():
    """Test that always_diff_types is case-insensitive."""
    commits = [
        {"hash": "abc", "message": "feat: add feature", "author": "Dev", "date": "2024-01-01"},
        {"hash": "def", "message": "FIX: resolve bug", "author": "Dev", "date": "2024-01-02"},
    ]

    # Test with uppercase config
    important = identify_important_commits(commits, always_diff_types=["FEAT", "FIX"])
    
    assert len(important) == 2  # Should match both despite case mismatch


def test_identify_important_commits_heuristics_still_apply():
    """Test that heuristics still apply even with always_diff_types set."""
    commits = [
        {"hash": "abc", "message": "feat: add feature", "author": "Dev", "date": "2024-01-01"},
        {"hash": "def", "message": "fix!: breaking fix", "author": "Dev", "date": "2024-01-02"},
        {"hash": "ghi", "message": "update things", "author": "Dev", "date": "2024-01-03"},  # Unclear
    ]

    # Configure only "feat", but heuristics should still catch breaking changes and unclear commits
    important = identify_important_commits(commits, always_diff_types=["feat"])
    
    assert len(important) == 3
    hashes = [c["hash"] for c in important]
    assert "abc" in hashes  # feat (configured)
    assert "def" in hashes  # breaking (heuristic)
    assert "ghi" in hashes  # unclear (heuristic)


def test_collect_commits_and_diffs_with_always_diff_types(tmp_path, monkeypatch):
    """Test that collect_commits_and_diffs passes always_diff_types correctly."""
    sample_commits = [
        {"hash": "abc123", "message": "feat: add feature", "author": "Dev", "date": "2024-01-01"},
        {"hash": "def456", "message": "fix: resolve bug", "author": "Dev", "date": "2024-01-02"},
    ]

    def mock_get_commit_log(*args, **kwargs):
        return sample_commits

    def mock_get_commit_diff(*args, **kwargs):
        return "sample diff content"

    monkeypatch.setattr("releaser.ai.data_collector.get_commit_log", mock_get_commit_log)
    monkeypatch.setattr("releaser.ai.data_collector.get_commit_diff", mock_get_commit_diff)

    # Call with always_diff_types
    data = collect_commits_and_diffs(
        repo_path=tmp_path,
        from_ref="v1.0.0",
        to_ref="HEAD",
        include_diffs=True,
        always_diff_types=["feat"],
    )

    # Should only include diff for feat commit
    assert len(data["commits"]) == 2
    assert len(data["diffs"]) == 1
    assert "abc123" in data["diffs"]  # feat commit
    assert "def456" not in data["diffs"]  # fix not configured
