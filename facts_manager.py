import asyncio
import logging
import os
import re

import config
from memory_manager import get_guild_memory_path, load_manual_memory, save_manual_memory

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


def load_facts(guild_id: str | None = None) -> str:
    """
    Load guild memory as a combined string for prompt injection.
    
    Now uses unified per-guild memory - no user-specific memory.
    """
    if guild_id:
        manual_memory = load_manual_memory(guild_id)
        if manual_memory:
            return f"## Server Memory\n{manual_memory}"
    return ""


async def upsert_user_fact(
    user_id: str,
    user_name: str,
    new_fact: str,
    msg_id=None,
    old_fact: str | None = None,
    guild_id: str | None = None,
) -> None:
    """
    Add a fact to the guild's shared memory.
    
    Since memory is now unified per-guild, user-specific facts are
    stored in the guild's MEMORY.md with user context in the fact text.
    """
    if not new_fact or not new_fact.strip():
        return
    
    # If guild_id provided, store in guild memory
    if guild_id:
        await upsert_server_fact(guild_id, f"[{user_name}] {new_fact}", msg_id)
        return
    
    logger.warning(f"upsert_user_fact called without guild_id - fact not saved: {new_fact}")


async def upsert_server_fact(
    guild_id: str | None,
    new_fact: str,
    msg_id=None,
) -> None:
    """Add/update a fact in the guild's shared manual memory."""
    if not guild_id or not new_fact or not new_fact.strip():
        return
    
    # Load existing memory
    existing = load_manual_memory(guild_id)
    
    # Parse existing facts
    facts = _read_memory_file(get_guild_memory_path(guild_id)) if existing else []
    
    # If no existing file with proper format, create new facts list
    if not facts and existing:
        # Try to parse as bullet points
        for line in existing.split('\n'):
            line = line.strip()
            if line.startswith('- '):
                facts.append({"text": line[2:], "msg_id": msg_id})
    
    new_tokens = _tokenize(new_fact)
    best_match = None
    best_score = 0

    for f in facts:
        overlap = len(new_tokens & _tokenize(f["text"]))
        if overlap >= 2 and overlap > best_score:
            best_score = overlap
            best_match = f

    async with _facts_lock:
        if best_match:
            logger.info(f"Replaced server fact: '{best_match['text']}' -> '{new_fact}' (overlap={best_score})")
            best_match["text"] = new_fact
            best_match["msg_id"] = msg_id
        else:
            logger.info(f"Appended new server fact: '{new_fact}'")
            facts.append({"text": new_fact, "msg_id": msg_id})

        # Write back using memory_manager's save function
        _write_memory_file(get_guild_memory_path(guild_id), facts, header="# Server Memory")


async def remove_facts_by_msg_id(
    msg_id: int,
    user_id: str | None = None,
    guild_id: str | None = None,
) -> int:
    """
    Remove facts tagged with msg_id from guild memory.
    
    Note: user_id is ignored in the new unified system - facts are stored
    per-guild, not per-user.
    """
    removed = 0
    
    if not guild_id:
        return 0
    
    async with _facts_lock:
        path = get_guild_memory_path(guild_id)
        facts = _read_memory_file(path)
        to_keep = [f for f in facts if f.get("msg_id") != msg_id]
        delta = len(facts) - len(to_keep)
        
        if delta > 0:
            _write_memory_file(path, to_keep, header="# Server Memory")
            logger.info(f"Removed {delta} fact(s) tagged with msg_id={msg_id} from {path}")
            removed += delta

    return removed
