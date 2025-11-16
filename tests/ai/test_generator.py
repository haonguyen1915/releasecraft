"""Tests for AI generator module."""

from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
import subprocess

import pytest

from releaser.ai.config import AiConfig
from releaser.ai.generator import (
    generate_release_notes_for_version,
    generate_release_notes_with_fallback,
)
from releaser.ai.schemas import ReleaseNotes


@pytest.fixture
def mock_ai_config():
    """Sample AI configuration for testing."""
    return AiConfig(
        enabled=True,
        provider="openai",
        model="gpt-4o-mini",
        api_key_env="OPENAI_API_KEY",
        temperature=0.2,
        max_tokens=800,
        cache=True,
        accept_automatically=False,
        fail_on_error=False,
        include_diff=False,
        max_commits=100,
    )


@pytest.fixture
def mock_commits():
    """Sample git commits."""
    return [
        {
            "hash": "abc123",
            "message": "feat: add new feature",
            "author": "Dev <dev@example.com>",
            "date": "2024-01-15",
        },
        {
            "hash": "def456",
            "message": "fix: resolve bug",
            "author": "Dev <dev@example.com>",
            "date": "2024-01-14",
        },
    ]


@pytest.fixture
def mock_release_notes():
    """Sample AI-generated release notes."""
    return ReleaseNotes(
        summary="Version 1.2.0 introduces new features and bug fixes.",
        highlights=["New feature added", "Bug resolved"],
        breaking_changes=[],
    )


def test_generate_release_notes_success(mock_ai_config, mock_commits, mock_release_notes, tmp_path, monkeypatch):
    """Test successful release notes generation."""
    # Mock data collection
    mock_data = {
        "commits": mock_commits,
        "diffs": {},
    }

    with patch("releaser.ai.generator.collect_commits_and_diffs", return_value=mock_data), \
         patch("releaser.ai.generator.generate_release_notes", return_value=mock_release_notes), \
         patch("releaser.ai.generator.os.getenv", return_value="fake-api-key"), \
         patch("releaser.ai.generator.get_cached_notes", return_value=None), \
         patch("releaser.ai.generator.save_cached_notes"):

        notes = generate_release_notes_for_version(
            config=mock_ai_config,
            repo_path=tmp_path,
            current_version="1.2.0",
            previous_version="1.1.0",
        )

        assert isinstance(notes, str)
        assert len(notes) > 0
        assert "1.2.0" in notes or "features" in notes.lower()


def test_generate_release_notes_with_cache_hit(mock_ai_config, mock_commits, tmp_path):
    """Test that cached notes are returned without API call."""
    cached_notes = "# Cached Release Notes\n\nThis is from cache."

    mock_data = {
        "commits": mock_commits,
        "diffs": {},
    }

    with patch("releaser.ai.generator.collect_commits_and_diffs", return_value=mock_data), \
         patch("releaser.ai.generator.get_cached_notes", return_value=cached_notes), \
         patch("releaser.ai.generator.generate_release_notes") as mock_generate:

        notes = generate_release_notes_for_version(
            config=mock_ai_config,
            repo_path=tmp_path,
            current_version="1.2.0",
            previous_version="1.1.0",
        )

        # Should return cached notes
        assert notes == cached_notes

        # Should NOT call API
        mock_generate.assert_not_called()


def test_generate_release_notes_cache_disabled(mock_ai_config, mock_commits, mock_release_notes, tmp_path):
    """Test generation with cache disabled."""
    # Disable cache
    mock_ai_config.cache = False

    mock_data = {
        "commits": mock_commits,
        "diffs": {},
    }

    with patch("releaser.ai.generator.collect_commits_and_diffs", return_value=mock_data), \
         patch("releaser.ai.generator.generate_release_notes", return_value=mock_release_notes), \
         patch("releaser.ai.generator.os.getenv", return_value="fake-api-key"), \
         patch("releaser.ai.generator.get_cached_notes") as mock_get_cache, \
         patch("releaser.ai.generator.save_cached_notes") as mock_save_cache:

        notes = generate_release_notes_for_version(
            config=mock_ai_config,
            repo_path=tmp_path,
            current_version="1.2.0",
            previous_version="1.1.0",
        )

        # Cache should not be checked or saved
        mock_get_cache.assert_not_called()
        mock_save_cache.assert_not_called()

        assert isinstance(notes, str)


def test_generate_release_notes_no_commits(mock_ai_config, tmp_path):
    """Test handling of no commits found."""
    mock_data = {
        "commits": [],
        "diffs": {},
    }

    with patch("releaser.ai.generator.collect_commits_and_diffs", return_value=mock_data):
        notes = generate_release_notes_for_version(
            config=mock_ai_config,
            repo_path=tmp_path,
            current_version="1.2.0",
            previous_version="1.1.0",
        )

        assert notes == "No changes since last release."


