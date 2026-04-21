"""Utility commands module for Discord bot."""

from discord import app_commands

from .commands import userid_command


def load(tree: app_commands.CommandTree) -> None:
    """Register utility commands to the command tree."""
    tree.add_command(userid_command)
