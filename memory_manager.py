import datetime
import logging
import os
import shutil
import re

import config

logger = logging.getLogger(__name__)


def get_log_path(date: datetime.date) -> str:
    return os.path.join(config.MEMORY_DIR, date.strftime("%Y-%m-%d") + ".md")


def load_memory(date: datetime.date) -> str:
    path = get_log_path(date)
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return ""
    except Exception as e:
        logger.error(f"Error reading memory file {path}: {e}")
        return ""


def load_context() -> str:
    today = datetime.date.today()
    yesterday = today - datetime.timedelta(days=1)
    today_log = load_memory(today)
    yesterday_log = load_memory(yesterday)
    parts = [p for p in [yesterday_log, today_log] if p]
    return "\n---\n".join(parts)


def append_exchange(
    channel_name: str,
    author_name: str,
    user_message: str,
    bot_reply: str,
) -> None:
    date = datetime.date.today()
    path = get_log_path(date)
    try:
        os.makedirs(config.MEMORY_DIR, exist_ok=True)
        file_exists = os.path.exists(path)
        with open(path, "a", encoding="utf-8") as f:
            if not file_exists:
                f.write(f"## {date.strftime('%Y-%m-%d')}\n")
            now = datetime.datetime.now().strftime("%H:%M")
            f.write(f"### [{now}] #{channel_name}\n")
            f.write(f"User ({author_name}): {user_message}\n")
            f.write(f"Bot: {bot_reply}\n\n")
    except Exception as e:
        logger.error(f"Error appending exchange to {path}: {e}")


def count_exchanges(date: datetime.date) -> int:
    content = load_memory(date)
    return len(re.findall(r"^###", content, re.MULTILINE))


async def summarize_if_needed(date: datetime.date) -> None:
    try:
        if count_exchanges(date) > config.SUMMARIZE_THRESHOLD:
            path = get_log_path(date)
            log_content = load_memory(date)
            backup_path = path.replace(".md", ".raw.md")
            shutil.copy2(path, backup_path)
            from llm_client import summarize  # lazy import to avoid circular dependency
            summary = await summarize(log_content)
            with open(path, "w", encoding="utf-8") as f:
                f.write(f"## {date.strftime('%Y-%m-%d')} (Summarized)\n\n")
                f.write(summary)
    except Exception as e:
        logger.error(f"Error during summarize_if_needed: {e}")
