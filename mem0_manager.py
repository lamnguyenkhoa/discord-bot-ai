"""
Mem0 Memory Manager - Semantic memory using mem0 with ChromaDB backend.

Memory organization:
- Unified guild memories: user_id = guild_id
"""

import logging
import threading
from collections import defaultdict
from typing import Optional

from mem0 import Memory

import config

logger = logging.getLogger(__name__)

MAX_RECENT_MESSAGES = 20
GUILD_MEMORY_THRESHOLD = 0.6

_memory_client: Optional[Memory] = None
_recent_buffer: dict[str, list[dict]] = defaultdict(list)
_buffer_lock = threading.Lock()


def _build_mem0_config() -> dict:
    """Build mem0 configuration matching existing LLM setup."""
    llm_provider = "openai"
    if config.LLM_BASE_URL and "ollama" in config.LLM_BASE_URL:
        llm_provider = "ollama"
    elif config.LLM_BASE_URL and "openrouter" in config.LLM_BASE_URL:
        llm_provider = "openai"
    
    embedding_provider = "openai"
    if config.EMBEDDING_BASE_URL and "ollama" in config.EMBEDDING_BASE_URL:
        embedding_provider = "ollama"

    return {
        "llm": {
            "provider": llm_provider,
            "config": {
                "model": config.MODEL_NAME,
                "api_key": config.LLM_API_KEY,
                "openai_base_url": config.LLM_BASE_URL,
            }
        },
        "vector_store": {
            "provider": "chroma",
            "config": {
                "collection_name": "discord_bot_memory",
                "path": "./index/mem0_db",
            }
        },
        "embedder": {
            "provider": embedding_provider,
            "config": {
                "model": config.EMBEDDING_MODEL,
                "api_key": config.EMBEDDING_API_KEY,
                "openai_base_url": config.EMBEDDING_BASE_URL,
            }
        }
    }


async def initialize() -> None:
    """Initialize mem0 client."""
    global _memory_client
    try:
        _memory_client = Memory.from_config(_build_mem0_config())
        logger.info("Mem0 memory client initialized")
    except Exception as e:
        logger.error(f"Failed to initialize mem0: {e}")
        raise


def _get_client() -> Memory:
    """Get the mem0 client, raising if not initialized."""
    if _memory_client is None:
        raise RuntimeError("mem0_manager not initialized. Call initialize() first.")
    return _memory_client


async def capture_exchange(
    user_id: str,
    guild_id: str,
    channel_name: str,
    username: str,
    user_message: str,
    bot_reply: str,
    msg_id: Optional[int] = None,
) -> None:
    """
    Capture a conversation exchange into memory.
    
    Args:
        user_id: Discord user ID
        guild_id: Discord guild/server ID
        channel_name: Channel where exchange happened
        username: Display name of the user
        user_message: What the user said
        bot_reply: What the bot responded
        msg_id: Discord message ID for cross-referencing
    """
    if _memory_client is None:
        return

    messages = [
        {"role": "user", "content": user_message},
        {"role": "assistant", "content": bot_reply},
    ]
    
    metadata = {
        "channel": channel_name,
        "username": username,
    }
    if msg_id:
        metadata["msg_id"] = str(msg_id)

    try:
        with _buffer_lock:
            _recent_buffer[guild_id].append({
                "role": "user",
                "content": f"{username}: {user_message}",
            })
            _recent_buffer[guild_id].append({
                "role": "assistant", 
                "content": f"Bot: {bot_reply}",
            })
            if len(_recent_buffer[guild_id]) > MAX_RECENT_MESSAGES * 2:
                _recent_buffer[guild_id] = _recent_buffer[guild_id][-MAX_RECENT_MESSAGES * 2:]

        result = _get_client().add(
            messages=messages,
            user_id=guild_id,
            metadata=metadata,
        )
        logger.info(f"Captured memory for guild {guild_id}: {result.get('memories', [])}")

    except Exception as e:
        logger.error(f"Error capturing exchange to mem0: {e}")


