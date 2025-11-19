"""
Rich console utilities for enhanced terminal output.

This module provides a centralized console interface using the rich library
for better formatting, colors, and visual appeal throughout the releaser package.
"""

from typing import Optional, Any, Dict, List

from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.prompt import Confirm, Prompt
from rich.rule import Rule
from rich.table import Table
from rich.text import Text

# Global console instance
console = Console()
error_console = Console(stderr=True)


class RichLogger:
    """Logger-like interface using rich console for consistent styling."""

    def __init__(self, console_instance: Optional[Console] = None) -> None:
        self.console = console_instance or console

    def info(self, message: str, **kwargs: Any) -> None:
        """Log info message with blue color."""
        self.console.print(f"ℹ️  {message}", style="blue", **kwargs)

    def success(self, message: str, **kwargs: Any) -> None:
        """Log success message with green color."""
        self.console.print(f"✅ {message}", style="green", **kwargs)

    def warning(self, message: str, **kwargs: Any) -> None:
        """Log warning message with yellow color."""
        self.console.print(f"⚠️  {message}", style="yellow", **kwargs)

    def error(self, message: str, **kwargs: Any) -> None:
        """Log error message with red color."""
        error_console.print(f"❌ {message}", style="red bold", **kwargs)

    def debug(self, message: str, **kwargs: Any) -> None:
        """Log debug message with dim style."""
        self.console.print(f"🐛 {message}", style="dim", **kwargs)

    def highlight_value(self, value: str) -> Text:
        """Create highlighted text for important values."""
        return Text(value, style="bright_red bold")

    def print_header(self, title: str, subtitle: Optional[str] = None) -> None:
        """Print a formatted header."""
        if subtitle:
            header_text = f"[bold]{title}[/bold]\n[dim]{subtitle}[/dim]"
        else:
            header_text = f"[bold]{title}[/bold]"

        panel = Panel(header_text, style="blue", padding=(1, 2))
        self.console.print(panel)

    def print_rule(self, title: Optional[str] = None, style: str = "blue") -> None:
        """Print a horizontal rule with optional title."""
        self.console.print(Rule(title or "", style=style))

    def print_status(self, message: str, status: str = "info") -> None:
        """Print a status message with appropriate styling."""
        styles = {
            "info": "blue",
            "success": "green",
            "warning": "yellow",
            "error": "red bold",
        }
        icons = {"info": "ℹ️", "success": "✅", "warning": "⚠️", "error": "❌"}

        style = styles.get(status, "blue")
        icon = icons.get(status, "ℹ️")

        self.console.print(f"{icon} {message}", style=style)


class BorderedOutput:
    """Create bordered output similar to the existing table-like displays."""

    def __init__(self, console_instance: Optional[Console] = None) -> None:
        self.console = console_instance or console

    def create_bordered_content(
        self, content: str, title: str = "", dry_run: bool = False
    ) -> None:
        """Create a bordered panel with content."""
        if dry_run:
            header_text = "DRY RUN - " + title if title else "DRY RUN - PREVIEW"
            panel_style = "yellow"
        else:
            header_text = title or "PREVIEW"
            panel_style = "green"

        panel = Panel(
            content,
            title=header_text,
            title_align="left",
            style=panel_style,
            padding=(1, 2),
            expand=False,
        )
        self.console.print(panel)

    def create_table(
        self,
        title: str = "",
        headers: Optional[List[str]] = None,
        rows: Optional[List[List[object]]] = None,
        style: str = "blue",
    ) -> Table:
        """Create a rich table with styling."""
        table = Table(title=title, style=style, show_header=bool(headers))

        if headers:
            for header in headers:
                table.add_column(header, style="cyan")

        if rows:
            for row in rows:
                # Convert all items to strings
                str_row = [str(item) for item in row]
                table.add_row(*str_row)

        return table

    def print_table(
        self,
        title: str = "",
        headers: Optional[List[str]] = None,
        rows: Optional[List[List[object]]] = None,
        style: str = "blue",
    ) -> None:
        """Print a formatted table."""
        table = self.create_table(title, headers, rows, style)
        self.console.print(table)


