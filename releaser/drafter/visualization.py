"""
Visualization utilities for git workflow and release process.
"""
from releaser.console import console
from rich.panel import Panel
from rich.tree import Tree


def _display_rich_workflow_visualization(
    new_version: str,
    release_branch: str,
    create_mr: bool,
    auto_release: bool,
    mr_target_branch: str,
    changelog_file: str,
    pyproject_file: str,
    tag_prefix: str = "v",
):
    """Display workflow visualization using rich."""
    from rich.table import Table

    # Create current state info
    state_table = Table.grid(padding=1)
    state_table.add_column(style="blue")
    state_table.add_column(style="bright_red bold")
    state_table.add_row("📍 Current branch:", mr_target_branch)
    state_table.add_row("📦 Target version:", f"{tag_prefix}{new_version}")

    state_panel = Panel(state_table, title="Current State", style="blue")

    # Create workflow tree
    workflow_tree = Tree("🔧 [bold green]Planned Workflow[/bold green]")

    if create_mr:
        # MR workflow
        mr_branch = workflow_tree.add(
            f"🌿 Create release branch: [bright_red]{release_branch}[/bright_red]"
        )
        mr_branch.add(f"📝 Update {changelog_file}")
        if pyproject_file:
            mr_branch.add(f"🔢 Update {pyproject_file} version to {new_version}")
        mr_branch.add("💾 Commit changes")
        mr_branch.add("🚀 Push branch to remote")
        mr_branch.add(
            f"📋 Create MR: [bright_red]{release_branch}[/bright_red] → [bright_red]{mr_target_branch}[/bright_red]"
        )

        if auto_release:
            mr_branch.add(
                f"🏷️ Create and push tag: [bright_red]{tag_prefix}{new_version}[/bright_red]"
            )
            mr_branch.add("🎉 Create GitLab release")
        else:
            mr_branch.add("⏳ Wait for MR review and merge")
            mr_branch.add("🏷️ Manually create tag after merge")
    else:
        # Direct workflow
        direct_branch = workflow_tree.add("🎯 [bold]Direct Release[/bold]")
        direct_branch.add(f"📝 Update {changelog_file}")
        if pyproject_file:
            direct_branch.add(f"🔢 Update {pyproject_file} version to {new_version}")
        direct_branch.add(
            f"🏷️ Create and push tag: [bright_red]{tag_prefix}{new_version}[/bright_red]"
        )
        if auto_release:
            direct_branch.add("🎉 Create GitLab release")

    # Create git flow diagram
    git_tree = Tree(f"📊 [bold cyan]Git Flow Diagram[/bold cyan]")
    main_branch = git_tree.add(mr_target_branch)

    if create_mr:
        release_node = main_branch.add(f"[bright_red]{release_branch}[/bright_red]")
        release_node.add(f"📝 Update {changelog_file}")
        if pyproject_file:
            release_node.add(f"🔢 Update {pyproject_file}")
        release_node.add("💾 Commit release changes")

        main_branch.add(
            f"📋 MR: [bright_red]{release_branch}[/bright_red] → [bright_red]{mr_target_branch}[/bright_red]"
        )
        if auto_release:
            main_branch.add(
                f"🏷️ Tag: [bright_red]{tag_prefix}{new_version}[/bright_red]"
            )
            main_branch.add(
                f"🎉 Release: [bright_red]{tag_prefix}{new_version}[/bright_red]"
            )
        else:
            main_branch.add("⏳ Manual merge & tag")
    else:
        main_branch.add(f"📝 Update {changelog_file}")
        if pyproject_file:
            main_branch.add(f"🔢 Update {pyproject_file}")
        main_branch.add(f"🏷️ Tag: [bright_red]{tag_prefix}{new_version}[/bright_red]")
        if auto_release:
            main_branch.add(
                f"🎉 Release: [bright_red]{tag_prefix}{new_version}[/bright_red]"
            )
        else:
            main_branch.add("📤 Ready for manual release")

    # Display everything
    main_panel = Panel(
        state_panel,
        title="🔍 DRY RUN - Git Workflow Visualization",
        style="yellow",
        padding=(1, 2),
    )

    console.print(main_panel)
    console.print()
    console.print(workflow_tree)
    console.print()
    console.print(git_tree)
    console.print()

    # Status message
    if auto_release:
        console.print("⚡ [yellow]Auto-release mode: Full automation enabled[/yellow]")
    elif create_mr:
        console.print(
            "🔄 [yellow]MR mode: Manual review required before release[/yellow]"
        )
    else:
        console.print(
            "📋 [yellow]Manual mode: Review changes before continuing[/yellow]"
        )

    console.print()


def display_git_workflow_visualization(
    new_version: str,
    release_branch: str,
    create_mr: bool,
    auto_release: bool,
    mr_target_branch: str,
    changelog_file: str,
    pyproject_file: str,
    tag_prefix: str = "v",
    dry_run: bool = False,
):
    """Display a visual representation of the git workflow in dry-run mode."""

    # Only show visualization in dry-run mode
    if not dry_run:
        return

    # Use rich for better visualization
    _display_rich_workflow_visualization(
        new_version,
        release_branch,
        create_mr,
        auto_release,
        mr_target_branch,
        changelog_file,
        pyproject_file,
        tag_prefix,
    )
