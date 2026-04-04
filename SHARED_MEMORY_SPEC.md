# Shared Log-Based Memory System Specification

## Overview

This specification defines a new shared memory system for the Discord bot that replaces the current per-user memory model with a unified, log-based approach per guild (server). All chat history is stored in daily log files that are shared across the guild, with automatic compression when logs become too large.

---

## 1. New Directory Structure

### Current Structure (to be replaced)
```
memory/
├── users/
│   └── {user_id}/
│       ├── MEMORY.md          # Long-term user memory
│       ├── USER.md            # User-specific data
│       └── logs/
│           └── YYYY-MM-DD.md  # Daily logs per user
└── guilds/
    └── {guild_id}/
        └── MEMORY.md          # Guild memory (rarely used)
```

### New Structure
```
memory/
├── guilds/
│   └── {guild_id}/
│       ├── MEMORY.md          # Long-term guild facts (flushed from logs)
│       └── logs/
│           ├── YYYY-MM-DD.md      # Daily log (active)
│           ├── YYYY-MM-DD.raw.md  # Backup before compression
│           └── ...
```

### Key Changes
- **Single shared memory location per guild** - No user-specific memory directories
- **All chat history stored at guild level** - Every message in the guild gets logged
- **Daily log files** - One file per day in `memory/guilds/{guild_id}/logs/`
- **User separation via log entries** - User info stored in each message entry

---

## 2. Log Format

### Daily Log File Structure
```markdown
## 2026-04-03

### [14:23] #general
| user_id | username | display_name | is_bot |
|---------|----------|--------------|--------|
| 220740556496699394 | user#1234 | JohnDoe | false |

**JohnDoe**: Hello, how are you?

**Bot**: I'm doing great! How can I help you today?

---

### [14:25] #general
| user_id | username | display_name | is_bot |
|---------|----------|--------------|--------|
| 264727115558027264 | bot#0000 | Assistant | true |

**JohnDoe**: What's the weather like?

**Assistant**: I don't have access to weather data, but you could check a weather app!

---

### [14:30] #random
| user_id | username | display_name | is_bot |
|---------|----------|--------------|--------|
| 230231309073514496 | user#5678 | JaneSmith | false |

**JaneSmith**: Anyone want to play a game?

```

### Format Specifications
- **Header**: `## YYYY-MM-DD` - Date separator for the log file
- **Exchange Block**: `### [HH:MM] #channel_name` - Timestamp and channel
- **Metadata Table**: User info (user_id, username, display_name, is_bot)
- **Message Content**: 
  - User messages: `**display_name**: message content`
  - Bot messages: `**display_name**: message content` (is_bot=true)
- **Separator**: `---` - Clear separation between exchanges

### Example Log Entry (Compact Form)
```markdown
### [14:23] #general
- **JohnDoe** (220740556496699394): Hello, how are you?
- **Bot** (264727115558027264) [bot]: I'm doing great!

---
```

---

## 3. Memory Operations

### Core Functions

#### `append_to_log(guild_id, channel_id, user_id, username, message, is_bot=False)`

Adds a message to today's log file for the specified guild.

```python
import datetime
import os
from typing import Optional

import config

def get_guild_log_path(guild_id: str, date: datetime.date) -> str:
    """Get path to guild's log file for a specific date."""
    return os.path.join(
        config.MEMORY_BASE_PATH,
        "guilds",
        str(guild_id),
        "logs",
        date.strftime("%Y-%m-%d") + ".md"
    )


def append_to_log(
    guild_id: str,
    channel_id: str,
    channel_name: str,
    user_id: str,
    username: str,
    display_name: str,
    message: str,
    is_bot: bool = False
) -> None:
    """
    Append a message to today's log for the guild.
    
    Args:
        guild_id: Discord guild (server) ID
        channel_id: Discord channel ID
        channel_name: Discord channel name (e.g., "general")
        user_id: Discord user ID
        username: User's Discord username (user#1234)
        display_name: User's display name in the guild
        message: The message content
        is_bot: Whether this message is from a bot
    """
    date = datetime.date.today()
    path = get_guild_log_path(str(guild_id), date)
    
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        file_exists = os.path.exists(path)
        
        with open(path, "a", encoding="utf-8") as f:
            # Write date header if new file
            if not file_exists:
                f.write(f"## {date.strftime('%Y-%m-%d')}\n\n")
            
            # Write exchange header with timestamp
            now = datetime.datetime.now().strftime("%H:%M")
            f.write(f"### [{now}] #{channel_name}\n")
            
            # Write metadata
            bot_marker = " [bot]" if is_bot else ""
            f.write(f"- **{display_name}** ({user_id}){bot_marker}: {message}\n")
            
            # Write separator
            f.write("\n---\n\n")
            
    except Exception as e:
        logger.error(f"Error appending to log {path}: {e}")
```

