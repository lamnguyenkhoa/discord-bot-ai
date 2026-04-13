# Proactive Auto-Post Feature

**Date:** 2026-04-13

## Overview

The bot occasionally writes standalone messages in watched channels, related to recent conversation context. No mention required.

## Configuration

`config.py` additions:

```python
# Auto-post feature
AUTO_POST_ENABLED = os.getenv("AUTO_POST_ENABLED", "false").lower() in ("1", "true", "yes")
AUTO_POST_TRIGGER_MIN = 3
AUTO_POST_TRIGGER_MAX = 10
AUTO_POST_COOLDOWN_SECONDS = 60
AUTO_POST_MAX_LENGTH = 500
```

## Behavior

| Parameter | Value |
|-----------|-------|
| Trigger | Random after 3-10 messages observed in watched channel |
| Cooldown | 60 seconds between posts in same channel |
| Content type | Mix of react-to-context and share-memory |
| Format | Single statement (no questions) |
| Max length | 500 characters |

## Data Structures

In `bot.py`, add to track per-channel state:

```python
class AutoPostState:
    def __init__(self):
        self.message_count: dict[str, int] = {}  # channel_name -> count
        self.last_post_time: dict[str, float] = {}  # channel_name -> timestamp
```

## Implementation

### 1. Message Tracking

In `on_message()` when silently observing watched channels:

```python
if AUTO_POST_ENABLED and str(message.channel) in config.WATCH_CHANNELS:
    channel_key = str(message.channel)
    state.message_count[channel_key] = state.message_count.get(channel_key, 0) + 1

    # Check trigger
    trigger_threshold = random.randint(config.AUTO_POST_TRIGGER_MIN, config.AUTO_POST_TRIGGER_MAX)
    if state.message_count[channel_key] >= trigger_threshold:
        await try_auto_post(message.channel, channel_key, state)
```

### 2. Try Auto-Post Logic

```python
async def try_auto_post(channel, channel_key, state):
    # Check cooldown
    last_post = state.last_post_time.get(channel_key, 0)
    if time.time() - last_post < config.AUTO_POST_COOLDOWN_SECONDS:
        state.message_count[channel_key] = 0
        return

    # Get channel context from mem0
    channel_context = mem0_manager.format_context_for_prompt(guild_id, None, "")

    # Generate post
    async with channel.typing():
        prompt = f"""In 1-2 sentences, write a standalone statement related to recent conversation in #{channel}.
It can comment on something discussed or share an interesting memory.
Keep it short (under {config.AUTO_POST_MAX_LENGTH} chars), conversational, no questions.

Recent context:
{channel_context}"""
        post = await llm_client.generate_reply(prompt, "", channel.name)

    if post and len(post) <= config.AUTO_POST_MAX_LENGTH:
        await channel.send(post)
        logger.info(f"Auto-posted in #{channel}")
        state.last_post_time[channel_key] = time.time()

    state.message_count[channel_key] = 0
```

### 3. State Initialization

Add as module-level in `bot.py`:

```python
auto_post_state = AutoPostState()
```

## Files to Modify

1. `config.py` — add `AUTO_POST_ENABLED` and related constants
2. `bot.py` — add state tracking, trigger logic, post generation

## Edge Cases

- No memory/context available → skip post
- LLM returns empty or error → skip post
- Channel cooldown active → reset count, don't post
- Message longer than max → truncate to 497 + "..."
- Multiple guilds → track per channel per guild

## Testing

1. Enable feature, post in watched channel, observe messages
2. Verify post triggers after ~3-10 messages randomly
3. Verify cooldown blocks rapid posts
4. Verify content is statement, not question
5. Verify length under 500 chars