def format_context_for_prompt(guild_id: str, user_id: Optional[str] = None, query: str = "") -> str:
    """
    Build context string for prompt injection.
    
    Args:
        guild_id: Discord guild/server ID
        user_id: Optional Discord user ID (kept for signature compatibility, ignored)
        query: Current user message for semantic search
    
    Returns:
        Formatted context string with recent messages and relevant memories
    """
    parts = []

    with _buffer_lock:
        recent = _recent_buffer.get(guild_id, [])[-MAX_RECENT_MESSAGES * 2:]

    if recent:
        recent_formatted = "\n".join(
            f"{'User' if m['role'] == 'user' else 'Bot'}: {m['content']}" 
            for m in recent
        )
        parts.append(f"## Recent Conversation\n{recent_formatted}")

    if _memory_client is None:
        return "\n\n".join(parts) if parts else "No memory available."

    try:
        memories = _get_client().search(
            query=query or "what was recently discussed or talked about",
            user_id=guild_id,
            limit=5,
            threshold=GUILD_MEMORY_THRESHOLD,
        )
        if memories.get("results"):
            memory_text = "\n".join(f"- {m['memory']}" for m in memories["results"])
            parts.append(f"## Memory\n{memory_text}")

    except Exception as e:
        logger.error(f"Error searching memories: {e}")

    return "\n\n".join(parts) if parts else "No memory available."


def get_channel_context(channel_name: str, guild_id: str, max_hours: int = 24) -> str:
    """
    Build context for a specific channel with recency boost.
    
    Note: mem0 does not store timestamps in metadata, so temporal filtering
    by max_hours is not implemented. The parameter is kept for API compatibility.
    
    Args:
        channel_name: Channel to get context for
        guild_id: Discord guild/server ID
        max_hours: Unused (kept for API compatibility)
    
    Returns:
        Formatted context string with recency-boosted memories
    """
    parts = []

    with _buffer_lock:
        recent = _recent_buffer.get(guild_id, [])[-MAX_RECENT_MESSAGES * 2:]

    if recent:
        recent_formatted = "\n".join(
            f"{'User' if m['role'] == 'user' else 'Bot'}: {m['content']}" 
            for m in recent
        )
        parts.append(f"## Recent Conversation\n{recent_formatted}")

    if _memory_client is None:
        return "\n\n".join(parts) if parts else "No memory available."

    try:
        all_memories = _get_client().get_all(user_id=guild_id)
        recent_memories = []
        older_memories = []
        
        for m in all_memories.get("results", []):
            memory_text = m.get("memory", "")
            metadata = m.get("metadata", {})
            if metadata.get("channel", "").lower() == channel_name.lower():
                recent_memories.append(f"- {memory_text}")
            else:
                older_memories.append(f"- {memory_text}")
        
        if recent_memories:
            parts.append(f"## Recent Memories for #{channel_name}\n" + "\n".join(recent_memories[:5]))
        if older_memories and not recent_memories:
            parts.append(f"## Related Memories\n" + "\n".join(older_memories[:3]))

    except Exception as e:
        logger.error(f"Error getting channel context: {e}")

    return "\n\n".join(parts) if parts else "No memory available."


async def delete_by_msg_id(msg_id: int, guild_id: str) -> None:
    """
    Delete memories associated with a specific message.
    
    Note: mem0 doesn't support direct lookup by metadata.
    This is a best-effort cleanup — memories may persist.
    """
    if _memory_client is None:
        return
    
    try:
        all_memories = _get_client().get_all(user_id=guild_id)
        for memory in all_memories.get("results", []):
            if memory.get("metadata", {}).get("msg_id") == str(msg_id):
                _get_client().delete(memory_id=memory["id"])
                logger.info(f"Deleted guild memory {memory['id']} for msg_id={msg_id}")
    except Exception as e:
        logger.error(f"Error deleting memories for msg_id={msg_id}: {e}")


def get_guild_memories(guild_id: str) -> list[str]:
    """Get all memories for a guild."""
    if _memory_client is None:
        return []
    
    try:
        result = _get_client().get_all(user_id=guild_id)
        return [m["memory"] for m in result.get("results", [])]
    except Exception as e:
        logger.error(f"Error getting guild memories: {e}")
        return []
