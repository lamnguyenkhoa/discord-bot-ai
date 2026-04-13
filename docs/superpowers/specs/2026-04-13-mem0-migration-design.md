# Mem0 Memory System Migration

**Date:** 2026-04-13

## Overview

Replace the current file-based memory system (daily logs + manual fact extraction) with mem0 for semantic memory management.

## Architecture

**New file:** `mem0_manager.py`

Replaces `memory_manager.py` + `facts_manager.py` entirely. Uses mem0's native API for auto-extraction and semantic search.

## Memory Organization

| Scope | User ID Format | Purpose |
|-------|----------------|---------|
| Guild | `guild:{guild_id}` | Shared server knowledge, conversation summaries |
| User | `{guild_id}:{user_id}` | Per-user important info (preferences, skills, habits) |

## Core Interface

```python
async def initialize() -> None
    # Initialize mem0 client with ChromaDB backend

async def capture_exchange(
    user_id: str,           # "{guild_id}:{user_id}" for user, "guild:{guild_id}" for guild
    session_id: str,         # guild_id (conversation thread)
    messages: list[dict],    # [{"role": "user/assistant", "content": "..."}]
    metadata: dict,          # {channel, username, msg_id}
) -> None

def format_context_for_prompt(session_id: str, query: str = "") -> str
    # Returns: recent messages + semantic memories (guild + user)

async def delete_by_msg_id(msg_id: int, guild_id: str) -> None
    # Delete memories associated with a specific message

async def get_user_memories(guild_id: str, user_id: str) -> list[str]
async def get_guild_memories(guild_id: str) -> list[str]
```

## Data Flow

### Capture Exchange
1. Build messages list: `[{"role": "user", "content": user_text}, {"role": "assistant", "content": bot_reply}]`
2. Call `mem0.add()` twice: once for user memories, once for guild memories
3. mem0 auto-extracts important facts based on relevance

### Context Retrieval
1. Recent in-memory buffer → last 20 messages per guild
2. `mem0.search()` → guild memories with relevance >= 0.6
3. `mem0.search()` → user memories with relevance >= 0.7
4. Combine: `## Recent\n{buffer}\n\n## Guild Memory\n{memories}\n\n## User Memory\n{user_memories}`

## Mem0 Configuration

```python
from mem0 import Memory

config = {
    "llm": {
        "provider": "openai",
        "config": {"model": config.MODEL_NAME, "api_key": config.OPENAI_API_KEY}
    },
    "vector_store": {
        "provider": "chroma",
        "config": {"collection_name": "discord_bot_memory", "path": "./index"}
    },
    "embedder": {
        "provider": "openai",
        "config": {"model": "text-embedding-3-small", "api_key": config.OPENAI_API_KEY}
    }
}

memory = Memory.from_config(config)
```

## bot.py Integration

```python
import mem0_manager

# on_ready()
await mem0_manager.initialize()

# on_message()
messages = [{"role": "user", "content": user_text}]
# ... generate reply ...
messages.append({"role": "assistant", "content": reply})
await mem0_manager.capture_exchange(
    user_id=f"{guild_id}:{user_id}",
    session_id=guild_id,
    messages=messages,
    metadata={"channel": channel_name, "username": author_name, "msg_id": message.id}
)
context = mem0_manager.format_context_for_prompt(session_id=guild_id, query=user_text)
```

## Config Additions

```python
# config.py
MEMORY_VECTOR_DB_PATH = "./index/memory"  # ChromaDB persistence
```

## Constants

```python
MAX_RECENT_MESSAGES = 20      # In-memory buffer per guild
USER_MEMORY_THRESHOLD = 0.7  # Relevance threshold for user memories
GUILD_MEMORY_THRESHOLD = 0.6 # Slightly lower for broader guild context
```

## Deleted Files

After migration and validation:
- `memory_manager.py` — replaced
- `facts_manager.py` — replaced
- `index/memory.sqlite` — replaced by ChromaDB
- `memory/guilds/` directory — no longer used

## Testing

1. Manual testing in Discord — verify memories are captured and retrieved
2. Check ChromaDB collection for stored memories
3. Verify semantic search returns relevant results

## Scope

Single deliverable: functional mem0 integration replacing the old system.