#### `get_recent_log(guild_id, max_lines=None)`

Retrieves the most recent log file for context. This is the primary function for loading context into prompts.

```python
def get_recent_log(guild_id: str, max_lines: Optional[int] = None) -> str:
    """
    Get the most recent log file for a guild.
    
    Args:
        guild_id: Discord guild ID
        max_lines: Optional limit on lines to return (for token management)
    
    Returns:
        The log content as a string, or empty string if no log exists
    """
    today = datetime.date.today()
    path = get_guild_log_path(str(guild_id), today)
    
    # If today's log doesn't exist, try yesterday
    if not os.path.exists(path):
        yesterday = today - datetime.timedelta(days=1)
        path = get_guild_log_path(str(guild_id), yesterday)
    
    if not os.path.exists(path):
        return ""
    
    try:
        with open(path, "r", encoding="utf-8") as f:
            if max_lines:
                lines = []
                for line in f:
                    if len(lines) >= max_lines:
                        break
                    lines.append(line)
                return "".join(lines)
            return f.read()
    except Exception as e:
        logger.error(f"Error reading log {path}: {e}")
        return ""
```

#### `compress_log_if_needed(guild_id, threshold=None)`

Compresses the log when it exceeds the threshold number of exchanges. Uses LLM to summarize and stores the original as a backup.

```python
import shutil
from llm_client import summarize  # Lazy import to avoid circular dependency


def count_exchanges_in_log(guild_id: str, date: datetime.date) -> int:
    """Count the number of exchanges in a log file."""
    path = get_guild_log_path(str(guild_id), date)
    try:
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
            # Count "### [" patterns (exchange headers)
            return len(re.findall(r"^### \[", content, re.MULTILINE))
    except FileNotFoundError:
        return 0
    except Exception as e:
        logger.error(f"Error counting exchanges in {path}: {e}")
        return 0


async def compress_log_if_needed(
    guild_id: str,
    threshold: Optional[int] = None
) -> bool:
    """
    Compress today's log if it exceeds the threshold.
    
    Args:
        guild_id: Discord guild ID
        threshold: Number of exchanges before compression (default from config)
    
    Returns:
        True if compression was performed, False otherwise
    """
    if threshold is None:
        threshold = config.LOG_COMPRESSION_THRESHOLD
    
    date = datetime.date.today()
    exchange_count = count_exchanges_in_log(str(guild_id), date)
    
    if exchange_count <= threshold:
        return False
    
    path = get_guild_log_path(str(guild_id), date)
    
    try:
        # Read current log content
        with open(path, "r", encoding="utf-8") as f:
            log_content = f.read()
        
        if not log_content:
            return False
        
        # Create backup
        backup_path = path.replace(".md", ".raw.md")
        shutil.copy2(path, backup_path)
        logger.info(f"Created backup at {backup_path}")
        
        # Generate summary using LLM
        summary = await summarize(log_content)
        
        # Write compressed summary
        with open(path, "w", encoding="utf-8") as f:
            f.write(f"## {date.strftime('%Y-%m-%d')} (Summarized)\n\n")
            f.write("### Compressed Summary\n\n")
            f.write(summary)
            f.write("\n\n### Original Exchange Count\n")
            f.write(f"- Total exchanges: {exchange_count}\n")
            f.write(f"- Full log backed up to: {os.path.basename(backup_path)}\n")
        
        logger.info(f"Compressed log for guild {guild_id}: {exchange_count} -> summary")
        return True
        
    except Exception as e:
        logger.error(f"Error compressing log for guild {guild_id}: {e}")
        return False
```

