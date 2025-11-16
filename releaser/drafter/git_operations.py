"""
Git operations for the release generator.
"""

import subprocess
from pathlib import Path

from . import utils


def create_release_branch(
    version: str,
    base_branch: str,
    tag_prefix: str = "v",
    dry_run: bool = False,
    logger=None,
) -> str:
    """Create and checkout a new release branch from the specified base branch."""
    branch_name = f"release/{tag_prefix}{version}"

    if dry_run:
        if logger:
            logger.log_info(
                f"DRY RUN: Would create and checkout branch: {branch_name} from {base_branch}"
            )
        return branch_name

    try:
        # Check if branch already exists
        result = utils.run_command(["git", "branch", "--list", branch_name])
        if result.stdout.strip():
            if logger:
                logger.log_error(f"Branch {branch_name} already exists")
            return ""

        # Ensure we're on the base branch
        utils.run_command(["git", "checkout", base_branch], capture_output=False)
        if logger:
            logger.log_info(f"Switched to base branch: {base_branch}")

        # Create and checkout new branch from current branch
        utils.run_command(["git", "checkout", "-b", branch_name], capture_output=False)
        if logger:
            logger.log_success(
                f"Created and checked out branch: {branch_name} from {base_branch}"
            )
        return branch_name

    except subprocess.CalledProcessError as e:
        if logger:
            logger.log_error(
                f"Failed to create branch {branch_name} from {base_branch}: {e}"
            )
        return ""


def commit_release_changes(
    version: str,
    changelog_file: str,
    pyproject_file: str,
    tag_prefix: str = "v",
    dry_run: bool = False,
    logger=None,
) -> bool:
    """Commit the changelog and version changes."""
    if dry_run:
        if logger:
            logger.log_info(f"DRY RUN: Would commit release changes for {version}")
        return True

    try:
        # Add files
        files_to_add = [changelog_file]
        if Path(pyproject_file).exists():
            files_to_add.append(pyproject_file)

        for file in files_to_add:
            utils.run_command(["git", "add", file])

        # Commit changes
        commit_message = f"chore: bump version to {tag_prefix}{version}\n\n- Update {changelog_file} with release notes"
        if Path(pyproject_file).exists():
            commit_message += f"\n- Bump version in {pyproject_file} to {version}"

        utils.run_command(["git", "commit", "-m", commit_message], capture_output=False)
        if logger:
            logger.log_success(f"Committed release changes for {tag_prefix + version}")
        return True

    except subprocess.CalledProcessError as e:
        if logger:
            logger.log_error(f"Failed to commit changes: {e}")
        return False


def push_release_branch(branch_name: str, dry_run: bool = False, logger=None) -> bool:
    """Push the release branch to remote."""
    if dry_run:
        if logger:
            logger.log_info(f"DRY RUN: Would push branch: {branch_name}")
        return True

    try:
        utils.run_command(
            ["git", "push", "-u", "origin", branch_name], capture_output=False
        )
        if logger:
            logger.log_success(f"Pushed branch: {branch_name}")
        return True

    except subprocess.CalledProcessError as e:
        if logger:
            logger.log_error(f"Failed to push branch {branch_name}: {e}")
        return False


def create_git_tag(
    version: str, tag_prefix: str = "v", dry_run: bool = False, logger=None
) -> bool:
    """Create git tag."""
    tag = f"{tag_prefix}{version}"

    if dry_run:
        if logger:
            logger.log_info(f"DRY RUN: Would create tag: {tag}")
        return True

    try:
        # Check if tag already exists
        result = utils.run_command(["git", "tag", "-l"])
        if tag in result.stdout.split("\n"):
            if logger:
                logger.log_error(f"Tag {tag} already exists")
            return False

        utils.run_command(
            ["git", "tag", "-a", tag, "-m", f"Release {tag}"], capture_output=False
        )
        if logger:
            logger.log_success(f"Created tag: {tag}")
        return True

    except subprocess.CalledProcessError:
        if logger:
            logger.log_error(f"Failed to create tag: {tag}")
        return False


def push_git_tag(
    version: str, tag_prefix: str = "v", dry_run: bool = False, logger=None
) -> bool:
    """Push git tag to remote."""
    tag = f"{tag_prefix}{version}"

    if dry_run:
        if logger:
            logger.log_info(f"DRY RUN: Would push tag: {tag}")
        return True

    try:
        utils.run_command(["git", "push", "origin", tag], capture_output=False)
        if logger:
            logger.log_success(f"Pushed tag: {tag}")
        return True

    except subprocess.CalledProcessError as e:
        if logger:
            logger.log_error(f"Failed to push tag {tag}: {e}")
        return False
