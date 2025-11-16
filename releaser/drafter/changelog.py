"""
Changelog generation and version management utilities.
"""

import re
from pathlib import Path
from typing import List

from ..console import console
from . import utils


def get_current_version(
    tag_prefix: str = "v", pyproject_file: str = "pyproject.toml", logger=None
) -> str:
    """Get the latest version from git tags or pyproject.toml."""
    # First try to get from git tags
    git_version = utils.get_latest_tag()

    if git_version:
        if logger:
            logger.log_info(f"Found git tag version: {git_version}")
        return git_version

    # Fallback to pyproject.toml if no tags found
    if Path(pyproject_file).exists():
        pyproject_version = utils.get_pyproject_version(pyproject_file)
        if pyproject_version:
            full_version = f"{tag_prefix}{pyproject_version}"
            if logger:
                logger.log_info(f"Found pyproject.toml version: {full_version}")
            return full_version

    if logger:
        logger.log_info("No existing version found, starting from v0.0.0")
    return f"{tag_prefix}0.0.0"


def categorize_commits(commits: List[str]) -> str:
    """Categorize commits with template format."""
    if not commits:
        return "No changes recorded."

    categories = {
        "🚀 Features": [],
        "🐛 Bug Fixes": [],
        "📚 Documentation": [],
        "⚡ Performance": [],
        "💥 Breaking Changes": [],
        "🔄 Other Changes": [],
    }

    for commit in commits:
        if not commit.strip():
            continue

        # Parse commit format: sha|message|author
        if "|" in commit:
            parts = commit.split("|", 2)
            if len(parts) >= 3:
                sha, message, author = parts[0].strip(), parts[1].strip(), parts[2].strip()
            else:
                # Fallback for incomplete format
                sha = parts[0].strip() if len(parts) > 0 else ""
                message = parts[1].strip() if len(parts) > 1 else ""
                author = "unknown"
        else:
            # Fallback for old format (just in case)
            sha_match = re.match(r"^([a-f0-9]+)\s+(.+)$", commit)
            if sha_match:
                sha, message = sha_match.groups()
                author = "unknown"
            else:
                sha = ""
                message = commit.strip()
                author = "unknown"

        commit_type = utils.parse_commit_type(message)
        
        # Skip chore commits entirely
        if commit_type == "chore":
            continue
            
        pr_number = utils.extract_pr_number(message)

        # Format the commit message: "- message by @author (sha)"
        if pr_number:
            # Remove PR number from message to avoid duplication
            message_clean = re.sub(r'\s*\(#\d+\)\s*$', '', message).strip()
            formatted_message = f"- {message_clean} by @{author} ({sha}) {pr_number}"
        else:
            formatted_message = f"- {message} by @{author} ({sha})"

        # Categorize based on type
        if commit_type == "feat":
            categories["🚀 Features"].append(formatted_message)
        elif commit_type == "fix":
            categories["🐛 Bug Fixes"].append(formatted_message)
        elif commit_type == "docs":
            categories["📚 Documentation"].append(formatted_message)
        elif commit_type == "breaking":
            categories["💥 Breaking Changes"].append(formatted_message)
        elif commit_type == "improve":
            categories["⚡ Performance"].append(formatted_message)
        else:
            categories["🔄 Other Changes"].append(formatted_message)

    # Build changelog text
    changelog_parts = []
    for category, items in categories.items():
        if items:
            changelog_parts.append(f"\n### {category}\n")
            changelog_parts.extend(items)
            changelog_parts.append("")  # Empty line

    return "\n".join(changelog_parts).strip()


def update_pyproject_version(
    pyproject_file: str, new_version: str, dry_run: bool = False, logger=None
) -> bool:
    """Update pyproject.toml version."""
    if dry_run:
        if logger:
            logger.log_info(
                f"DRY RUN: Would update {pyproject_file} version to {new_version}"
            )
        return True

    if not Path(pyproject_file).exists():
        if logger:
            logger.log_warning(f"{pyproject_file} not found")
        return False

    try:
        with open(pyproject_file, "r") as f:
            content = f.read()

        # Update version field (handle both single and double quotes)
        updated_content = re.sub(
            r'^version\s*=\s*["\'][^"\']*["\']',
            f'version = "{new_version}"',
            content,
            flags=re.MULTILINE,
        )

        with open(pyproject_file, "w") as f:
            f.write(updated_content)

        if logger:
            logger.log_success(f"Updated {pyproject_file} version to {new_version}")
        return True

    except Exception as e:
        if logger:
            logger.log_error(f"Failed to update {pyproject_file}: {e}")
        return False