#### `get_log_for_date(guild_id, date)`

Retrieves a specific day's log file for debugging or historical analysis.

```python
def get_log_for_date(guild_id: str, date: datetime.date) -> str:
    """
    Get the log file for a specific date.
    
    Args:
        guild_id: Discord guild ID
        date: The date to retrieve
    
    Returns:
        The log content as a string, or empty string if not found
    """
    path = get_guild_log_path(str(guild_id), date)
    
    if not os.path.exists(path):
        logger.warning(f"Log not found for guild {guild_id} on {date}")
        return ""
    
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        logger.error(f"Error reading log {path}: {e}")
        return ""
```

---

## 4. Compression Strategy

### When to Compress
- **Threshold**: Default 100 exchanges per day (configurable via `LOG_COMPRESSION_THRESHOLD`)
- **Trigger**: Checked after each message append
- **Frequency**: At most once per day per guild

### Compression Process
1. **Count exchanges** in today's log
2. **If exceeds threshold**:
   - Create backup: `YYYY-MM-DD.md` → `YYYY-MM-DD.raw.md`
   - Read full log content
   - Call LLM `summarize()` function with full content
   - Write summary to `YYYY-MM-DD.md`
   - Add metadata: exchange count, backup reference

### LLM Summary Prompt
```python
SUMMARY_PROMPT = """Summarize this Discord chat log, preserving key information:
- Important facts mentioned by users
- Decisions or agreements made
- Topics discussed
- Any actionable items
- User preferences or interests

Keep the summary concise but informative. Use bullet points.

Chat Log:
{log_content}

Summary:"""
```

### Backup File Format
Original logs are preserved as `.raw.md` files for potential recovery:
```markdown
## 2026-04-03 (Compressed)

### Compressed Summary
- JohnDoe asked about the weather
- Discussion about weekend plans
- JaneSmith shared a link to a game

### Original Exchange Count
- Total exchanges: 127
- Full log backed up to: 2026-04-03.raw.md
```

---

## 5. Context Loading

### Primary Context Function
```python
def load_context_for_prompt(guild_id: str) -> str:
    """
    Load the most recent log for context injection into prompts.
    
    This is the main function called when preparing prompts for the LLM.
    
    Args:
        guild_id: Discord guild ID
    
    Returns:
        Formatted context string for prompt injection
    """
    log_content = get_recent_log(str(guild_id))
    
    if not log_content:
        return "No recent conversation history available."
    
    # Check if log is compressed
    is_compressed = "(Summarized)" in log_content
    
    context_header = "## Recent Conversation Context\n\n"
    
    if is_compressed:
        context_header += "⚠️ *This is a compressed summary of earlier conversations*\n\n"
    
    return context_header + log_content
```

### Prompt Injection Format
```python
SYSTEM_PROMPT_TEMPLATE = """You are a helpful Discord bot.

{context}

Current conversation:
{user_message}

Your response:"""
```

### Context Loading Rules
1. **Always use today's log first** - Most relevant for ongoing conversations
2. **Fall back to yesterday** - If today's log doesn't exist
3. **Handle compressed logs** - Load summary if log is compressed
4. **Limit context size** - Use `max_lines` parameter for token management

---

## 6. Manual Memory (MEMORY.md)

### Overview

In addition to the automatic daily log system, each guild can have a manually-editable `MEMORY.md` file that stores persistent knowledge. This file is:

- **Manually edited** by users/admins (not auto-generated)
- **Persists across days** - Not compressed or cleared automatically
- **Loaded alongside daily logs** for context in prompts
- Located at `memory/guilds/{guild_id}/MEMORY.md`

### Example MEMORY.md Format

```markdown
# Server Memory

## Persistent Knowledge
- Bot prefix: !
- This server uses Vietnamese language
- Popular games: Uno, Chess

## Custom Commands
- !aura - Check aura points
- !rules - Show server rules
```