def create_duplicate_commits_table(duplicates: Dict[str, List[List[str]]]) -> Table:
    """Create a table for displaying duplicate commits."""
    table = Table(
        title="⚠️ Duplicate Commit Messages Found",
        show_header=True,
        header_style="bold cyan",
    )

    table.add_column("Message", style="white", width=60)
    table.add_column("SHA", style="bright_red", width=10)
    table.add_column("Count", style="bright_red", width=8, justify="center")

    for message, commits in duplicates.items():
        # Truncate message if too long
        display_message = message[:57] + "..." if len(message) > 60 else message
        count = len(commits)

        # First row with message and count
        first_sha = commits[0][0][:8] if commits else ""
        table.add_row(display_message, first_sha, str(count))

        # Additional rows for other SHAs
        for sha, _ in commits[1:]:
            short_sha = sha[:8]
            table.add_row("", short_sha, "")

    return table


def prompt_confirmation(message: str, default: bool = False) -> bool:
    """Prompt for yes/no confirmation with rich styling."""
    return Confirm.ask(message, default=default)


def prompt_input(message: str, default: str = "") -> str:
    """Prompt for user input with rich styling."""
    return Prompt.ask(message, default=default)


def prompt_choice(
    message: str, choices: List[str], default: Optional[str] = None
) -> str:
    """Prompt for choice selection with numbered options.

    Args:
        message: The question to ask
        choices: List of choice strings
        default: Default choice (optional)

    Returns:
        The selected choice string
    """
    # Format choices with numbers
    numbered_choices = [f"{i+1}) {choice}" for i, choice in enumerate(choices)]

    # Display numbered options
    console.print()
    for numbered_choice in numbered_choices:
        console.print(f"  {numbered_choice}")
    console.print()

    # Create mapping from number strings to original choices
    number_to_choice = {str(i + 1): choice for i, choice in enumerate(choices)}

    # Also allow full text match
    valid_inputs = list(number_to_choice.keys()) + choices

    # Determine default display - show value in prompt, use number as default
    default_display = None
    prompt_text = message
    if default and default in choices:
        default_num = choices.index(default) + 1
        default_display = str(default_num)
        # Add default value name to the message
        prompt_text = f"{message} (default: {default})"

    # Prompt for input
    default_arg = default_display or ""
    response: str = Prompt.ask(
        prompt_text,
        choices=valid_inputs,
        default=default_arg,
        show_choices=False,  # We already showed them above
    )

    # Convert number input to choice text
    if response in number_to_choice:
        return str(number_to_choice[response])

    # If they typed the full text, return as-is
    return str(response)


def print_version_header() -> None:
    """Print the version header with rich formatting."""
    try:
        import pyfiglet

        ascii_art = pyfiglet.figlet_format("Releaser", font="ansi_shadow")
        console.print(ascii_art, style="bright_blue")
    except ImportError:
        console.print("🚀 [bold bright_blue]Releaser[/bold bright_blue]")


def create_progress_spinner(description: str = "Processing...") -> Progress:
    """Create a progress spinner for long-running operations."""
    return Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
        transient=True,
    )


# Create global instances
logger = RichLogger()
bordered = BorderedOutput()


# Compatibility functions for easy migration
def log_info(message: str, **kwargs: Any) -> None:
    """Compatibility function for log_info."""
    logger.info(message, **kwargs)


def log_success(message: str, **kwargs: Any) -> None:
    """Compatibility function for log_success."""
    logger.success(message, **kwargs)


def log_warning(message: str, **kwargs: Any) -> None:
    """Compatibility function for log_warning."""
    logger.warning(message, **kwargs)


def log_error(message: str, **kwargs: Any) -> None:
    """Compatibility function for log_error."""
    logger.error(message, **kwargs)


def highlight_value(value: str) -> Text:
    """Compatibility function for highlight_value."""
    return logger.highlight_value(value)


def print_rule(title: Optional[str] = None, style: str = "blue") -> None:
    """Compatibility function for print_rule."""
    logger.print_rule(title, style)


def print_status(message: str, status: str = "info") -> None:
    """Compatibility function for print_status."""
    logger.print_status(message, status)