def test_generate_release_notes_missing_api_key(mock_ai_config, mock_commits, tmp_path):
    """Test error when API key is missing."""
    mock_data = {
        "commits": mock_commits,
        "diffs": {},
    }

    with patch("releaser.ai.generator.collect_commits_and_diffs", return_value=mock_data), \
         patch("releaser.ai.generator.os.getenv", return_value=None), \
         patch("releaser.ai.generator.get_cached_notes", return_value=None):

        with pytest.raises(ValueError, match="API key not found"):
            generate_release_notes_for_version(
                config=mock_ai_config,
                repo_path=tmp_path,
                current_version="1.2.0",
                previous_version="1.1.0",
            )


def test_generate_release_notes_git_error(mock_ai_config, tmp_path):
    """Test error handling when git operations fail."""
    with patch("releaser.ai.generator.collect_commits_and_diffs", side_effect=Exception("Git error")):

        with pytest.raises(ValueError, match="Failed to collect git data"):
            generate_release_notes_for_version(
                config=mock_ai_config,
                repo_path=tmp_path,
                current_version="1.2.0",
                previous_version="1.1.0",
            )


def test_generate_release_notes_with_diffs(mock_ai_config, mock_commits, mock_release_notes, tmp_path):
    """Test generation with diffs included."""
    mock_ai_config.include_diff = True

    mock_data = {
        "commits": mock_commits,
        "diffs": {
            "abc123": "diff --git a/file.py b/file.py\n+new code"
        },
    }

    with patch("releaser.ai.generator.collect_commits_and_diffs", return_value=mock_data), \
         patch("releaser.ai.generator.generate_release_notes", return_value=mock_release_notes) as mock_gen, \
         patch("releaser.ai.generator.os.getenv", return_value="fake-api-key"), \
         patch("releaser.ai.generator.get_cached_notes", return_value=None), \
         patch("releaser.ai.generator.save_cached_notes"):

        notes = generate_release_notes_for_version(
            config=mock_ai_config,
            repo_path=tmp_path,
            current_version="1.2.0",
            previous_version="1.1.0",
        )

        # Verify generate_release_notes was called with diffs
        call_kwargs = mock_gen.call_args.kwargs
        assert call_kwargs["diffs"] is not None
        assert "abc123" in call_kwargs["diffs"]


def test_generate_release_notes_with_fallback_success(mock_ai_config, mock_commits, mock_release_notes, tmp_path):
    """Test fallback function with successful generation."""
    mock_data = {
        "commits": mock_commits,
        "diffs": {},
    }

    with patch("releaser.ai.generator.collect_commits_and_diffs", return_value=mock_data), \
         patch("releaser.ai.generator.generate_release_notes", return_value=mock_release_notes), \
         patch("releaser.ai.generator.os.getenv", return_value="fake-api-key"), \
         patch("releaser.ai.generator.get_cached_notes", return_value=None), \
         patch("releaser.ai.generator.save_cached_notes"):

        notes = generate_release_notes_with_fallback(
            config=mock_ai_config,
            repo_path=tmp_path,
            current_version="1.2.0",
            previous_version="1.1.0",
        )

        assert notes is not None
        assert isinstance(notes, str)


def test_generate_release_notes_with_fallback_error_graceful(mock_ai_config, mock_commits, tmp_path):
    """Test fallback function returns None on error (fail_on_error=False)."""
    mock_ai_config.fail_on_error = False

    with patch("releaser.ai.generator.collect_commits_and_diffs", side_effect=Exception("Some error")):

        notes = generate_release_notes_with_fallback(
            config=mock_ai_config,
            repo_path=tmp_path,
            current_version="1.2.0",
            previous_version="1.1.0",
        )

        # Should return None instead of raising
        assert notes is None


def test_generate_release_notes_with_fallback_error_strict(mock_ai_config, mock_commits, tmp_path):
    """Test fallback function raises on error when fail_on_error=True."""
    mock_ai_config.fail_on_error = True

    with patch("releaser.ai.generator.collect_commits_and_diffs", side_effect=Exception("Some error")):

        with pytest.raises(Exception, match="Some error"):
            generate_release_notes_with_fallback(
                config=mock_ai_config,
                repo_path=tmp_path,
                current_version="1.2.0",
                previous_version="1.1.0",
            )


def test_generate_release_notes_saves_to_cache(mock_ai_config, mock_commits, mock_release_notes, tmp_path):
    """Test that generated notes are saved to cache."""
    mock_data = {
        "commits": mock_commits,
        "diffs": {},
    }

    with patch("releaser.ai.generator.collect_commits_and_diffs", return_value=mock_data), \
         patch("releaser.ai.generator.generate_release_notes", return_value=mock_release_notes), \
         patch("releaser.ai.generator.os.getenv", return_value="fake-api-key"), \
         patch("releaser.ai.generator.get_cached_notes", return_value=None), \
         patch("releaser.ai.generator.save_cached_notes") as mock_save:

        notes = generate_release_notes_for_version(
            config=mock_ai_config,
            repo_path=tmp_path,
            current_version="1.2.0",
            previous_version="1.1.0",
        )

        # Verify save was called
        mock_save.assert_called_once()
        call_args = mock_save.call_args
        assert len(call_args[0]) == 2  # cache_key, notes
        assert isinstance(call_args[0][0], str)  # cache_key
        assert isinstance(call_args[0][1], str)  # notes (markdown)
