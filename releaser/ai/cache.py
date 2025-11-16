"""Caching system for AI-generated release notes.

Provides disk-based caching to avoid redundant API calls when generating
release notes for the same commits/version multiple times.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Optional

from releaser.console import logger


def get_cache_dir() -> Path:
    """Get the cache directory path.

    Returns:
        Path to ~/.releaser/cache/ai_notes/

    Creates the directory if it doesn't exist.
    """
    cache_dir = Path.home() / ".releaser" / "cache" / "ai_notes"
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir


def compute_cache_key(
    *,
    commits: list[dict[str, Any]],
    current_version: str,
    previous_version: str,
    model: str,
    temperature: float,
    diffs: dict[str, str] | None = None,
) -> str:
    """Compute a cache key for a set of release notes parameters.

    The cache key is a hash of all inputs that affect the output:
    - Commit hashes (order matters)
    - Version numbers
    - AI model and temperature
    - Diff content (if included)

    Args:
        commits: List of commit dictionaries
        current_version: Target version
        previous_version: Previous version
        model: AI model name
        temperature: Sampling temperature
        diffs: Optional diffs dictionary

    Returns:
        SHA256 hash as hex string

    Example:
        >>> commits = [{"hash": "abc123", "message": "feat: add feature"}]
        >>> key = compute_cache_key(
        ...     commits=commits,
        ...     current_version="1.2.0",
        ...     previous_version="1.1.0",
        ...     model="gpt-4o-mini",
        ...     temperature=0.2
        ... )
        >>> len(key)
        64
    """
    # Create deterministic representation
    cache_input = {
        "commits": [c["hash"] for c in commits],  # Only hash, order matters
        "current_version": current_version,
        "previous_version": previous_version,
        "model": model,
        "temperature": temperature,
        "diffs": sorted(diffs.keys())
        if diffs
        else [],  # Diff commit hashes (sorted for determinism)
    }

    # Serialize to JSON with sorted keys for determinism
    cache_str = json.dumps(cache_input, sort_keys=True)

    # Hash it
    return hashlib.sha256(cache_str.encode()).hexdigest()


def get_cached_notes(cache_key: str) -> Optional[str]:
    """Retrieve cached release notes if available.

    Args:
        cache_key: Cache key from compute_cache_key()

    Returns:
        Cached markdown notes or None if not found

    Example:
        >>> notes = get_cached_notes("abc123...")
        >>> if notes:
        ...     print("Cache hit!")
        ... else:
        ...     print("Cache miss")
    """
    cache_file = get_cache_dir() / f"{cache_key}.md"

    if not cache_file.exists():
        logger.debug(f"Cache miss: {cache_key[:16]}...")
        return None

    try:
        notes = cache_file.read_text(encoding="utf-8")
        logger.info(
            f"✓ Cache hit! Using cached release notes (key: {cache_key[:16]}...)"
        )
        return notes
    except Exception as e:
        logger.warning(f"Failed to read cache file: {e}")
        return None


def save_cached_notes(cache_key: str, notes: str) -> None:
    """Save release notes to cache.

    Args:
        cache_key: Cache key from compute_cache_key()
        notes: Markdown notes to cache

    Example:
        >>> save_cached_notes("abc123...", "## Release Notes\\n...")
    """
    cache_file = get_cache_dir() / f"{cache_key}.md"

    try:
        cache_file.write_text(notes, encoding="utf-8")
        logger.debug(f"Saved to cache: {cache_key[:16]}...")
    except Exception as e:
        logger.warning(f"Failed to save to cache: {e}")


def clear_cache(max_age_days: Optional[int] = None) -> int:
    """Clear cached release notes.

    Args:
        max_age_days: If specified, only clear cache older than N days.
                     If None, clear all cache.

    Returns:
        Number of cache files deleted

    Example:
        >>> # Clear all cache
        >>> count = clear_cache()
        >>> print(f"Deleted {count} cache entries")

        >>> # Clear cache older than 30 days
        >>> count = clear_cache(max_age_days=30)
    """
    cache_dir = get_cache_dir()
    deleted = 0

    if max_age_days is None:
        # Delete all
        for cache_file in cache_dir.glob("*.md"):
            try:
                cache_file.unlink()
                deleted += 1
            except Exception as e:
                logger.warning(f"Failed to delete {cache_file}: {e}")
    else:
        # Delete old files
        import time

        cutoff_time = time.time() - (max_age_days * 24 * 60 * 60)

        for cache_file in cache_dir.glob("*.md"):
            try:
                if cache_file.stat().st_mtime < cutoff_time:
                    cache_file.unlink()
                    deleted += 1
            except Exception as e:
                logger.warning(f"Failed to delete {cache_file}: {e}")

    if deleted > 0:
        logger.info(f"Cleared {deleted} cache entries")

    return deleted


def get_cache_stats() -> dict[str, Any]:
    """Get cache statistics.

    Returns:
        Dictionary with cache statistics:
        - total_entries: Number of cached files
        - total_size_bytes: Total size of cache
        - cache_dir: Path to cache directory

    Example:
        >>> stats = get_cache_stats()
        >>> print(f"Cache has {stats['total_entries']} entries")
        >>> print(f"Total size: {stats['total_size_bytes'] / 1024:.1f} KB")
    """
    cache_dir = get_cache_dir()
    cache_files = list(cache_dir.glob("*.md"))

    total_size = sum(f.stat().st_size for f in cache_files)

    return {
        "total_entries": len(cache_files),
        "total_size_bytes": total_size,
        "cache_dir": str(cache_dir),
    }
