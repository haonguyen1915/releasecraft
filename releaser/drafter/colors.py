"""
ANSI color constants for terminal output formatting.

This module provides ANSI color codes for parts of the code that still use them.
Most output should use the rich console utilities instead.
"""


class Colors:
    """ANSI color codes for terminal output."""

    RED = "\033[0;31m"
    GREEN = "\033[0;32m"
    YELLOW = "\033[1;33m"
    BLUE = "\033[0;34m"
    BRIGHT_RED = "\033[1;31m"
    CYAN = "\033[0;36m"
    NC = "\033[0m"

    @staticmethod
    def red(text: str) -> str:
        """Return red colored text using rich markup."""
        return f"[red]{text}[/red]"

    @staticmethod
    def green(text: str) -> str:
        """Return green colored text using rich markup."""
        return f"[green]{text}[/green]"

    @staticmethod
    def yellow(text: str) -> str:
        """Return yellow colored text using rich markup."""
        return f"[yellow]{text}[/yellow]"

    @staticmethod
    def blue(text: str) -> str:
        """Return blue colored text using rich markup."""
        return f"[blue]{text}[/blue]"

    @staticmethod
    def bright_red(text: str) -> str:
        """Return bright red colored text using rich markup."""
        return f"[bright_red bold]{text}[/bright_red bold]"

    @staticmethod
    def cyan(text: str) -> str:
        """Return cyan colored text using rich markup."""
        return f"[cyan]{text}[/cyan]"
