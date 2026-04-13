# Auto-Post Module Design

## Overview
Refactor the auto-post feature into a separate module under `/module`.

## Directory Structure
```
module/
  auto_post/
    __init__.py      # exports: AutoPostManager, get_auto_post_manager
```

## Components

### AutoPostManager Class

**State:**
- `message_count: dict[str, int]` - message counter per channel
- `last_post_time: dict[str, float]` - last post timestamp per channel

**Methods:**
- `should_post(channel_key: str) -> bool` - returns True when threshold reached
- `post(message: discord.Message, guild, channel_key: str)` - generates and sends the auto-post

**Configuration (from config.py):**
- `AUTO_POST_ENABLED`
- `AUTO_POST_TRIGGER_MIN`
- `AUTO_POST_TRIGGER_MAX`
- `AUTO_POST_COOLDOWN_SECONDS`
- `AUTO_POST_MAX_LENGTH`

## Integration

In `bot.py`:
```python
from module.auto_post import get_auto_post_manager

# Replace lines 135-215 with:
auto_post_manager = get_auto_post_manager()
if await auto_post_manager.should_post(channel_key):
    await auto_post_manager.post(message, message.guild, channel_key)
```

## Silent Observation
Stays in `bot.py` (lines 196-215 only capture to memory, no auto-post logic).

## Testing
Add unit tests for `should_post` logic.