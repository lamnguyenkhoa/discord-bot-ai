"""Utility slash commands."""

import logging
import discord
from discord import app_commands

logger = logging.getLogger(__name__)


@app_commands.command(name="userid", description="Get user ID by name")
@app_commands.describe(name="Username to search for")
async def userid_command(interaction: discord.Interaction, name: str):
    """Look up a user ID by name within the server."""
    guild = interaction.guild
    if not guild:
        await interaction.response.send_message("This command only works in servers.", ephemeral=True)
        return

    await interaction.response.defer()

    members = await guild.fetch_members()
    name_lower = name.lower()
    matches = [m for m in members if name_lower in m.display_name.lower() or name_lower in m.name.lower()]

    if not matches:
        await interaction.followup.send(f"No user found matching '{name}'", ephemeral=True)
        return

    match = matches[0]
    await interaction.followup.send(f"**{match.display_name}**\nID: `{match.id}`\nMention: {match.mention}", ephemeral=True)