### Core Functions

#### `get_manual_memory_path(guild_id)`

```python
def get_manual_memory_path(guild_id: str) -> str:
    """Get path to guild's manual MEMORY.md file."""
    return os.path.join(
        config.MEMORY_BASE_PATH,
        "guilds",
        str(guild_id),
        "MEMORY.md"
    )
```

#### `load_manual_memory(guild_id)`

```python
def load_manual_memory(guild_id: str) -> str:
    """
    Load the manually-edited MEMORY.md file for a guild.
    
    Args:
        guild_id: Discord guild ID
    
    Returns:
        The MEMORY.md content as a string, or empty string if not found
    """
    path = get_manual_memory_path(str(guild_id))
    
    if not os.path.exists(path):
        return ""
    
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        logger.error(f"Error reading manual memory {path}: {e}")
        return ""
```

#### `save_manual_memory(guild_id, content)`

```python
def save_manual_memory(guild_id: str, content: str) -> bool:
    """
    Save manually edited content to MEMORY.md file.
    
    Args:
        guild_id: Discord guild ID
        content: The full content to save to MEMORY.md
    
    Returns:
        True if successful, False otherwise
    """
    path = get_manual_memory_path(str(guild_id))
    
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        logger.info(f"Saved manual memory for guild {guild_id}")
        return True
    except Exception as e:
        logger.error(f"Error saving manual memory {path}: {e}")
        return False
```

#### `append_to_manual_memory(guild_id, fact)`

```python
def append_to_manual_memory(guild_id: str, fact: str, category: str = "General") -> bool:
    """
    Add a new fact to the manual MEMORY.md file.
    
    Args:
        guild_id: Discord guild ID
        fact: The fact to add
        category: Optional category header to add under (default: "General")
    
    Returns:
        True if successful, False otherwise
    """
    path = get_manual_memory_path(str(guild_id))
    
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        
        # Read existing content or create new file
        existing_content = ""
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                existing_content = f.read()
        
        # Build new content
        if not existing_content:
            # Create new file with header
            new_content = f"""# Server Memory

## {category}
- {fact}
"""
        else:
            # Check if category exists and append to it
            category_header = f"## {category}"
            if category_header in existing_content:
                # Find the category section and append
                lines = existing_content.split('\n')
                new_lines = []
                in_category = False
                for line in lines:
                    new_lines.append(line)
                    if line.strip() == category_header:
                        in_category = True
                    elif in_category and line.startswith("## "):
                        # Reached next section, add fact before it
                        new_lines.insert(-1, f"- {fact}")
                        in_category = False
                    elif in_category and line.strip() and not line.startswith("-"):
                        # Reached content after bullets, insert before
                        new_lines.insert(-1, f"- {fact}")
                        in_category = False
                
                # If still in category at end of file
                if in_category:
                    new_lines.append(f"- {fact}")
                
                existing_content = '\n'.join(new_lines)
            else:
                # Add new category section
                existing_content += f"\n\n{category_header}\n- {fact}\n"
        
        with open(path, "w", encoding="utf-8") as f:
            f.write(existing_content)
        
        logger.info(f"Appended fact to manual memory for guild {guild_id}")
        return True
        
    except Exception as e:
        logger.error(f"Error appending to manual memory {path}: {e}")
        return False
```

### Updated Context Loading

The `load_context_for_prompt()` function now returns both the manual MEMORY.md content and today's log:

