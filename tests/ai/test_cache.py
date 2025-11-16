"""Tests for AI cache module."""

import pytest
from pathlib import Path

from releaser.ai.cache import (
    compute_cache_key,
    get_cached_notes,
    save_cached_notes,
    clear_cache,
    get_cache_stats,
)


@pytest.fixture
def temp_cache_dir(tmp_path, monkeypatch):
    """Override cache directory to use temp directory for testing."""
    cache_dir = tmp_path / "cache" / "ai_notes"
    cache_dir.mkdir(parents=True, exist_ok=True)

    # Monkeypatch get_cache_dir to return our temp directory
    monkeypatch.setattr("releaser.ai.cache.get_cache_dir", lambda: cache_dir)

    return cache_dir


def test_compute_cache_key_deterministic():
    """Test that cache key is deterministic for same inputs."""
    commits = [
        {
            "hash": "abc123",
            "message": "feat: add feature",
            "author": "Dev",
            "date": "2024-01-01",
        },
        {
            "hash": "def456",
            "message": "fix: bug",
            "author": "Dev",
            "date": "2024-01-02",
        },
    ]

    key1 = compute_cache_key(
        commits=commits,
        current_version="1.2.0",
        previous_version="1.1.0",
        model="gpt-4o-mini",
        temperature=0.2,
    )

    key2 = compute_cache_key(
        commits=commits,
        current_version="1.2.0",
        previous_version="1.1.0",
        model="gpt-4o-mini",
        temperature=0.2,
    )

    assert key1 == key2
    assert len(key1) == 64  # SHA256 hex length


def test_compute_cache_key_different_for_different_inputs():
    """Test that cache key changes when inputs change."""
    commits = [
        {
            "hash": "abc123",
            "message": "feat: add feature",
            "author": "Dev",
            "date": "2024-01-01",
        }
    ]

    key1 = compute_cache_key(
        commits=commits,
        current_version="1.2.0",
        previous_version="1.1.0",
        model="gpt-4o-mini",
        temperature=0.2,
    )

    # Different version
    key2 = compute_cache_key(
        commits=commits,
        current_version="1.3.0",  # Changed
        previous_version="1.1.0",
        model="gpt-4o-mini",
        temperature=0.2,
    )

    # Different model
    key3 = compute_cache_key(
        commits=commits,
        current_version="1.2.0",
        previous_version="1.1.0",
        model="gpt-4",  # Changed
        temperature=0.2,
    )

    # Different temperature
    key4 = compute_cache_key(
        commits=commits,
        current_version="1.2.0",
        previous_version="1.1.0",
        model="gpt-4o-mini",
        temperature=0.7,  # Changed
    )

    assert key1 != key2
    assert key1 != key3
    assert key1 != key4


def test_compute_cache_key_with_diffs():
    """Test that diffs affect cache key."""
    commits = [
        {
            "hash": "abc123",
            "message": "feat: add feature",
            "author": "Dev",
            "date": "2024-01-01",
        }
    ]

    key_no_diffs = compute_cache_key(
        commits=commits,
        current_version="1.2.0",
        previous_version="1.1.0",
        model="gpt-4o-mini",
        temperature=0.2,
        diffs=None,
    )

    key_with_diffs = compute_cache_key(
        commits=commits,
        current_version="1.2.0",
        previous_version="1.1.0",
        model="gpt-4o-mini",
        temperature=0.2,
        diffs={"abc123": "diff content"},
    )

    assert key_no_diffs != key_with_diffs


def test_save_and_get_cached_notes(temp_cache_dir):
    """Test saving and retrieving cached notes."""
    cache_key = "test_cache_key_123"
    notes = "# Release Notes\n\nThis is a test."

    # Save
    save_cached_notes(cache_key, notes)

    # Verify file exists
    cache_file = temp_cache_dir / f"{cache_key}.md"
    assert cache_file.exists()

    # Retrieve
    retrieved = get_cached_notes(cache_key)
    assert retrieved == notes


def test_get_cached_notes_miss(temp_cache_dir):
    """Test cache miss returns None."""
    result = get_cached_notes("nonexistent_key")
    assert result is None


def test_clear_cache_all(temp_cache_dir):
    """Test clearing all cache."""
    # Create some cache files
    save_cached_notes("key1", "notes 1")
    save_cached_notes("key2", "notes 2")
    save_cached_notes("key3", "notes 3")

    # Verify they exist
    assert len(list(temp_cache_dir.glob("*.md"))) == 3

    # Clear all
    deleted = clear_cache(max_age_days=None)

    assert deleted == 3
    assert len(list(temp_cache_dir.glob("*.md"))) == 0


def test_clear_cache_by_age(temp_cache_dir):
    """Test clearing cache by age."""
    import time

    # Create a cache file
    save_cached_notes("old_key", "old notes")

    # Make it appear old by modifying mtime
    cache_file = temp_cache_dir / "old_key.md"
    old_time = time.time() - (60 * 24 * 60 * 60)  # 60 days ago
    Path(cache_file).touch()
    import os

    os.utime(cache_file, (old_time, old_time))

    # Create a new cache file
    save_cached_notes("new_key", "new notes")

    # Clear cache older than 30 days
    deleted = clear_cache(max_age_days=30)

    # Only old file should be deleted
    assert deleted == 1
    assert not (temp_cache_dir / "old_key.md").exists()
    assert (temp_cache_dir / "new_key.md").exists()


def test_get_cache_stats(temp_cache_dir):
    """Test getting cache statistics."""
    # Empty cache
    stats = get_cache_stats()
    assert stats["total_entries"] == 0
    assert stats["total_size_bytes"] == 0
    assert "cache_dir" in stats

    # Add some files
    save_cached_notes("key1", "notes 1")
    save_cached_notes("key2", "notes 2" * 100)  # Larger file

    stats = get_cache_stats()
    assert stats["total_entries"] == 2
    assert stats["total_size_bytes"] > 0


def test_cache_key_commit_order_matters():
    """Test that commit order affects cache key."""
    commits_order1 = [
        {"hash": "abc123", "message": "feat", "author": "Dev", "date": "2024-01-01"},
        {"hash": "def456", "message": "fix", "author": "Dev", "date": "2024-01-02"},
    ]

    commits_order2 = [
        {"hash": "def456", "message": "fix", "author": "Dev", "date": "2024-01-02"},
        {"hash": "abc123", "message": "feat", "author": "Dev", "date": "2024-01-01"},
    ]

    key1 = compute_cache_key(
        commits=commits_order1,
        current_version="1.2.0",
        previous_version="1.1.0",
        model="gpt-4o-mini",
        temperature=0.2,
    )

    key2 = compute_cache_key(
        commits=commits_order2,
        current_version="1.2.0",
        previous_version="1.1.0",
        model="gpt-4o-mini",
        temperature=0.2,
    )

    assert key1 != key2  # Order matters!