def update_changelog(
    changelog_file: str, new_changelog: str, dry_run: bool = False, logger=None
) -> bool:
    """Update changelog with new template."""
    if dry_run:
        if logger:
            logger.log_info(f"DRY RUN: Would update {changelog_file}")
        return True

    try:
        # Read existing changelog if it exists
        existing_content = ""
        if Path(changelog_file).exists():
            with open(changelog_file, "r") as f:
                existing_content = f.read()

        # If the file is empty or doesn't exist, create header
        if not existing_content.strip():
            full_content = f"# Changelog\n\n---\n\nAll notable changes to this project will be documented in this file.\n\n{new_changelog}"
        else:
            # Insert new changelog after the header
            lines = existing_content.split("\n")

            # Find where to insert (after the header and any initial description)
            insert_index = 0
            for i, line in enumerate(lines):
                if line.startswith("# ") and i == 0:
                    # Found main header, look for next section or end of description
                    for j in range(i + 1, len(lines)):
                        if lines[j].startswith("# ") or lines[j].startswith("## "):
                            insert_index = j
                            break
                        elif j == len(lines) - 1:
                            insert_index = len(lines)
                            break
                    break
            else:
                # No header found, insert at beginning
                insert_index = 0

            # Insert new content
            if insert_index < len(lines):
                lines.insert(insert_index, new_changelog)
                lines.insert(insert_index + 1, "")  # Add empty line
            else:
                lines.extend(["", new_changelog])

            full_content = "\n".join(lines)

        # Write updated content
        with open(changelog_file, "w") as f:
            f.write(full_content)

        if logger:
            logger.log_success(f"Updated {changelog_file}")
        return True

    except Exception as e:
        if logger:
            logger.log_error(f"Failed to update {changelog_file}: {e}")
        return False


def parse_version(version_str: str) -> tuple:
    """Parse version string into components.

    Returns: (major, minor, patch, is_rc, rc_number)
    """
    # Remove 'v' prefix if present
    version_str = version_str.lstrip("v")

    # Check for RC version
    is_rc = False
    rc_number = 0
    base_version = version_str

    if "-rc." in version_str:
        base_version, rc_part = version_str.split("-rc.")
        is_rc = True
        rc_number = int(rc_part)

    # Parse base version
    parts = base_version.split(".")
    major = int(parts[0]) if len(parts) > 0 else 0
    minor = int(parts[1]) if len(parts) > 1 else 0
    patch = int(parts[2]) if len(parts) > 2 else 0

    return major, minor, patch, is_rc, rc_number


def calculate_next_version(current_version: str, bump_type: str, branch: str) -> str:
    """Calculate next version based on bump type and branch.

    Args:
        current_version: Current version string (with or without 'v' prefix)
        bump_type: One of 'major', 'minor', 'patch', 'skip', 'custom'
        branch: Current git branch name

    Returns:
        New version string (without 'v' prefix)
    """
    if bump_type == "custom":
        return None  # Will be handled separately

    major, minor, patch, is_rc, rc_num = parse_version(current_version)

    # Check if we're on a branch that should create RC versions
    is_prerelease_branch = (
        branch in ["develop", "development", "dev"] or
        branch.startswith("release/") or
        branch.startswith("hotfix/")
    )

    if is_prerelease_branch:
        # Develop branch - always create RC versions
        if bump_type == "skip":
            # Continue current RC series or add RC to current version
            if is_rc:
                return f"{major}.{minor}.{patch}-rc.{rc_num + 1}"
            else:
                # No RC yet, just add RC to current version without bumping
                return f"{major}.{minor}.{patch}-rc.1"

        # Calculate new base version
        if bump_type == "major":
            new_base = f"{major + 1}.0.0"
        elif bump_type == "minor":
            new_base = f"{major}.{minor + 1}.0"
        else:  # patch
            new_base = f"{major}.{minor}.{patch + 1}"

        # Always start new RC series for new versions
        return f"{new_base}-rc.1"

    else:
        # Main/master branch - clean versions only
        if bump_type == "major":
            return f"{major + 1}.0.0"
        elif bump_type == "minor":
            return f"{major}.{minor + 1}.0"
        elif bump_type == "patch":
            return f"{major}.{minor}.{patch + 1}"
        else:
            # Skip doesn't make sense on main branch
            return f"{major}.{minor}.{patch + 1}"


