"""
Drafter package for release generation functionality.

This package contains modular components for generating releases,
managing GitLab API integration, and handling release workflows.
"""

from .colors import Colors
from .gitlab_api import GitLabAPI
from .release_generator import ReleaseGenerator

__all__ = ["Colors", "GitLabAPI", "ReleaseGenerator"]
