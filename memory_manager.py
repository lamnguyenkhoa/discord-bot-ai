"""
Shared Memory Manager - Unified per-guild log-based memory system.

Directory structure:
    memory/guilds/{guild_id}/
    ├── MEMORY.md          # Manually editable persistent memory
    └── logs/
        ├── YYYY-MM-DD.md      # Daily conversation log
        └── YYYY-MM-DD.raw.md  # Backup before compression

All users in a guild share the same log file - no per-user separation.
"""

import datetime
import os
import logging
import re
import shutil

import config

logger = logging.getLogger(__name__)

# Global flag to disable all log writes; now controlled via environment variable


# --- Legacy compatibility functions ---

def append_exchange(
    user_id: str,
    guild_id: str | None,
    channel_name: str,
    author_name: str,
    user_message: str,
    bot_reply: str,
) -> None:
    """
    Legacy function for backward compatibility.
    
    Appends to the unified guild log (not user-specific).
    """
    if not guild_id:
        logger.warning("append_exchange called without guild_id")
        return
    
    # Determine if this is a bot message
    is_bot = bool(bot_reply)
    
    append_to_log(
        guild_id=guild_id,
        channel_id="",
        channel_name=channel_name,
        user_id=user_id,
        username=author_name,
        message=user_message if not bot_reply else bot_reply,
        is_bot=is_bot,
    )


# --- Path helpers ---

def _guild_dir(guild_id: str) -> str:
    """Get the guild's memory directory."""
    return os.path.join(config.MEMORY_BASE_PATH, "guilds", str(guild_id))


def _guild_logs_dir(guild_id: str) -> str:
    """Get the guild's logs directory."""
    return os.path.join(_guild_dir(guild_id), "logs")


def get_guild_log_path(guild_id: str, date: datetime.date) -> str:
    """Get path to a specific day's log file."""
    return os.path.join(_guild_logs_dir(guild_id), date.strftime("%Y-%m-%d") + ".md")


def get_guild_memory_path(guild_id: str) -> str:
    """Get path to the guild's manual MEMORY.md file."""
    return os.path.join(_guild_dir(guild_id), "MEMORY.md")


# --- Log operations ---

def load_guild_log(guild_id: str, date: datetime.date) -> str:
    if config.LOGGING_DISABLED:
        return ""
    """Load a specific day's log content."""
    path = get_guild_log_path(guild_id, date)
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return ""
    except Exception as e:
        logger.error(f"Error reading log {path}: {e}")
        return ""


def get_recent_log(guild_id: str, max_lines: int | None = None) -> str:
    if config.LOGGING_DISABLED:
        return ""
    """
    Get the most recent log for context.
    
    Args:
        guild_id: The Discord guild ID
        max_lines: Optional limit on lines to return (for context size control)
    
    Returns:
        The most recent log content, or empty string if none exists.
    """
    today = datetime.date.today()
    
    # Try today's log first
    log = load_guild_log(guild_id, today)
    if log:
        if max_lines:
            lines = log.split('\n')
            return '\n'.join(lines[-max_lines:])
        return log
    
    # Fall back to yesterday if today's log is empty
    yesterday = today - datetime.timedelta(days=1)
    log = load_guild_log(guild_id, yesterday)
    if log:
        if max_lines:
            lines = log.split('\n')
            return '\n'.join(lines[-max_lines:])
        return log
    
    return ""


def append_to_log(
    guild_id: str,
    channel_id: str,
    channel_name: str,
    user_id: str,
    username: str,
    message: str,
    is_bot: bool = False,
) -> None:
    if config.LOGGING_DISABLED:
        return
    """
    Append a message to today's log.
    
    All users in the guild share the same log file.
    
    Format:
        ### 2026-04-03T10:30:45 | #channel_name | username
        **username**: message content
        
        ---
    """
    date = datetime.date.today()
    path = get_guild_log_path(guild_id, date)
    
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        file_exists = os.path.exists(path)
        
        timestamp = datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
        
        with open(path, "a", encoding="utf-8") as f:
            if not file_exists:
                f.write(f"# {date.strftime('%Y-%m-%d')} - {guild_id}\n\n")
            
            f.write(f"### {timestamp} | #{channel_name} | {username}\n")
            f.write(f"**{username}**: {message}\n")
            f.write("\n---\n\n")
            
    except Exception as e:
        logger.error(f"Error appending to log {path}: {e}")


