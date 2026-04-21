"""Utility slash commands."""

import logging
import discord

logger = logging.getLogger(__name__)


def create_userid_command(tree):
    @tree.command(name="get_userid_by_name", description="Get user ID by name")
    @discord.app_commands.describe(name="Username to search for")
    async def userid_command(interaction: discord.Interaction, name: str):
        """Look up a user ID by name within the server."""
        guild = interaction.guild
        if not guild:
            await interaction.response.send_message("This command only works in servers.", ephemeral=True)
            return

        await interaction.response.defer()

        matches = await guild.search_members(query=name)

        if not matches:
            await interaction.followup.send(f"No user found matching '{name}'", ephemeral=True)
            return

        match = matches[0]
        await interaction.followup.send(f"**{match.display_name}**\nID: `{match.id}`\nMention: {match.mention}", ephemeral=True)
