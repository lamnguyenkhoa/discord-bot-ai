import asyncio
import logging
import os
import re

import config
from memory_manager import get_user_memory_path, get_guild_memory_path

logger = logging.getLogger(__name__)

_FACT_RE = re.compile(r"^- (.+?)(?:\s+<!-- msg:(\d+) -->)?$")

_facts_lock = asyncio.Lock()

STOP_WORDS = {
    "likes", "plays", "is", "are", "was", "were", "has", "have", "had",
    "a", "an", "the", "and", "or", "but", "in", "on", "at", "to", "for",
    "of", "with", "about", "from", "by", "not", "no", "i", "my", "me",
    "he", "she", "they", "we", "it",
    "really", "very", "good", "bad", "best", "great", "favorite",
    "much", "just", "also", "so", "too", "that", "this", "some",
}


def _tokenize(text: str) -> set:
    tokens = re.split(r"\s+", text.lower())
    result = set()
    for token in tokens:
        token = token.strip(".,!?;:'\"()[]{}")
        if token and token not in STOP_WORDS:
            result.add(token)
    return result


def _read_memory_file(path: str) -> list[dict]:
    """Parse a MEMORY.md file into a list of {text, msg_id} dicts."""
    facts = []
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                stripped = line.rstrip("\n").strip()
                m = _FACT_RE.match(stripped)
                if m:
                    facts.append({
                        "text": m.group(1).strip(),
                        "msg_id": int(m.group(2)) if m.group(2) else None,
                    })
    except FileNotFoundError:
        pass
    except Exception as e:
        logger.error(f"Error reading memory file {path}: {e}")
    return facts


def _write_memory_file(path: str, facts: list[dict], header: str = "# Memory") -> None:
    """Write facts list back to a MEMORY.md file."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    lines = [header, ""]
    for f in facts:
        bullet = f"- {f['text']}"
        if f.get("msg_id") is not None:
            bullet += f" <!-- msg:{f['msg_id']} -->"
        lines.append(bullet)
    lines.append("")
    try:
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("\n".join(lines))
    except Exception as e:
        logger.error(f"Error writing memory file {path}: {e}")


def load_facts(user_id: str, guild_id: str | None = None) -> str:
    """Load user and guild memory as a combined string for prompt injection."""
    parts = []
    user_path = get_user_memory_path(user_id)
    if os.path.exists(user_path):
        try:
            with open(user_path, "r", encoding="utf-8") as f:
                content = f.read().strip()
            if content:
                parts.append(f"## User Memory\n{content}")
        except Exception as e:
            logger.error(f"Error reading user memory {user_path}: {e}")

    if guild_id:
        guild_path = get_guild_memory_path(guild_id)
        if os.path.exists(guild_path):
            try:
                with open(guild_path, "r", encoding="utf-8") as f:
                    content = f.read().strip()
                if content:
                    parts.append(f"## Server Memory\n{content}")
            except Exception as e:
                logger.error(f"Error reading guild memory {guild_path}: {e}")

    return "\n\n".join(parts)


async def upsert_user_fact(
    user_id: str,
    user_name: str,
    new_fact: str,
    msg_id=None,
    old_fact: str | None = None,
) -> None:
    if not new_fact or not new_fact.strip():
        return
    path = get_user_memory_path(user_id)
    async with _facts_lock:
        facts = _read_memory_file(path)
        replaced = False

        # Correction path: old_fact must be a substring of stored text
        if old_fact:
            for f in facts:
                if old_fact in f["text"]:
                    logger.info(f"Corrected fact for {user_name}: '{f['text']}' -> '{new_fact}'")
                    f["text"] = new_fact
                    f["msg_id"] = msg_id
                    replaced = True
                    break

        # Keyword overlap path (>= 2 shared non-stop tokens)
        if not replaced:
            new_tokens = _tokenize(new_fact)
            best_match = None
            best_score = 0
            for f in facts:
                overlap = len(new_tokens & _tokenize(f["text"]))
                if overlap >= 2 and overlap > best_score:
                    best_score = overlap
                    best_match = f
            if best_match:
                logger.info(f"Replaced fact for {user_name}: '{best_match['text']}' -> '{new_fact}' (overlap={best_score})")
                best_match["text"] = new_fact
                best_match["msg_id"] = msg_id
                replaced = True

        if not replaced:
            logger.info(f"Appended new fact for {user_name}: '{new_fact}'")
            facts.append({"text": new_fact, "msg_id": msg_id})

        _write_memory_file(path, facts, header="# User Memory")


async def upsert_server_fact(
    guild_id: str | None,
    new_fact: str,
    msg_id=None,
) -> None:
    if not guild_id or not new_fact or not new_fact.strip():
        return
    path = get_guild_memory_path(guild_id)
    async with _facts_lock:
        facts = _read_memory_file(path)
        new_tokens = _tokenize(new_fact)
        best_match = None
        best_score = 0

        for f in facts:
            overlap = len(new_tokens & _tokenize(f["text"]))
            if overlap >= 2 and overlap > best_score:
                best_score = overlap
                best_match = f

        if best_match:
            logger.info(f"Replaced server fact: '{best_match['text']}' -> '{new_fact}' (overlap={best_score})")
            best_match["text"] = new_fact
            best_match["msg_id"] = msg_id
        else:
            logger.info(f"Appended new server fact: '{new_fact}'")
            facts.append({"text": new_fact, "msg_id": msg_id})

        _write_memory_file(path, facts, header="# Server Memory")


async def remove_facts_by_msg_id(
    msg_id: int,
    user_id: str | None = None,
    guild_id: str | None = None,
) -> int:
    """Remove facts tagged with msg_id from user and/or guild memory files."""
    removed = 0
    async with _facts_lock:
        paths = []
        if user_id:
            paths.append((get_user_memory_path(user_id), "# User Memory"))
        if guild_id:
            paths.append((get_guild_memory_path(guild_id), "# Server Memory"))

        for path, header in paths:
            facts = _read_memory_file(path)
            to_keep = [f for f in facts if f.get("msg_id") != msg_id]
            delta = len(facts) - len(to_keep)
            if delta > 0:
                _write_memory_file(path, to_keep, header=header)
                logger.info(f"Removed {delta} fact(s) tagged with msg_id={msg_id} from {path}")
                removed += delta

    return removed