def count_exchanges(guild_id: str, date: datetime.date) -> int:
    """Count the number of message exchanges in a log."""
    content = load_guild_log(guild_id, date)
    return len(re.findall(r"^### ", content, re.MULTILINE))


# --- Compression ---

async def compress_log_if_needed(guild_id: str) -> None:
    if config.LOGGING_DISABLED:
        return
    """
    Compress today's log if it exceeds the threshold.
    
    When the log has more than LOG_COMPRESSION_THRESHOLD exchanges,
    summarize it using the LLM and replace the original.
    """
    date = datetime.date.today()
    threshold = getattr(config, 'LOG_COMPRESSION_THRESHOLD', 100)
    
    try:
        if count_exchanges(guild_id, date) > threshold:
            path = get_guild_log_path(guild_id, date)
            log_content = load_guild_log(guild_id, date)
            
            if not log_content:
                return
            
            # Check if already summarized
            if "(Summarized)" in log_content:
                return
            
            # Backup original
            backup_path = path.replace(".md", ".raw.md")
            shutil.copy2(path, backup_path)
            logger.info(f"Backed up log to {backup_path}")
            
            # Summarize
            from llm_client import summarize
            summary = await summarize(log_content)
            
            # Write summarized version
            with open(path, "w", encoding="utf-8") as f:
                f.write(f"# {date.strftime('%Y-%m-%d')} - {guild_id} (Summarized)\n\n")
                f.write(summary)
                f.write("\n\n---\n*This log has been compressed. See .raw.md for original.*\n")
            
            logger.info(f"Compressed log for guild {guild_id}, date {date}")
            
    except Exception as e:
        logger.error(f"Error during compress_log_if_needed for guild {guild_id}: {e}")


# --- Manual Memory (MEMORY.md) ---

def load_manual_memory(guild_id: str) -> str:
    """
    Load the manually editable MEMORY.md for a guild.
    
    This file is for persistent knowledge that should not be lost
    across days or compressed. Users/admins can manually edit it.
    """
    path = get_guild_memory_path(guild_id)
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return ""
    except Exception as e:
        logger.error(f"Error reading manual memory {path}: {e}")
        return ""


def save_manual_memory(guild_id: str, content: str) -> None:
    """Save content to the guild's manual MEMORY.md file."""
    path = get_guild_memory_path(guild_id)
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
    except Exception as e:
        logger.error(f"Error saving manual memory {path}: {e}")


def append_to_manual_memory(guild_id: str, fact: str) -> None:
    """
    Append a new fact to the guild's manual MEMORY.md.
    
    Creates the file with a default header if it doesn't exist.
    """
    path = get_guild_memory_path(guild_id)
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        
        # Check if file exists and has content
        existing = ""
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                existing = f.read().strip()
        
        # Build new content
        if existing:
            # Append to existing
            new_content = existing + "\n- " + fact
        else:
            # Create new with header
            new_content = "# Server Memory\n\n- " + fact
        
        with open(path, "w", encoding="utf-8") as f:
            f.write(new_content)
            
    except Exception as e:
        logger.error(f"Error appending to manual memory {path}: {e}")


# --- Context loading for prompts ---

def load_context_for_prompt(guild_id: str) -> dict:
    """
    Load all context needed for prompt injection.
    
    Returns a dict with:
        - manual_memory: The manually editable MEMORY.md content
        - daily_log: Today's conversation log
        - is_summarized: Whether the log is a compressed summary
    """
    manual_memory = load_manual_memory(guild_id)
    daily_log = get_recent_log(guild_id)
    
    # Check if log is summarized
    is_summarized = "(Summarized)" in daily_log
    
    return {
        "manual_memory": manual_memory,
        "daily_log": daily_log,
        "is_summarized": is_summarized,
    }


def format_context_for_prompt(guild_id: str) -> str:
    """
    Format context as a string for LLM prompt injection.
    
    Includes both manual memory and daily log.
    """
    context = load_context_for_prompt(guild_id)
    
    parts = []
    
    if context["manual_memory"]:
        parts.append(f"## Persistent Memory (Manual)\n{context['manual_memory']}")
    
    if context["daily_log"]:
        label = "Today's Conversation (Compressed)" if context["is_summarized"] else "Today's Conversation"
        parts.append(f"## {label}\n{context['daily_log']}")
    
    if not parts:
        return "No memory available yet."
    
    return "\n\n".join(parts)


