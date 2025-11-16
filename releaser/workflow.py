#!/usr/bin/env python3
"""
Git Workflow Validator

This script validates whether a Git repository follows the prescribed workflow:
- Feature branches: feature/* → merge to main
- Bugfix branches: bugfix/* → merge to feature or main
- Release branches: release/* → merge to main, tagged
- Hotfix branches: hotfix/* → merge to main, tagged
- Master/Main branch: protected, only receives merges
"""

import json
import re
import subprocess
from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional


class BranchType(Enum):
    FEATURE = "feature"
    BUGFIX = "bugfix"
    RELEASE = "release"
    HOTFIX = "hotfix"
    MAIN = "main"
    OTHER = "other"


@dataclass
class ValidationResult:
    passed: bool
    message: str
    severity: str  # 'error', 'warning', 'info'


@dataclass
class Branch:
    name: str
    type: BranchType
    commits: List[str]
    merged_to: Optional[str] = None
    merge_commit: Optional[str] = None


class GitWorkflowValidator:
    def __init__(self, repo_path: str = "."):
        self.repo_path = repo_path
        self.main_branches = ["main", "master"]
        self.results: List[ValidationResult] = []

    def run_git_command(self, command: List[str]) -> str:
        """Execute a git command and return the output."""
        try:
            result = subprocess.run(
                ["git", "-C", self.repo_path] + command,
                capture_output=True,
                text=True,
                check=True,
            )
            return result.stdout.strip()
        except subprocess.CalledProcessError as e:
            raise Exception(f"Git command failed: {e}")

    def get_branch_type(self, branch_name: str) -> BranchType:
        """Determine the type of branch based on naming convention."""
        if branch_name in self.main_branches:
            return BranchType.MAIN
        elif branch_name.startswith("feature/"):
            return BranchType.FEATURE
        elif branch_name.startswith("bugfix/"):
            return BranchType.BUGFIX
        elif branch_name.startswith("release/"):
            return BranchType.RELEASE
        elif branch_name.startswith("hotfix/"):
            return BranchType.HOTFIX
        else:
            return BranchType.OTHER

    def get_all_branches(self) -> List[str]:
        """Get all branches in the repository."""
        output = self.run_git_command(["branch", "-a", "--format=%(refname:short)"])
        branches = []
        for line in output.split("\n"):
            if line and not line.startswith("origin/"):
                branches.append(line.strip())
        return branches

    def get_merged_branches(self) -> Dict[str, str]:
        """Get branches that have been merged and their merge commits."""
        merged_branches = {}

        # Get merge commits
        merge_log = self.run_git_command(
            ["log", "--merges", "--pretty=format:%H|%s|%P", "--all"]
        )

        for line in merge_log.split("\n"):
            if line:
                parts = line.split("|")
                if len(parts) >= 3:
                    merge_commit = parts[0]
                    message = parts[1]
                    _parents = parts[2].split()

                    # Extract branch name from merge message
                    branch_match = re.search(r"Merge branch '([^']+)'", message)
                    if branch_match:
                        branch_name = branch_match.group(1)
                        merged_branches[branch_name] = merge_commit

        return merged_branches

    def get_tags(self) -> Dict[str, str]:
        """Get all tags and their associated commits."""
        tags = {}
        tag_output = self.run_git_command(
            ["tag", "-l", "--format=%(refname:short)|%(objectname)"]
        )

        for line in tag_output.split("\n"):
            if line and "|" in line:
                tag_name, commit_hash = line.split("|", 1)
                tags[tag_name] = commit_hash

        return tags

    def validate_branch_naming(self) -> List[ValidationResult]:
        """Validate branch naming conventions."""
        results = []
        branches = self.get_all_branches()

        for branch in branches:
            branch_type = self.get_branch_type(branch)

            if branch_type == BranchType.OTHER and branch not in self.main_branches:
                results.append(
                    ValidationResult(
                        passed=False,
                        message=f"Branch '{branch}' doesn't follow naming convention (feature/, bugfix/, release/, hotfix/)",
                        severity="warning",
                    )
                )
            elif branch_type != BranchType.OTHER:
                results.append(
                    ValidationResult(
                        passed=True,
                        message=f"Branch '{branch}' follows naming convention",
                        severity="info",
                    )
                )

        return results

    def validate_merge_patterns(self) -> List[ValidationResult]:
        """Validate that merges follow the correct workflow patterns."""
        results = []
        merged_branches = self.get_merged_branches()

        for branch_name, merge_commit in merged_branches.items():
            branch_type = self.get_branch_type(branch_name)

            # Get the target branch for this merge
            merge_info = self.run_git_command(
                ["log", "--pretty=format:%s", "-1", merge_commit]
            )

            # Validate merge targets based on branch type
            if branch_type == BranchType.FEATURE:
                if "main" in merge_info.lower() or "master" in merge_info.lower():
                    results.append(
                        ValidationResult(
                            passed=True,
                            message=f"Feature branch '{branch_name}' correctly merged to main",
                            severity="info",
                        )
                    )
                else:
                    results.append(
                        ValidationResult(
                            passed=False,
                            message=f"Feature branch '{branch_name}' should merge to main/master",
                            severity="error",
                        )
                    )

            elif branch_type == BranchType.RELEASE:
                if "main" in merge_info.lower() or "master" in merge_info.lower():
                    results.append(
                        ValidationResult(
                            passed=True,
                            message=f"Release branch '{branch_name}' correctly merged to main",
                            severity="info",
                        )
                    )
                else:
                    results.append(
                        ValidationResult(
                            passed=False,
                            message=f"Release branch '{branch_name}' should merge to main/master",
                            severity="error",
                        )
                    )

            elif branch_type == BranchType.HOTFIX:
                if "main" in merge_info.lower() or "master" in merge_info.lower():
                    results.append(
                        ValidationResult(
                            passed=True,
                            message=f"Hotfix branch '{branch_name}' correctly merged to main",
                            severity="info",
                        )
                    )
                else:
                    results.append(
                        ValidationResult(
                            passed=False,
                            message=f"Hotfix branch '{branch_name}' should merge to main/master",
                            severity="error",
                        )
                    )

        return results

    def validate_release_tagging(self) -> List[ValidationResult]:
        """Validate that releases and hotfixes are properly tagged."""
        results = []
        tags = self.get_tags()
        merged_branches = self.get_merged_branches()

        # Check if release branches have corresponding tags
        for branch_name, merge_commit in merged_branches.items():
            branch_type = self.get_branch_type(branch_name)

            if branch_type in [BranchType.RELEASE, BranchType.HOTFIX]:
                # Check if there's a tag near this merge commit
                has_tag = False
                for tag_name, tag_commit in tags.items():
                    if tag_commit == merge_commit:
                        has_tag = True
                        results.append(
                            ValidationResult(
                                passed=True,
                                message=f"{branch_type.value.title()} branch '{branch_name}' is properly tagged with '{tag_name}'",
                                severity="info",
                            )
                        )
                        break

                if not has_tag and re.match(
                    r"v?\d+\.\d+\.\d+", branch_name.split("/")[-1]
                ):
                    results.append(
                        ValidationResult(
                            passed=False,
                            message=f"{branch_type.value.title()} branch '{branch_name}' should have a version tag",
                            severity="error",
                        )
                    )

        return results

    def validate_main_branch_protection(self) -> List[ValidationResult]:
        """Validate that main branch only receives merge commits."""
        results = []

        try:
            # Get commits on main that are not merges
            main_branch = "main" if "main" in self.get_all_branches() else "master"
            direct_commits = self.run_git_command(
                ["log", main_branch, "--no-merges", "--pretty=format:%H|%s", "-10"]
            )

            if direct_commits:
                commit_lines = direct_commits.split("\n")
                for line in commit_lines[:5]:  # Show only first 5
                    if line:
                        commit_hash, message = line.split("|", 1)
                        results.append(
                            ValidationResult(
                                passed=False,
                                message=f"Direct commit to {main_branch}: '{message}' ({commit_hash[:8]})",
                                severity="warning",
                            )
                        )
            else:
                results.append(
                    ValidationResult(
                        passed=True,
                        message=f"Main branch ({main_branch}) only contains merge commits",
                        severity="info",
                    )
                )

        except Exception as e:
            results.append(
                ValidationResult(
                    passed=False,
                    message=f"Could not validate main branch protection: {e}",
                    severity="error",
                )
            )

        return results

    def validate_workflow(self) -> Dict[str, List[ValidationResult]]:
        """Run all workflow validations."""
        validations = {
            "Branch Naming": self.validate_branch_naming(),
            "Merge Patterns": self.validate_merge_patterns(),
            "Release Tagging": self.validate_release_tagging(),
            "Main Branch Protection": self.validate_main_branch_protection(),
        }

        return validations

    def abbreviate_commit_message(self, message: str) -> str:
        """Abbreviate commit message to show type and first few words."""
        # Common commit types
        commit_types = [
            "feat",
            "fix",
            "docs",
            "style",
            "refactor",
            "test",
            "chore",
            "perf",
            "ci",
            "build",
            "revert",
        ]

        # Check if message starts with a commit type
        for commit_type in commit_types:
            if message.lower().startswith(commit_type + ":"):
                # Extract type and first few words
                parts = message.split(":", 1)
                if len(parts) > 1:
                    # Take first 3 words after the type
                    words = parts[1].strip().split()[:3]
                    return f"{parts[0]}: {' '.join(words)}..."

        # If no type, just take first 4 words
        words = message.split()[:4]
        return " ".join(words) + "..."

    def get_branch_commit_history(
        self, branch_name: str, limit: int = 10
    ) -> List[Dict[str, str]]:
        """Get commit history for a specific branch."""
        try:
            commits = []
            log_output = self.run_git_command(
                [
                    "log",
                    branch_name,
                    "--pretty=format:%H|%s|%an|%ad",
                    f"-{limit}",
                    "--date=short",
                ]
            )

            for line in log_output.split("\n"):
                if line:
                    parts = line.split("|")
                    if len(parts) >= 4:
                        commits.append(
                            {
                                "hash": parts[0][:8],
                                "full_hash": parts[0],
                                "message": parts[1],
                                "abbrev_message": self.abbreviate_commit_message(
                                    parts[1]
                                ),
                                "author": parts[2],
                                "date": parts[3],
                            }
                        )
            return commits
        except Exception:
            return []

    def get_all_commits_with_branches(self, limit: int = 30) -> List[Dict]:
        """Get all commits with their branch information."""
        # Get all commits across all branches
        commits_info = []

        # Get commit graph with branch information
        log_output = self.run_git_command(
            [
                "log",
                "--all",
                "--graph",
                "--pretty=format:%H|%s|%d|%P|%ad",
                f"-{limit}",
                "--date=short",
            ]
        )

        for line in log_output.split("\n"):
            if "|" in line:
                # Remove graph characters
                clean_line = re.sub(r"^[\s\*\|\\\/]+", "", line)
                parts = clean_line.split("|")
                if len(parts) >= 5:
                    refs = parts[2].strip()
                    # Extract branch names from refs
                    branches = []
                    if refs:
                        # Parse refs like (HEAD -> main, origin/main, tag: v1.0.0)
                        ref_matches = re.findall(r"(?:HEAD -> )?([^,\(\)]+)", refs)
                        for ref in ref_matches:
                            ref = ref.strip()
                            if (
                                ref
                                and not ref.startswith("tag:")
                                and not ref.startswith("origin/")
                            ):
                                branches.append(ref)

                    commits_info.append(
                        {
                            "hash": parts[0][:8],
                            "full_hash": parts[0],
                            "message": parts[1],
                            "abbrev_message": self.abbreviate_commit_message(parts[1]),
                            "branches": branches,
                            "parents": parts[3].split() if parts[3] else [],
                            "date": parts[4],
                        }
                    )

        return commits_info

    def get_commit_statistics(self) -> Dict:
        """Generate statistics about commits and branches."""
        branches = self.get_all_branches()
        all_commits = self.get_all_commits_with_branches(200)

        stats = {
            "total_commits": len(all_commits),
            "branches": {"total": len(branches), "by_type": {}},
            "commits_by_type": {},
            "commits_by_author": {},
            "commits_by_month": {},
            "average_commits_per_day": 0,
            "most_active_day": "",
            "branch_details": [],
        }

        # Count branches by type
        for branch in branches:
            branch_type = self.get_branch_type(branch).value
            stats["branches"]["by_type"][branch_type] = (
                stats["branches"]["by_type"].get(branch_type, 0) + 1
            )

            # Get branch details
            try:
                # Get branch creation date and commit count
                branch_commits = self.get_branch_commit_history(branch, 100)
                if branch_commits:
                    stats["branch_details"].append(
                        {
                            "name": branch,
                            "type": branch_type,
                            "commit_count": len(branch_commits),
                            "last_commit": branch_commits[0]["date"]
                            if branch_commits
                            else None,
                            "first_commit": branch_commits[-1]["date"]
                            if branch_commits
                            else None,
                        }
                    )
            except Exception:
                pass

        # Analyze commits
        dates = []
        for commit in all_commits:
            # Count by commit type
            commit_type = "other"
            for ctype in ["feat", "fix", "docs", "style", "refactor", "test", "chore"]:
                if commit["message"].lower().startswith(ctype + ":"):
                    commit_type = ctype
                    break
            stats["commits_by_type"][commit_type] = (
                stats["commits_by_type"].get(commit_type, 0) + 1
            )

            # Count by author
            author = self.run_git_command(
                ["log", "--pretty=format:%an", "-1", commit["full_hash"]]
            )
            stats["commits_by_author"][author] = (
                stats["commits_by_author"].get(author, 0) + 1
            )

            # Count by month
            if commit["date"]:
                month = commit["date"][:7]  # YYYY-MM
                stats["commits_by_month"][month] = (
                    stats["commits_by_month"].get(month, 0) + 1
                )
                dates.append(commit["date"])

        # Calculate average commits per day
        if dates:
            from datetime import datetime

            date_objs = [datetime.strptime(d, "%Y-%m-%d") for d in dates if d]
            if len(date_objs) > 1:
                days_span = (date_objs[0] - date_objs[-1]).days
                if days_span > 0:
                    stats["average_commits_per_day"] = round(len(dates) / days_span, 2)

        return stats

    def generate_interactive_data(self) -> Dict:
        """Generate data for interactive visualization."""
        branches = self.get_all_branches()
        all_commits = self.get_all_commits_with_branches(100)
        stats = self.get_commit_statistics()

        # Get detailed commit information
        commit_details = []
        for i, commit in enumerate(reversed(all_commits[-20:])):  # Last 20 commits
            try:
                # Get full commit details
                details = self.run_git_command(
                    [
                        "log",
                        "--pretty=format:%H|%s|%an|%ae|%ad|%P",
                        "-1",
                        commit["full_hash"],
                        "--date=iso",
                    ]
                ).split("|")

                if len(details) >= 5:
                    # Get changed files
                    changed_files = (
                        self.run_git_command(
                            [
                                "show",
                                "--name-status",
                                "--pretty=format:",
                                commit["full_hash"],
                            ]
                        )
                        .strip()
                        .split("\n")
                    )

                    commit_details.append(
                        {
                            "id": f"commit_{i}",
                            "hash": details[0][:8],
                            "full_hash": details[0],
                            "message": details[1],
                            "abbrev_message": self.abbreviate_commit_message(
                                details[1]
                            ),
                            "author": details[2],
                            "email": details[3],
                            "date": details[4],
                            "parents": details[5].split() if len(details) > 5 else [],
                            "files_changed": len([f for f in changed_files if f]),
                            "branches": commit.get("branches", []),
                        }
                    )
            except Exception:
                pass

        return {
            "commits": commit_details,
            "statistics": stats,
            "branches": branches,
            "main_branch": "main" if "main" in branches else "master",
        }

    def generate_mermaid_diagram(self) -> str:
        """Generate a Mermaid diagram showing branch commit flow."""
        branches = self.get_all_branches()
        tags = self.get_tags()

        # Initialize diagram
        diagram = ["```mermaid", "gitGraph"]

        # Find main branch
        main_branch = "main" if "main" in branches else "master"

        # Get all commits with branch info
        all_commits = self.get_all_commits_with_branches(100)

        # Track current branch and created branches
        current_branch = main_branch
        created_branches = {main_branch}
        processed_commits = set()

        # Reverse commits for chronological order
        commits_chronological = list(reversed(all_commits))

        # Show only first 3 and last 5 commits if more than 10 total
        if len(commits_chronological) > 10:
            commits_to_show = (
                commits_chronological[:3] + [None] + commits_chronological[-5:]
            )
        else:
            commits_to_show = commits_chronological

        # Process selected commits
        for i, commit in enumerate(commits_to_show):
            if commit is None:
                # Add visual separator for skipped commits
                diagram.append('    commit id: "..."')
                continue

            if commit["full_hash"] in processed_commits:
                continue

            processed_commits.add(commit["full_hash"])

            # Get abbreviated commit message
            commit_msg = commit["abbrev_message"]

            # Check if this commit introduces a new branch
            commit_branches = [b for b in commit["branches"] if b in branches]

            # If this is a merge commit
            if len(commit["parents"]) > 1:
                # This is a merge commit
                merge_message = self.run_git_command(
                    ["log", "--pretty=format:%s", "-1", commit["full_hash"]]
                )

                # Extract source branch from merge message
                branch_match = re.search(
                    r"Merge (?:branch|pull request #\d+ from) '?([^'\s]+)'?",
                    merge_message,
                )
                if branch_match:
                    source_branch = branch_match.group(1)
                    branch_type = self.get_branch_type(source_branch)

                    if branch_type != BranchType.OTHER:
                        # Ensure we're on main for the merge
                        if current_branch != main_branch:
                            diagram.append(f"    checkout {main_branch}")
                            current_branch = main_branch

                        diagram.append(
                            f'    merge {source_branch.replace("/", "_")} id: "{commit_msg}"'
                        )

                        # Check for tags
                        for tag_name, tag_commit in tags.items():
                            if tag_commit.startswith(commit["full_hash"]):
                                diagram.append(f'    tag: "{tag_name}"')
                                break
                else:
                    # Regular merge commit
                    diagram.append(f'    commit id: "{commit_msg}"')
            else:
                # Regular commit
                # Determine which branch this commit belongs to
                commit_branch = None

                # Check if commit has explicit branch info
                if commit_branches:
                    # Prefer non-main branches
                    for b in commit_branches:
                        if b != main_branch:
                            commit_branch = b
                            break
                    if not commit_branch:
                        commit_branch = commit_branches[0]
                else:
                    # Try to determine branch from commit history
                    commit_branch = main_branch

                # Create branch if needed
                if (
                    commit_branch not in created_branches
                    and commit_branch != main_branch
                ):
                    diagram.append(f"    branch {commit_branch.replace('/', '_')}")
                    created_branches.add(commit_branch)
                    current_branch = commit_branch
                elif commit_branch != current_branch:
                    diagram.append(
                        f"    checkout {commit_branch.replace('/', '_') if commit_branch != main_branch else main_branch}"
                    )
                    current_branch = commit_branch

                diagram.append(f'    commit id: "{commit_msg}"')

        # Add any active branches that haven't been included
        for branch in branches:
            branch_type = self.get_branch_type(branch)
            if branch_type in [
                BranchType.FEATURE,
                BranchType.RELEASE,
                BranchType.BUGFIX,
                BranchType.HOTFIX,
            ]:
                if branch not in created_branches:
                    # Check if this branch has any unique commits
                    try:
                        unique_commits = self.run_git_command(
                            [
                                "log",
                                f"{main_branch}..{branch}",
                                "--pretty=format:%H",
                                "-3",
                            ]
                        )
                        if unique_commits:
                            if current_branch != main_branch:
                                diagram.append(f"    checkout {main_branch}")
                                current_branch = main_branch

                            diagram.append(f"    branch {branch.replace('/', '_')}")
                            created_branches.add(branch)

                            # Add commits for this branch
                            branch_commits = self.get_branch_commit_history(branch, 3)
                            for bc in branch_commits[:3]:  # Show up to 3 commits
                                diagram.append(
                                    f'    commit id: "{bc["abbrev_message"]}"'
                                )

                            diagram.append(f"    checkout {main_branch}")
                            current_branch = main_branch
                    except Exception:
                        pass

        diagram.append("```")
        return "\n".join(diagram)

    def generate_report(self) -> str:
        """Generate a comprehensive validation report."""
        validations = self.validate_workflow()

        report = ["Git Workflow Validation Report", "=" * 35, ""]

        total_checks = 0
        passed_checks = 0
        errors = 0
        warnings = 0

        for category, results in validations.items():
            report.append(f"\n{category}:")
            report.append("-" * (len(category) + 1))

            if not results:
                report.append("  No issues found")
                continue

            for result in results:
                total_checks += 1
                if result.passed:
                    passed_checks += 1

                if result.severity == "error":
                    errors += 1
                    icon = "❌"
                elif result.severity == "warning":
                    warnings += 1
                    icon = "⚠️ "
                else:
                    icon = "✅"

                report.append(f"  {icon} {result.message}")

        # Summary
        report.extend(
            [
                "",
                "Summary:",
                "-" * 8,
                f"Total checks: {total_checks}",
                f"Passed: {passed_checks}",
                f"Errors: {errors}",
                f"Warnings: {warnings}",
                f"Success rate: {(passed_checks / total_checks * 100):.1f}%"
                if total_checks > 0
                else "No checks performed",
            ]
        )

        return "\n".join(report)


