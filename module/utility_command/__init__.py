"""Utility commands module for Discord bot."""

from .commands import create_userid_command


def load(tree) -> None:
    """Register utility commands to the command tree."""
    print("Register utility command")
    create_userid_command(tree)
