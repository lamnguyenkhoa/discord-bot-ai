# Auto Post Module

Periodically posts AI-generated messages in Discord channels to keep conversation engaging.

## What It Does

- Tracks message count per channel
- Triggers AI-generated posts after random threshold (3-10 messages by default)
- Uses LLM to generate contextual standalone statements based on recent conversation
- Enforces cooldown between posts (60 seconds default)
- Truncates long posts to fit within character limit (500 chars default)

## Usage

```python
from module.auto_post import get_auto_post_manager

manager = get_auto_post_manager()

# Check if should post
if manager.should_post(channel_key):
    await manager.post(message, guild, channel_key)
```

## Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `AUTO_POST_ENABLED` | `false` | Enable/disable auto posting |
| `AUTO_POST_TRIGGER_MIN` | `3` | Minimum messages before random trigger |
| `AUTO_POST_TRIGGER_MAX` | `10` | Maximum messages before random trigger |
| `AUTO_POST_COOLDOWN_SECONDS` | `60` | Seconds between posts |
| `AUTO_POST_MAX_LENGTH` | `500` | Max characters per post |

## How It Works

1. `should_post(channel_key)` - Returns True when message count hits random threshold
2. `post(message, guild, channel_key)` - Generates and sends AI message with channel context