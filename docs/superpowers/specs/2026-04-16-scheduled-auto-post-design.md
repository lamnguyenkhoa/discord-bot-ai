# Scheduled Auto-Post Feature Design

## Overview

Add scheduled/proactive posting capability to the existing auto_post module. The bot will periodically post AI-generated messages to watched channels in a round-robin fashion, skipping channels with recent activity.

## Configuration

New environment variables in `.env`:

| Variable | Default | Description |
|----------|---------|-------------|
| `AUTO_POST_SCHEDULED_ENABLED` | `false` | Enable/disable scheduled posting |
| `AUTO_POST_SCHEDULED_CHANNELS` | (empty) | Comma-separated channels allowed for scheduled posts |
| `AUTO_POST_SCHEDULED_INTERVAL_MINUTES` | `60` | Minutes between channel rotations |
| `AUTO_POST_SCHEDULED_ACTIVE_SKIP_MINUTES` | `5` | Skip if messages in last X minutes |
| `AUTO_POST_CONTEXT_HOURS` | `24` | Only use memories from last X hours for relevance |

## Architecture

### Components

1. **ScheduledPoster class** - Manages the round-robin state and scheduling logic
2. **Background task** - Uses asyncio to run the scheduler
3. **Channel activity tracker** - Tracks last message time per channel

### Data Flow

```
on_ready()
  └─> start_scheduled_poster()
        └─> Background task (runs every INTERVAL minutes)
              ├─> Select next channel (round-robin from allowed list)
              ├─> Check if channel was quiet (no messages in last X min)
              │     ├─> If quiet: generate and post message
              │     └─> If active: skip, move to next channel
              └─> Schedule next run
```

### State Management

- `_current_channel_index` - tracks position in round-robin
- `_channel_last_message_time` - dict[channel_key] = timestamp
- `_scheduled_channels` - list of channels allowed for scheduled posts

## Behavior Details

### Round-Robin Selection
- Only considers channels in `AUTO_POST_SCHEDULED_CHANNELS`
- Maintains index position across cycles
- Skips channels that don't exist or bot can't post to

### Activity Detection
- Track `on_message` timestamp per channel
- On scheduled post attempt, compare against `AUTO_POST_SCHEDULED_ACTIVE_SKIP_MINUTES`
- If messages occurred in window, skip that channel

### Message Generation
- Reuses existing `llm_client.generate_reply()` 
- Uses same prompt template as reactive auto-post
- Same truncation and cooldown logic applies

### Context Retrieval with Recency Boost
- Uses existing `_recent_buffer` (last 20 messages) for immediate recency
- For semantic memory search, uses `mem0.search()` with the channel as filter
- Applies recency boost: memories from recent hours are weighted higher
- If mem0 metadata includes timestamps, filter to last 24 hours by default
- Final context combines: immediate recent buffer + recency-boosted semantic memories

### Integration with Existing Code
- No changes to existing reactive auto-post (`should_post`, `post`)
- New `ScheduledPoster` class in `module/auto_post/__init__.py`
- Background task started in `bot.py` `on_ready()`

## Error Handling

- Network/API failures: log warning, continue to next cycle
- Invalid channel: skip, move to next in round-robin
- LLM generates empty response: skip, reset cooldown for that channel

## Testing Considerations

1. Unit test `ScheduledPoster` round-robin logic
2. Unit test activity detection logic
3. Integration test with mock Discord client
