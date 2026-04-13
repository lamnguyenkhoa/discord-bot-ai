# Mem0 Memory System Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace file-based memory system with mem0 for semantic memory management

**Architecture:** Single `mem0_manager.py` module using mem0's native API with ChromaDB backend. Stores guild-shared and per-user memories with automatic extraction.

**Tech Stack:** Python, mem0ai, ChromaDB, existing OpenAI-compatible LLM (OpenRouter/Ollama)

---

## File Structure

| File | Purpose |
|------|---------|
| Create: `mem0_manager.py` | New memory manager using mem0 |
| Modify: `bot.py:179-266` | Update to use new mem0_manager |
| Create: `tests/test_mem0_manager.py` | Unit tests |

---

## Task 1: Install Dependencies

- [ ] **Step 1: Install mem0 package**

Run: `pip install mem0ai`

Expected: Package installed successfully

- [ ] **Step 2: Commit**

```bash
pip install mem0ai
git add requirements.txt 2>/dev/null || echo "mem0ai" >> requirements.txt
git commit -m "chore: add mem0ai dependency"
```

---

## Task 2: Create mem0_manager.py

**Files:**
- Create: `mem0_manager.py`

- [ ] **Step 1: Write the mem0_manager.py module**

```python
"""
Mem0 Memory Manager - Semantic memory using mem0 with ChromaDB backend.

Memory organization:
- Guild memories: user_id = "guild:{guild_id}"
- User memories: user_id = "{guild_id}:{user_id}"
"""

import asyncio
import logging
from collections import defaultdict
from typing import Optional

from mem0 import Memory

import config

logger = logging.getLogger(__name__)

MAX_RECENT_MESSAGES = 20
USER_MEMORY_THRESHOLD = 0.7
GUILD_MEMORY_THRESHOLD = 0.6

_memory_client: Optional[Memory] = None
_recent_buffer: dict[str, list[dict]] = defaultdict(list)
_buffer_lock = asyncio.Lock()


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
                "api_base": config.LLM_BASE_URL,
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
                "api_base": config.EMBEDDING_BASE_URL,
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


def _guild_user_id(guild_id: str, user_id: str) -> str:
    """Format user_id for per-user memories."""
    return f"{guild_id}:{user_id}"


def _guild_id_only(guild_id: str) -> str:
    """Format user_id for guild-level memories."""
    return f"guild:{guild_id}"


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
        "msg_id": str(msg_id) if msg_id else None,
    }

    try:
        async with _buffer_lock:
            buffer_key = guild_id
            self_id = _guild_user_id(guild_id, user_id)
            
            _recent_buffer[buffer_key].append({
                "role": "user",
                "content": f"{username}: {user_message}",
            })
            _recent_buffer[buffer_key].append({
                "role": "assistant", 
                "content": f"Bot: {bot_reply}",
            })
            if len(_recent_buffer[buffer_key]) > MAX_RECENT_MESSAGES * 2:
                _recent_buffer[buffer_key] = _recent_buffer[buffer_key][-MAX_RECENT_MESSAGES * 2:]

        user_result = _get_client().add(
            messages=messages,
            user_id=self_id,
            session_id=guild_id,
            metadata=metadata,
        )
        logger.info(f"Captured user memory for {self_id}: {user_result.get('memories', [])}")

        guild_result = _get_client().add(
            messages=messages,
            user_id=_guild_id_only(guild_id),
            session_id=guild_id,
            metadata=metadata,
        )
        logger.info(f"Captured guild memory for {guild_id}: {guild_result.get('memories', [])}")

    except Exception as e:
        logger.error(f"Error capturing exchange to mem0: {e}")


def format_context_for_prompt(guild_id: str, user_id: Optional[str] = None, query: str = "") -> str:
    """
    Build context string for prompt injection.
    
    Args:
        guild_id: Discord guild/server ID
        user_id: Optional Discord user ID for per-user context
        query: Current user message for semantic search
    
    Returns:
        Formatted context string with recent messages and relevant memories
    """
    parts = []

    async with _buffer_lock:
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
        guild_memories = _get_client().search(
            query=query or "server knowledge and preferences",
            user_id=_guild_id_only(guild_id),
            limit=5,
            threshold=GUILD_MEMORY_THRESHOLD,
        )
        if guild_memories.get("results"):
            guild_text = "\n".join(f"- {m['memory']}" for m in guild_memories["results"])
            parts.append(f"## Guild Memory\n{guild_text}")

        if user_id:
            user_memories = _get_client().search(
                query=query or "user preferences and important facts",
                user_id=_guild_user_id(guild_id, user_id),
                limit=3,
                threshold=USER_MEMORY_THRESHOLD,
            )
            if user_memories.get("results"):
                user_text = "\n".join(f"- {m['memory']}" for m in user_memories["results"])
                parts.append(f"## User Memory\n{user_text}")

    except Exception as e:
        logger.error(f"Error searching memories: {e}")

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
        all_memories = _get_client().get_all(user_id=_guild_id_only(guild_id))
        for memory in all_memories.get("results", []):
            if memory.get("metadata", {}).get("msg_id") == str(msg_id):
                _get_client().delete(memory_id=memory["id"])
                logger.info(f"Deleted guild memory {memory['id']} for msg_id={msg_id}")
    except Exception as e:
        logger.error(f"Error deleting memories for msg_id={msg_id}: {e}")


def get_user_memories(guild_id: str, user_id: str) -> list[str]:
    """Get all memories for a specific user in a guild."""
    if _memory_client is None:
        return []
    
    try:
        result = _get_client().get_all(user_id=_guild_user_id(guild_id, user_id))
        return [m["memory"] for m in result.get("results", [])]
    except Exception as e:
        logger.error(f"Error getting user memories: {e}")
        return []


def get_guild_memories(guild_id: str) -> list[str]:
    """Get all memories for a guild."""
    if _memory_client is None:
        return []
    
    try:
        result = _get_client().get_all(user_id=_guild_id_only(guild_id))
        return [m["memory"] for m in result.get("results", [])]
    except Exception as e:
        logger.error(f"Error getting guild memories: {e}")
        return []
```

