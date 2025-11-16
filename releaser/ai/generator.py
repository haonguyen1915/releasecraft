"""High-level AI release notes generator.

This module orchestrates the entire AI release notes generation process,
tying together data collection, prompt rendering, and AI generation.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from releaser.ai.config import AiConfig
from releaser.ai.data_collector import collect_commits_and_diffs
from releaser.ai.engine.openai_instructor import generate_release_notes
from releaser.ai.schemas import ReleaseNotes
from releaser.ai.cache import compute_cache_key, get_cached_notes, save_cached_notes
from releaser.console import logger


def generate_release_notes_for_version(
    *,
    config: AiConfig,
    repo_path: str | Path,
    current_version: str,
    previous_version: str,
) -> str:
    """Generate AI-powered release notes for a version bump.

    This is the main entry point called from the bump flow. It orchestrates:
    1. Collecting commit data and smart diff selection
    2. Loading prompts (with custom template support)
    3. Calling OpenAI API for structured generation
    4. Converting to markdown format

    Args:
        config: AI configuration from .releaser.toml
        repo_path: Path to git repository
        current_version: New version being released (e.g., "1.2.0")
        previous_version: Previous version tag (e.g., "v1.1.0", "1.1.0")

    Returns:
        Markdown-formatted release notes string

    Raises:
        ValueError: If API key is missing or git operations fail
        ImportError: If required dependencies (jinja2, instructor, openai) not installed
        Exception: Other errors during generation (if fail_on_error=True)

    Example:
        >>> from releaser.ai.config import AiConfig
        >>> config = AiConfig(
        ...     enabled=True,
        ...     model="gpt-4o-mini",
        ...     temperature=0.2,
        ...     max_tokens=800,
        ... )
        >>> notes = generate_release_notes_for_version(
        ...     config=config,
        ...     repo_path="/path/to/repo",
        ...     current_version="1.2.0",
        ...     previous_version="v1.1.0",
        ... )
        >>> print(notes)
    """
    logger.info(
        f"Generating AI release notes from {previous_version} to {current_version}"
    )

    # Step 1: Collect commit data
    logger.debug(
        f"Collecting commits (max: {config.max_commits}, include_diffs: {config.include_diff})"
    )

    try:
        data = collect_commits_and_diffs(
            repo_path=repo_path,
            from_ref=previous_version,
            to_ref="HEAD",
            include_diffs=config.include_diff,
            max_commits=config.max_commits,
            always_diff_types=config.always_diff_types,
        )
    except Exception as e:
        raise ValueError(f"Failed to collect git data: {e}") from e

    if not data["commits"]:
        logger.warning("No commits found since last version")
        return "No changes since last release."

    logger.info(f"Found {len(data['commits'])} commits")
    if data["diffs"]:
        logger.info(f"Including diffs for {len(data['diffs'])} important commits")

    # Step 2: Check cache (if enabled)
    if config.cache:
        cache_key = compute_cache_key(
            commits=data["commits"],
            current_version=current_version,
            previous_version=previous_version,
            model=config.model,
            temperature=config.temperature,
            diffs=data["diffs"],
        )

        cached_notes = get_cached_notes(cache_key)
        if cached_notes:
            return cached_notes

    # Step 3: Get API key
    api_key = os.getenv(config.api_key_env)
    if not api_key:
        raise ValueError(
            f"API key not found in environment variable '{config.api_key_env}'. "
            f"Please set it or disable AI features."
        )

    # Step 4: Generate structured release notes
    logger.debug(
        f"Calling AI model: {config.model} (temp={config.temperature}, max_tokens={config.max_tokens})"
    )

    try:
        release_notes: ReleaseNotes = generate_release_notes(
            api_key=api_key,
            model=config.model,
            temperature=config.temperature,
            max_tokens=config.max_tokens,
            commits=data["commits"],
            current_version=current_version,
            previous_version=previous_version,
            diffs=data["diffs"] if data["diffs"] else None,
            system_prompt_file=config.system_prompt_file,
            user_prompt_file=config.prompt_release_notes_file,
        )
    except Exception as e:
        raise Exception(f"AI generation failed: {e}") from e

    # Step 5: Convert to markdown
    markdown = release_notes.to_markdown()

    logger.debug(f"Generated {len(markdown)} characters of release notes")

    # Step 6: Save to cache (if enabled)
    if config.cache:
        save_cached_notes(cache_key, markdown)

    return markdown


def generate_release_notes_with_fallback(
    *,
    config: AiConfig,
    repo_path: str | Path,
    current_version: str,
    previous_version: str,
) -> Optional[str]:
    """Generate AI release notes with graceful fallback on errors.

    Similar to generate_release_notes_for_version but catches exceptions
    and returns None instead of raising (unless fail_on_error=True).

    This is useful for bump flow integration where AI is optional.

    Args:
        config: AI configuration
        repo_path: Path to git repository
        current_version: New version
        previous_version: Previous version

    Returns:
        Markdown release notes or None if generation failed

    Example:
        >>> notes = generate_release_notes_with_fallback(
        ...     config=config,
        ...     repo_path="/path/to/repo",
        ...     current_version="1.2.0",
        ...     previous_version="v1.1.0",
        ... )
        >>> if notes:
        ...     print("AI generated notes successfully")
        ... else:
        ...     print("Failed, will use manual notes")
    """
    try:
        return generate_release_notes_for_version(
            config=config,
            repo_path=repo_path,
            current_version=current_version,
            previous_version=previous_version,
        )
    except Exception as e:
        logger.error(f"AI release notes generation failed: {e}")

        if config.fail_on_error:
            raise

        logger.warning("Falling back to manual release notes entry")
        return None