def main():
    """Main function to run the validator."""
    import argparse

    parser = argparse.ArgumentParser(description="Git Workflow Validator")
    parser.add_argument("--repo", "-r", default=".", help="Path to git repository")
    parser.add_argument(
        "--json", action="store_true", help="Output results in JSON format"
    )
    parser.add_argument(
        "--mermaid",
        action="store_true",
        help="Generate Mermaid diagram of branch commits",
    )
    parser.add_argument(
        "--interactive-data",
        action="store_true",
        help="Generate data for interactive visualization",
    )

    args = parser.parse_args()

    try:
        validator = GitWorkflowValidator(args.repo)

        if args.interactive_data:
            interactive_data = validator.generate_interactive_data()
            print(json.dumps(interactive_data, indent=2))
        elif args.mermaid:
            print(validator.generate_mermaid_diagram())
        elif args.json:
            validations = validator.validate_workflow()
            json_output = {}
            for category, results in validations.items():
                json_output[category] = [
                    {"passed": r.passed, "message": r.message, "severity": r.severity}
                    for r in results
                ]
            print(json.dumps(json_output, indent=2))
        else:
            print(validator.generate_report())

    except Exception as e:
        print(f"Error: {e}")
        return 1

    return 0


if __name__ == "__main__":
    exit(main())
