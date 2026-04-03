import datetime
import logging
import os
import re
import shutil

import config

logger = logging.getLogger(__name__)


# --- Path helpers ---

def _user_dir(user_id: str) -> str:
    return os.path.join(config.MEMORY_BASE_PATH, "users", str(user_id))


def _guild_dir(guild_id: str) -> str:
    return os.path.join(config.MEMORY_BASE_PATH, "guilds", str(guild_id))


def get_user_log_path(user_id: str, date: datetime.date) -> str:
    return os.path.join(_user_dir(user_id), "logs", date.strftime("%Y-%m-%d") + ".md")


def get_user_memory_path(user_id: str) -> str:
    return os.path.join(_user_dir(user_id), "MEMORY.md")


def get_guild_memory_path(guild_id: str) -> str:
    return os.path.join(_guild_dir(guild_id), "MEMORY.md")


def get_all_user_files(user_id: str) -> list[str]:
    """Return all markdown file paths for a user (MEMORY.md, USER.md, and daily logs)."""
    user_dir = _user_dir(user_id)
    paths = []
    for filename in ("MEMORY.md", "USER.md"):
        p = os.path.join(user_dir, filename)
        if os.path.exists(p):
            paths.append(p)
    logs_dir = os.path.join(user_dir, "logs")
    if os.path.isdir(logs_dir):
        for f in sorted(os.listdir(logs_dir)):
            if f.endswith(".md") and not f.endswith(".raw.md"):
                paths.append(os.path.join(logs_dir, f))
    return paths


# --- Log read/write ---

def load_user_log(user_id: str, date: datetime.date) -> str:
    path = get_user_log_path(user_id, date)
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return ""
    except Exception as e:
        logger.error(f"Error reading log {path}: {e}")
        return ""


def append_exchange(
    user_id: str,
    guild_id: str | None,
    channel_name: str,
    author_name: str,
    user_message: str,
    bot_reply: str,
) -> None:
    date = datetime.date.today()
    path = get_user_log_path(user_id, date)
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        file_exists = os.path.exists(path)
        with open(path, "a", encoding="utf-8") as f:
            if not file_exists:
                f.write(f"## {date.strftime('%Y-%m-%d')}\n")
            now = datetime.datetime.now().strftime("%H:%M")
            f.write(f"### [{now}] #{channel_name}\n")
            f.write(f"User ({author_name}): {user_message}\n")
            if bot_reply:
                f.write(f"Bot: {bot_reply}\n")
            f.write("\n")
    except Exception as e:
        logger.error(f"Error appending exchange to {path}: {e}")


def count_exchanges(user_id: str, date: datetime.date) -> int:
    content = load_user_log(user_id, date)
    return len(re.findall(r"^###", content, re.MULTILINE))


# --- Summarize / flush ---

async def summarize_if_needed(user_id: str, date: datetime.date) -> None:
    """Compress today's log in-place when it exceeds SUMMARIZE_THRESHOLD exchanges."""
    try:
        if count_exchanges(user_id, date) > config.SUMMARIZE_THRESHOLD:
            path = get_user_log_path(user_id, date)
            log_content = load_user_log(user_id, date)
            if not log_content:
                return
            backup_path = path.replace(".md", ".raw.md")
            shutil.copy2(path, backup_path)
            from llm_client import summarize  # lazy import avoids circular dependency
            summary = await summarize(log_content)
            with open(path, "w", encoding="utf-8") as f:
                f.write(f"## {date.strftime('%Y-%m-%d')} (Summarized)\n\n")
                f.write(summary)
    except Exception as e:
        logger.error(f"Error during summarize_if_needed for user {user_id}: {e}")


async def flush_memory_if_needed(user_id: str, date: datetime.date) -> None:
    """Extract long-term facts from today's log and append to MEMORY.md when threshold exceeded."""
    try:
        if count_exchanges(user_id, date) > config.MEMORY_FLUSH_THRESHOLD:
            log_content = load_user_log(user_id, date)
            if not log_content:
                return
            from llm_client import flush_memory  # lazy import
            facts = await flush_memory(log_content)
            if facts and facts.strip():
                memory_path = get_user_memory_path(user_id)
                os.makedirs(os.path.dirname(memory_path), exist_ok=True)
                with open(memory_path, "a", encoding="utf-8") as f:
                    f.write(f"\n<!-- flushed {date.strftime('%Y-%m-%d')} -->\n")
                    f.write(facts.strip())
                    f.write("\n")
                logger.info(f"Flushed memory for user {user_id}")
    except Exception as e:
        logger.error(f"Error during flush_memory_if_needed for user {user_id}: {e}")
