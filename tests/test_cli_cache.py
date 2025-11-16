"""Tests for cache CLI commands."""

from unittest.mock import patch
import argparse

import pytest

from releaser.cli import handle_cache_command


@pytest.fixture
def mock_cache_functions():
    """Mock cache functions."""
    with patch("releaser.ai.cache.get_cache_stats") as mock_stats, patch(
        "releaser.ai.cache.clear_cache"
    ) as mock_clear:
        # Default cache stats
        mock_stats.return_value = {
            "total_entries": 5,
            "total_size_bytes": 2048,
            "cache_dir": "/home/user/.releaser/cache/ai_notes",
        }

        # Default clear returns 5 deleted
        mock_clear.return_value = 5

        yield {
            "stats": mock_stats,
            "clear": mock_clear,
        }


def test_cache_stats_command(mock_cache_functions, capsys):
    """Test 'cache stats' command."""
    args = argparse.Namespace(cache_action="stats")

    result = handle_cache_command(args)

    # Should succeed
    assert result == 0

    # Should call get_cache_stats
    mock_cache_functions["stats"].assert_called_once()

    # Should not call clear_cache
    mock_cache_functions["clear"].assert_not_called()

    # Check output contains expected info
    captured = capsys.readouterr()
    assert "AI Cache Statistics" in captured.out
    assert "5" in captured.out  # entries
    assert "2.0 KB" in captured.out  # size


def test_cache_stats_with_large_size(mock_cache_functions, capsys):
    """Test cache stats formats large sizes correctly."""
    mock_cache_functions["stats"].return_value = {
        "total_entries": 100,
        "total_size_bytes": 5 * 1024 * 1024,  # 5 MB
        "cache_dir": "/home/user/.releaser/cache/ai_notes",
    }

    args = argparse.Namespace(cache_action="stats")
    result = handle_cache_command(args)

    assert result == 0
    captured = capsys.readouterr()
    assert "5.0 MB" in captured.out


def test_cache_stats_with_bytes(mock_cache_functions, capsys):
    """Test cache stats formats bytes correctly."""
    mock_cache_functions["stats"].return_value = {
        "total_entries": 1,
        "total_size_bytes": 512,  # < 1024 bytes
        "cache_dir": "/home/user/.releaser/cache/ai_notes",
    }

    args = argparse.Namespace(cache_action="stats")
    result = handle_cache_command(args)

    assert result == 0
    captured = capsys.readouterr()
    assert "512 B" in captured.out


def test_cache_clear_with_force(mock_cache_functions, capsys):
    """Test 'cache clear --force' command."""
    args = argparse.Namespace(
        cache_action="clear",
        force=True,
        older_than=None,
        verbose=True,
    )

    result = handle_cache_command(args)

    # Should succeed
    assert result == 0

    # Should call clear_cache
    mock_cache_functions["clear"].assert_called_once_with(max_age_days=None)

    # Check output
    captured = capsys.readouterr()
    assert "Clearing all 5 cache entries" in captured.out
    assert "Successfully deleted 5 cache entries" in captured.out


def test_cache_clear_with_older_than(mock_cache_functions, capsys):
    """Test 'cache clear --older-than' command."""
    args = argparse.Namespace(
        cache_action="clear",
        force=True,
        older_than=30,
        verbose=False,
    )

    result = handle_cache_command(args)

    assert result == 0

    # Should call clear_cache with max_age_days
    mock_cache_functions["clear"].assert_called_once_with(max_age_days=30)

    captured = capsys.readouterr()
    assert "older than 30 days" in captured.out


def test_cache_clear_empty_cache(mock_cache_functions, capsys):
    """Test clearing when cache is already empty."""
    mock_cache_functions["stats"].return_value = {
        "total_entries": 0,
        "total_size_bytes": 0,
        "cache_dir": "/home/user/.releaser/cache/ai_notes",
    }

    args = argparse.Namespace(
        cache_action="clear",
        force=True,
        older_than=None,
        verbose=False,
    )

    result = handle_cache_command(args)

    assert result == 0

    # Should not call clear_cache
    mock_cache_functions["clear"].assert_not_called()

    captured = capsys.readouterr()
    assert "already empty" in captured.out


def test_cache_clear_without_force_cancel(mock_cache_functions):
    """Test canceling cache clear without --force."""
    with patch("releaser.console.prompt_choice", return_value="No, cancel"):
        args = argparse.Namespace(
            cache_action="clear",
            force=False,
            older_than=None,
            verbose=False,
        )

        result = handle_cache_command(args)

        assert result == 0

        # Should not call clear_cache
        mock_cache_functions["clear"].assert_not_called()


def test_cache_clear_without_force_confirm(mock_cache_functions):
    """Test confirming cache clear without --force."""
    with patch("releaser.console.prompt_choice", return_value="Yes, clear cache"):
        args = argparse.Namespace(
            cache_action="clear",
            force=False,
            older_than=None,
            verbose=False,
        )

        result = handle_cache_command(args)

        assert result == 0

        # Should call clear_cache
        mock_cache_functions["clear"].assert_called_once_with(max_age_days=None)


def test_cache_no_action():
    """Test cache command without action."""
    args = argparse.Namespace(cache_action=None)

    result = handle_cache_command(args)

    # Should fail
    assert result == 1


def test_cache_unknown_action():
    """Test cache command with unknown action."""
    args = argparse.Namespace(cache_action="invalid")

    result = handle_cache_command(args)

    # Should fail
    assert result == 1


def test_cache_command_error(mock_cache_functions):
    """Test cache command handles errors gracefully."""
    mock_cache_functions["stats"].side_effect = Exception("Test error")

    args = argparse.Namespace(cache_action="stats")

    result = handle_cache_command(args)

    # Should fail
    assert result == 1