def prompt_manual_version() -> str:
    """Prompt for version selection with branch-aware logic."""
    from .colors import Colors

    # Get current branch and latest tag
    current_branch = utils.get_current_branch()
    latest_tag = utils.get_latest_tag()
    is_prerelease_branch = (
        current_branch in ["develop", "development", "dev"] or
        current_branch.startswith("release/") or
        current_branch.startswith("hotfix/")
    )

    # Parse current version
    if latest_tag:
        major, minor, patch, is_rc, rc_num = parse_version(latest_tag)
        current_version_display = latest_tag
    else:
        major, minor, patch, is_rc, rc_num = 0, 0, 0, False, 0
        current_version_display = "none"
        latest_tag = "v0.0.0"  # Default for calculations

    from rich.panel import Panel
    from rich.table import Table

    # Create info panel
    info_table = Table.grid(padding=1)
    info_table.add_column(style="green")
    info_table.add_column(style="bright_red bold")
    info_table.add_row("Current branch:", current_branch)
    info_table.add_row("Current version:", current_version_display)

    panel = Panel(
        info_table, title="📋 Version Selection", style="blue", padding=(1, 2)
    )
    console.print(panel)

    if is_rc:
        print(f"{Colors.YELLOW}Currently on release candidate {rc_num}{Colors.NC}")

    print()

    # Build menu options based on branch
    if is_prerelease_branch:
        # Develop branch menu
        if is_rc:
            # Already on RC, show context-aware options
            print("Select version action:")
            print(
                f"  {Colors.CYAN}[1]{Colors.NC} Continue RC ({major}.{minor}.{patch}-rc.{rc_num + 1}) - More testing needed"
            )
            print(
                f"  {Colors.CYAN}[2]{Colors.NC} New Patch ({major}.{minor}.{patch + 1}-rc.1) - Start patch release"
            )
            print(
                f"  {Colors.CYAN}[3]{Colors.NC} New Minor ({major}.{minor + 1}.0-rc.1) - Start next minor"
            )
            print(
                f"  {Colors.CYAN}[4]{Colors.NC} New Major ({major + 1}.0.0-rc.1) - Start major release"
            )
            print(f"  {Colors.CYAN}[5]{Colors.NC} Custom - Type exact version")

            choice_map = {
                "1": "skip",
                "2": "patch",
                "3": "minor",
                "4": "major",
                "5": "custom",
            }
        else:
            # Not on RC, show standard bump options with Skip
            print("Select version action:")
            print(
                f"  {Colors.CYAN}[1]{Colors.NC} Skip/Add RC ({major}.{minor}.{patch}-rc.1) - Create RC for current version"
            )
            print(
                f"  {Colors.CYAN}[2]{Colors.NC} Patch ({major}.{minor}.{patch + 1}-rc.1) - Bug fixes"
            )
            print(
                f"  {Colors.CYAN}[3]{Colors.NC} Minor ({major}.{minor + 1}.0-rc.1) - New features"
            )
            print(
                f"  {Colors.CYAN}[4]{Colors.NC} Major ({major + 1}.0.0-rc.1) - Breaking changes"
            )
            print(f"  {Colors.CYAN}[5]{Colors.NC} Custom - Type exact version")

            choice_map = {
                "1": "skip",
                "2": "patch",
                "3": "minor",
                "4": "major",
                "5": "custom",
            }
    else:
        # Main/master branch menu - clean versions only
        print("Select version bump:")
        print(
            f"  {Colors.CYAN}[1]{Colors.NC} Patch ({major}.{minor}.{patch + 1}) - Bug fixes"
        )
        print(
            f"  {Colors.CYAN}[2]{Colors.NC} Minor ({major}.{minor + 1}.0) - New features"
        )
        print(
            f"  {Colors.CYAN}[3]{Colors.NC} Major ({major + 1}.0.0) - Breaking changes"
        )
        print(f"  {Colors.CYAN}[4]{Colors.NC} Custom - Type exact version")

        choice_map = {"1": "patch", "2": "minor", "3": "major", "4": "custom"}

    print()

    # Get user choice
    while True:
        max_choice = str(len(choice_map))
        choice = input(f"Choice [1-{max_choice}]: ").strip()

        if choice in choice_map:
            bump_type = choice_map[choice]
            break
        else:
            print(f"Please enter a number between 1 and {max_choice}")

    # Calculate or get custom version
    if bump_type == "custom":
        print()
        while True:
            version = input(
                "Enter the version number (e.g., 1.0.0 or 1.0.0-rc.1): "
            ).strip()

            if not version:
                print("Please enter a version number.")
                continue

            # Basic version validation
            if re.match(r"^\d+(\.\d+)*(-rc\.\d+)?$", version):
                break
            else:
                print("Please enter a valid version (e.g., 1.0.0, 1.0.0-rc.1)")
    else:
        # Calculate version based on selection
        version = calculate_next_version(latest_tag, bump_type, current_branch)

    # Display selected version
    print()
    print(
        f"{Colors.GREEN}Selected version:{Colors.NC} {Colors.BRIGHT_RED}v{version}{Colors.NC}"
    )

    # Check if pyproject.toml exists and needs updating
    pyproject_file = "pyproject.toml"
    if Path(pyproject_file).exists():
        current_pyproject_version = utils.get_pyproject_version(pyproject_file)

        # For RC versions, we might not want to update pyproject.toml
        # or we might want to strip the -rc.N suffix
        if is_prerelease_branch and "-rc." in version:
            print()
            print(f"{Colors.BLUE}📦 PyProject Version Update{Colors.NC}")
            print("─" * 40)

            if current_pyproject_version:
                print(
                    f"{Colors.GREEN}Current {pyproject_file} version:{Colors.NC} {Colors.BRIGHT_RED}{current_pyproject_version}{Colors.NC}"
                )

            # Ask if they want to update pyproject with the base version (without RC)
            base_version = version.split("-rc.")[0]
            print(
                f"{Colors.YELLOW}Note: RC suffix will be stripped for {pyproject_file}{Colors.NC}"
            )
            print(
                f"{Colors.GREEN}Will update to:{Colors.NC} {Colors.BRIGHT_RED}{base_version}{Colors.NC}"
            )

            while True:
                update_pyproject = (
                    input(f"Update {pyproject_file} to {base_version}? (y/N): ")
                    .strip()
                    .lower()
                )
                if update_pyproject in ["y", "yes"]:
                    if update_pyproject_version(
                        pyproject_file, base_version, dry_run=False
                    ):
                        print(
                            f"{Colors.GREEN}✅ Updated {pyproject_file} to {base_version}{Colors.NC}"
                        )
                    else:
                        print(
                            f"{Colors.RED}❌ Failed to update {pyproject_file}{Colors.NC}"
                        )
                    break
                elif update_pyproject in ["n", "no", ""]:
                    print(
                        f"{Colors.YELLOW}⏭ Skipping {pyproject_file} update{Colors.NC}"
                    )
                    break
                else:
                    print("Please enter 'y' (yes) or 'n' (no)")
        else:
            # Main branch or non-RC version
            if current_pyproject_version != version:
                print()
                print(f"{Colors.BLUE}📦 PyProject Version Update{Colors.NC}")
                print("─" * 40)

                if current_pyproject_version:
                    print(
                        f"{Colors.GREEN}Current {pyproject_file} version:{Colors.NC} {Colors.BRIGHT_RED}{current_pyproject_version}{Colors.NC}"
                    )

                print(
                    f"{Colors.GREEN}Will update to:{Colors.NC} {Colors.BRIGHT_RED}{version}{Colors.NC}"
                )

                if update_pyproject_version(pyproject_file, version, dry_run=False):
                    print(
                        f"{Colors.GREEN}✅ Updated {pyproject_file} to {version}{Colors.NC}"
                    )
                else:
                    print(
                        f"{Colors.RED}❌ Failed to update {pyproject_file}{Colors.NC}"
                    )

    return version
