from __future__ import annotations

import argparse

from .console import console


def main():
    """
    Main function to parse arguments and print the greeting.
    """
    # Create the parser
    parser = argparse.ArgumentParser(
        description="A simple CLI tool to print 'Hello, World!' with an optional fun mode.",
    )

    # Add the optional --fun argument
    parser.add_argument(
        "-f",
        "--fun",
        action="store_true",  # This makes it a boolean flag
        help="Print a fun and enthusiastic greeting!",
    )

    # Parse the arguments
    args = parser.parse_args()

    # Check if the fun flag was used
    if args.fun:
        console.print("🎉 [bold magenta]Hello, Fabulous World![/bold magenta] [yellow]Hope you're having an amazing day![/yellow] 🌟")
    else:
        console.print("[bold blue]Hello, World![/bold blue]")


if __name__ == "__main__":
    main()