```python
def load_context_for_prompt(guild_id: str) -> dict:
    """
    Load context for prompt injection - both manual memory and recent log.
    
    Args:
        guild_id: Discord guild ID
    
    Returns:
        Dictionary with 'manual_memory' and 'daily_log' keys
    """
    # Load manual memory (persistent knowledge)
    manual_memory = load_manual_memory(str(guild_id))
    
    # Load today's log (recent conversation)
    daily_log = get_recent_log(str(guild_id))
    
    return {
        "manual_memory": manual_memory,
        "daily_log": daily_log
    }


def format_context_for_prompt(guild_id: str) -> str:
    """
    Format context for prompt injection.
    
    Args:
        guild_id: Discord guild ID
    
    Returns:
        Formatted context string for prompt injection
    """
    context = load_context_for_prompt(str(guild_id))
    
    parts = []
    
    # Add manual memory if exists
    if context["manual_memory"]:
        parts.append("## Persistent Knowledge (Manual Memory)\n\n")
        parts.append(context["manual_memory"])
        parts.append("\n\n")
    
    # Add daily log if exists
    if context["daily_log"]:
        is_compressed = "(Summarized)" in context["daily_log"]
        
        parts.append("## Recent Conversation\n\n")
        
        if is_compressed:
            parts.append("⚠️ *This is a compressed summary of earlier conversations*\n\n")
        
        parts.append(context["daily_log"])
    
    if not parts:
        return "No conversation history available."
    
    return "".join(parts)
```

### Context Loading Rules (Updated)

1. **Manual memory first** - Persistent knowledge from MEMORY.md
2. **Daily log second** - Recent conversation from today's log
3. **Fallback to yesterday** - If today's log doesn't exist
4. **Handle compressed logs** - Load summary if log is compressed
5. **Separate concerns** - Manual memory for facts, logs for context

### Integration with Bot

```python
async def on_message(message: discord.Message):
    # Skip bot messages to avoid loops
    if message.author.bot:
        return
    
    # ... existing log append code ...
    
    # Check if user is admin for manual memory commands
    if is_admin(message.author):
        await handle_manual_memory_command(message)


async def handle_manual_memory_command(message: discord.Message):
    """Handle commands to edit MEMORY.md"""
    # !memory add <fact> - Add a fact to MEMORY.md
    # !memory edit - Open MEMORY.md for editing
    # !memory show - Show current MEMORY.md content
    pass
```

---

## 7. Configuration

### New Config Options (config.py)

```python
# Memory - Log-based shared memory
MEMORY_DIR = "memory"
MEMORY_BASE_PATH = os.getenv("MEMORY_BASE_PATH", "./memory")

# Log compression threshold (number of exchanges before compression)
LOG_COMPRESSION_THRESHOLD = int(os.getenv("LOG_COMPRESSION_THRESHOLD", "100"))

# Memory flush threshold (number of exchanges before extracting facts to MEMORY.md)
MEMORY_FLUSH_THRESHOLD = int(os.getenv("MEMORY_FLUSH_THRESHOLD", "200"))

# Maximum lines to load for context (None = unlimited)
LOG_CONTEXT_MAX_LINES = int(os.getenv("LOG_CONTEXT_MAX_LINES", "500"))

# Search
MEMORY_SEARCH_TOP_K = int(os.getenv("MEMORY_SEARCH_TOP_K", "5"))
```

### Environment Variables
| Variable | Default | Description |
|----------|---------|-------------|
| `LOG_COMPRESSION_THRESHOLD` | 100 | Exchanges before log compression |
| `LOG_CONTEXT_MAX_LINES` | 500 | Max lines to load for context |
| `MEMORY_FLUSH_THRESHOLD` | 200 | Exchanges before flushing facts to MEMORY.md |

---

## 9. Migration from Current System

### Phase 1: Parallel Operation
- Implement new functions alongside existing ones
- Both systems can operate simultaneously

### Phase 2: Data Migration
- Move existing guild data to new structure
- Convert user logs to guild logs (optional)
- Update references in code

### Phase 3: Full Migration
- Remove old per-user memory functions
- Update all bot code to use new functions
- Clean up old directory structure

