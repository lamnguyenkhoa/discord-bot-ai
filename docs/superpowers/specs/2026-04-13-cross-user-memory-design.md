# Cross-User Memory for Discord Bot

**Date:** 2026-04-13  
**Status:** Draft

## Goal

Enable the bot to maintain conversational context across users. When User B asks a follow-up question, the bot can reference what User A discussed with the bot earlier.

## Current State

mem0_manager.py stores memories in two scopes:

| Scope | user_id | Purpose |
|-------|---------|---------|
| User | `{guild_id}:{user_id}` | Per-user facts and preferences |
| Guild | `guild:{guild_id}` | Server-level knowledge |

`format_context_for_prompt()` queries guild memory with "server knowledge and preferences" - too factual, misses conversation flow.

## Proposed Change

Modify `format_context_for_prompt()` to query guild memory with a conversation-focused query.

### Code Change

In `mem0_manager.py`, change the guild memory query:

```python
# Before
guild_memories = _get_client().search(
    query=query or "server knowledge and preferences",
    user_id=_guild_id_only(guild_id),
    limit=5,
    threshold=GUILD_MEMORY_THRESHOLD,
)

# After
guild_memories = _get_client().search(
    query=query or "what was recently discussed or talked about",
    user_id=_guild_id_only(guild_id),
    limit=5,
    threshold=GUILD_MEMORY_THRESHOLD,
)
```

### Retrieval Order (unchanged)

1. Recent buffer (last 20 message pairs)
2. Guild memory (now conversation-focused)
3. User memory (if user_id provided)

### Memory Storage (unchanged)

`capture_exchange()` continues to store to both user and guild scopes. No storage changes needed.

## Example Flow

1. User A asks: "What anime should we watch this weekend?"
2. Bot stores to `guild:{guild_id}` (among other scopes)
3. User B joins next day, asks: "so what's happening this weekend?"
4. Bot queries guild memory with "recently discussed"
5. Bot finds anime discussion → includes in context
6. Bot responds naturally, referencing the weekend anime discussion

## Trade-offs

| Pro | Con |
|-----|-----|
| Single line change | Guild memory mixes facts + conversations |
| Zero storage overhead | May need query tuning |
| Immediate cross-user continuity | - |

## Future Considerations

If guild memory becomes too noisy, add a `type` field in metadata:
- `type: "fact"` - server rules, preferences
- `type: "conversation"` - discussion topics

Then filter by type when querying. Not implementing now (YAGNI).

## Files Changed

- `mem0_manager.py`: Line ~195 - change guild query string
