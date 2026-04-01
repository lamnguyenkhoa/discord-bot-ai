import logging
import os
import config

logger = logging.getLogger(__name__)

FACTS_FILE = os.path.join(config.MEMORY_DIR, "facts.md")

_USER_SECTION = "## User Facts"
_SERVER_SECTION = "## Server Facts"

_TEMPLATE = """\
# Bot Memory

## User Facts

## Server Facts
"""


def _ensure_file() -> None:
    os.makedirs(config.MEMORY_DIR, exist_ok=True)
    if not os.path.exists(FACTS_FILE):
        with open(FACTS_FILE, "w", encoding="utf-8") as f:
            f.write(_TEMPLATE)


def load_facts() -> str:
    _ensure_file()
    try:
        with open(FACTS_FILE, "r", encoding="utf-8") as f:
            return f.read().strip()
    except Exception as e:
        logger.error(f"Error reading facts file: {e}")
        return ""


def _append_bullet(section_header: str, bullet: str) -> None:
    _ensure_file()
    try:
        with open(FACTS_FILE, "r", encoding="utf-8") as f:
            content = f.read()

        if section_header not in content:
            content += f"\n{section_header}\n"

        # Insert bullet right after the section header line
        insert_after = content.index(section_header) + len(section_header)
        content = content[:insert_after] + f"\n- {bullet}" + content[insert_after:]

        with open(FACTS_FILE, "w", encoding="utf-8") as f:
            f.write(content)
    except Exception as e:
        logger.error(f"Error appending to facts file: {e}")


def append_user_fact(user_name: str, fact: str) -> None:
    _append_bullet(_USER_SECTION, f"**{user_name}**: {fact}")


def append_server_fact(fact: str) -> None:
    _append_bullet(_SERVER_SECTION, fact)