### Migration Script Example
```python
#!/usr/bin/env python3
"""Migration script to convert from per-user to shared guild memory."""

import os
import shutil
from pathlib import Path

OLD_BASE = Path("./memory/users")
NEW_BASE = Path("./memory/guilds")

def migrate_user_to_guild(user_id: str, guild_id: str):
    """Migrate a user's log files to guild structure."""
    user_dir = OLD_BASE / user_id
    guild_dir = NEW_BASE / guild_id / "logs"
    
    if not user_dir.exists():
        return
    
    # Create guild directory
    guild_dir.mkdir(parents=True, exist_ok=True)
    
    # Copy log files
    logs_dir = user_dir / "logs"
    if logs_dir.exists():
        for log_file in logs_dir.glob("*.md"):
            if ".raw" not in log_file.name:  # Skip backups
                dest = guild_dir / log_file.name
                shutil.copy2(log_file, dest)
                print(f"Copied {log_file} -> {dest}")
    
    # Copy MEMORY.md if exists
    memory_file = user_dir / "MEMORY.md"
    if memory_file.exists():
        dest = NEW_BASE / guild_id / "MEMORY.md"
        shutil.copy2(memory_file, dest)
        print(f"Copied {memory_file} -> {dest}")

# Example usage
# migrate_user_to_guild("220740556496699394", "265095242578001922")
```

---

## 10. Integration with Bot

### Message Handler Integration
```python
async def on_message(message: discord.Message):
    # Skip bot messages to avoid loops
    if message.author.bot:
        return
    
    # Append user message to log
    memory_manager.append_to_log(
        guild_id=str(message.guild.id),
        channel_id=str(message.channel.id),
        channel_name=message.channel.name,
        user_id=str(message.author.id),
        username=str(message.author),
        display_name=message.author.display_name,
        message=message.content,
        is_bot=False
    )
    
    # Process message and get bot response
    response = await process_message(message)
    
    if response:
        # Append bot response to log
        memory_manager.append_to_log(
            guild_id=str(message.guild.id),
            channel_id=str(message.channel.id),
            channel_name=message.channel.name,
            user_id=str(message.author.id),  # Use bot's ID or system ID
            username=str(message.author),    # Bot username
            display_name=message.author.display_name,
            message=response,
            is_bot=True
        )
        
        # Check if compression is needed
        await memory_manager.compress_log_if_needed(str(message.guild.id))
```

### Context Loading for LLM
```python
async def get_bot_response(guild_id: str, user_message: str) -> str:
    # Load recent conversation context
    context = memory_manager.load_context_for_prompt(guild_id)
    
    # Build prompt
    prompt = f"""You are a helpful Discord bot.

{context}

Current message: {user_message}

Your response:"""
    
    # Get LLM response
    response = await llm_client.chat(prompt)
    return response
```

---

## 11. Error Handling

### Logging
- All operations should log errors with appropriate context
- Use Python's `logging` module consistently

### Edge Cases
1. **Missing guild directory**: Create automatically on first write
2. **Corrupted log file**: Attempt recovery from `.raw.md` backup
3. **LLM summarization failure**: Keep original log, log error
4. **Disk full**: Graceful degradation, skip logging

### Recovery Procedure
```python
def recover_from_backup(guild_id: str, date: datetime.date) -> bool:
    """Attempt to recover a log from its backup file."""
    log_path = get_guild_log_path(str(guild_id), date)
    backup_path = log_path.replace(".md", ".raw.md")
    
    if not os.path.exists(backup_path):
        return False
    
    try:
        shutil.copy2(backup_path, log_path)
        logger.info(f"Recovered {log_path} from backup")
        return True
    except Exception as e:
        logger.error(f"Failed to recover {log_path}: {e}")
        return False
```

---

## 12. Summary

This specification provides a complete design for a shared, log-based memory system that:

| Feature | Description |
|---------|-------------|
| **Unified Storage** | Single memory location per guild instead of per-user |
| **Daily Logs** | One log file per day in `memory/guilds/{guild_id}/logs/YYYY-MM-DD.md` |
| **Shared Context** | All users in a guild share the same conversation history |
| **Automatic Compression** | Logs are summarized when they exceed threshold (default 100 exchanges) |
| **Backup System** | Original logs preserved as `.raw.md` files |
| **Simple Context Loading** | Load only today's log (or yesterday's if today doesn't exist) |
| **Manual Memory (MEMORY.md)** | Manually-editable persistent knowledge file per guild |

The system is designed to be:
- **Simple**: Easy to understand and maintain
- **Efficient**: Only loads relevant context
- **Scalable**: Handles large servers with many messages
- **Robust**: Includes backup and recovery options
- **Flexible**: Supports both automatic logging and manual memory editing