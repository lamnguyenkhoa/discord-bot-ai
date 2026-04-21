# Utility Command Module Design

## Overview

Add a new `utility_command` module to provide slash commands for utility functions. Initial command: `/userid` to look up user IDs.

## Command: `/userid`

### Parameters
- `name` (string, required): Username to search for

### Behavior
- **Scope:** Guild-only (current server)
- **Matching:** Partial/fuzzy match against display name and username (case-insensitive)
- **Output:** User ID in format `<@user_id>` (mention) plus raw ID
- **Error:** "No user found matching '{name}'"

### Implementation

**module/utility_command/__init__.py**
```python
from .commands import userid_command

def load(tree):
    tree.add_command(userid_command)
```

**module/utility_command/commands.py**
```python
@app_commands.command(name="userid", description="Get user ID by name")
@app_commands.describe(name="Username to search for")
async def userid_command(interaction: discord.Interaction, name: str):
    guild = interaction.guild
    if not guild:
        await interaction.response.send_message("This command only works in servers.")
        return

    members = await guild.fetch_members().flatten()
    matches = [m for m in members if name.lower() in m.display_name.lower() or name.lower() in m.name.lower()]

    if not matches:
        await interaction.response.send_message(f"No user found matching '{name}'")
        return

    match = matches[0]
    await interaction.response.send_message(f"ID: {match.id}\nMention: {match.mention}")
```

**bot.py changes**
- Add: `from module.utility_command import load as load_utility_commands`
- After `tree = app_commands.CommandTree(bot)`: `load_utility_commands(tree)`

## Acceptance Criteria

1. `/userid <name>` returns user ID and mention for matching user
2. Shows helpful error if no user found
3. Works only in servers (not DMs)