- [ ] **Step 2: Commit**

```bash
git add mem0_manager.py
git commit -m "feat: add mem0_manager module with semantic memory"
```

---

## Task 3: Update bot.py

**Files:**
- Modify: `bot.py`

- [ ] **Step 1: Update imports in bot.py**

Find line 8: `import memory_manager`

Replace with:
```python
import mem0_manager
```

Find line 9: `import facts_manager` and `import llm_client`

Remove `import facts_manager` line entirely.

- [ ] **Step 2: Update on_ready() to initialize mem0**

Find line 59-61:
```python
@client.event
async def on_ready():
    logger.info(f"Logged in as {client.user} (ID: {client.user.id})")
    indexer.init_db()
```

Replace with:
```python
@client.event
async def on_ready():
    logger.info(f"Logged in as {client.user} (ID: {client.user.id})")
    indexer.init_db()
    await mem0_manager.initialize()
```

- [ ] **Step 3: Update watch channel logging (lines 179-186)**

Find:
```python
            memory_manager.append_exchange(
                user_id=user_id,
                guild_id=guild_id,
                channel_name=str(message.channel),
                author_name=str(message.author.display_name),
                user_message=user_text,
                bot_reply="",
            )
```

Replace with:
```python
            await mem0_manager.capture_exchange(
                user_id=user_id,
                guild_id=guild_id,
                channel_name=str(message.channel),
                username=str(message.author.display_name),
                user_message=user_text,
                bot_reply="",
                msg_id=message.id,
            )
```

- [ ] **Step 4: Update context loading (lines 211-219)**

Find:
```python
    # RAG: retrieve relevant memory chunks for context
    # Use new unified memory system - load context from guild log
    if guild_id:
        memory_context = memory_manager.format_context_for_prompt(guild_id)
    else:
        # DM - no guild memory
        memory_context = ""

    facts_context = facts_manager.load_facts(guild_id)
```

Replace with:
```python
    # Mem0: retrieve relevant memory chunks for context
    if guild_id:
        memory_context = mem0_manager.format_context_for_prompt(guild_id, user_id, user_text)
    else:
        # DM - no guild memory
        memory_context = ""
```

- [ ] **Step 5: Update llm_client.generate_reply call (lines 222-229)**

Find:
```python
    async with message.channel.typing():
        reply = await llm_client.generate_reply(
            user_message=user_text,
            memory_context=memory_context,
            channel_name=str(message.channel),
            facts_context=facts_context,
            image_urls=image_urls,
        )
```

Replace with:
```python
    async with message.channel.typing():
        reply = await llm_client.generate_reply(
            user_message=user_text,
            memory_context=memory_context,
            channel_name=str(message.channel),
            image_urls=image_urls,
        )
```

- [ ] **Step 6: Update exchange capture after reply (lines 236-266)**

Find:
```python
    if reply != FALLBACK:
        author_name = str(message.author.display_name)
        memory_manager.append_exchange(
            user_id=user_id,
            guild_id=guild_id,
            channel_name=str(message.channel),
            author_name=author_name,
            user_message=user_text,
            bot_reply=reply,
        )
        extracted = await llm_client.extract_facts(
            author_name, user_text, reply, existing_facts=facts_context
        )
        for correction in extracted.get("corrections", []):
            await facts_manager.upsert_user_fact(
                user_id, author_name, correction["new_fact"],
                msg_id=message.id, old_fact=correction.get("old_fact"),
                guild_id=guild_id,
            )
        for fact in extracted["user_facts"]:
            await facts_manager.upsert_user_fact(user_id, author_name, fact, msg_id=message.id, guild_id=guild_id)
        for fact in extracted["server_facts"]:
            await facts_manager.upsert_server_fact(guild_id, fact, msg_id=message.id)

        # Compress log if needed (new unified system)
        if guild_id:
            await memory_manager.compress_log_if_needed(guild_id)
        if guild_id:
            asyncio.create_task(indexer.index_guild(guild_id))
```

Replace with:
```python
    if reply != FALLBACK and guild_id:
        author_name = str(message.author.display_name)
        await mem0_manager.capture_exchange(
            user_id=user_id,
            guild_id=guild_id,
            channel_name=str(message.channel),
            username=author_name,
            user_message=user_text,
            bot_reply=reply,
            msg_id=message.id,
        )
        if guild_id:
            asyncio.create_task(indexer.index_guild(guild_id))
```

- [ ] **Step 7: Commit**

```bash
git add bot.py
git commit -m "feat: integrate mem0_manager for semantic memory"
```

---

## Task 4: Test the Integration

- [ ] **Step 1: Run the bot and test basic functionality**

Start the bot: `python bot.py`

Test in Discord:
1. Send a message mentioning the bot
2. Ask something that reveals a preference (e.g., "I prefer Python over JavaScript")
3. Ask again later — bot should remember

- [ ] **Step 2: Verify mem0 storage**

Check the ChromaDB collection:
```python
from mem0 import Memory
import config

cfg = {...}  # Same config as mem0_manager
mem = Memory.from_config(cfg)
results = mem.get_all(user_id="guild:YOUR_GUILD_ID")
print(results)
```

- [ ] **Step 3: Commit test results or fixes**

```bash
git add -A
git commit -m "test: mem0 integration verified"
```

---

## Task 5: Cleanup Old Files (Optional)

**After successful testing, remove old memory system files:**

- [ ] **Step 1: Remove old files**

```bash
rm memory_manager.py
rm facts_manager.py
git add -A
git commit -m "chore: remove old file-based memory system"
```

---

## Verification Checklist

- [ ] mem0 package installed
- [ ] mem0_manager.py created with all functions
- [ ] bot.py updated to use mem0_manager
- [ ] Bot starts without errors
- [ ] Memories captured after conversation
- [ ] Context retrieved on subsequent queries
- [ ] ChromaDB files created in ./index/mem0_db
