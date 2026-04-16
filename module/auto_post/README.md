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

### Scheduled Auto-Post

Periodically posts AI-generated messages in a round-robin fashion across configured channels.

**Configuration:**

| Variable | Default | Description |
|----------|---------|-------------|
| `AUTO_POST_SCHEDULED_ENABLED` | `false` | Enable/disable scheduled posting |
| `AUTO_POST_SCHEDULED_CHANNELS` | (empty) | Comma-separated channels for scheduled posts |
| `AUTO_POST_SCHEDULED_INTERVAL_MINUTES` | `60` | Minutes between channel rotations |
| `AUTO_POST_SCHEDULED_ACTIVE_SKIP_MINUTES` | `5` | Skip if messages in last X minutes |
| `AUTO_POST_CONTEXT_HOURS` | `24` | Only use memories from last X hours |

**How It Works:**

1. Background task runs every interval (default 60 min)
2. Selects next channel in round-robin order
3. Checks if channel was quiet (no messages in last 5 min)
4. If quiet: generates and posts AI message using recency-boosted context
5. If active: skips and moves to next channel

## How It Works

1. `should_post(channel_key)` - Returns True when message count hits random threshold
2. `post(message, guild, channel_key)` - Generates and sends AI message with channel context

## Channel Personalities (Scheduled Posts)

You can configure custom content focus per channel for scheduled auto-posts via `channel_config.yaml`.

### Configuration File

Edit `module/auto_post/channel_config.yaml`:

```yaml
channels:
  general:
    prompt_directives:
      - "This channel is for casual conversation."
      - "Share interesting thoughts about the community."
    context_addition: ""
    capture_to_mem0: false

  python-help:
    prompt_directives:
      - "You are a Python expert."
      - "Provide concise, practical help."
    context_addition: "Recent Python discussions about async/await"
    capture_to_mem0: false
```

### Attributes

| Attribute | Default | Description |
|-----------|---------|-------------|
| `prompt_directives` | `[]` | List of directives; one randomly selected each post |
| `context_addition` | (empty) | Additional context; appended to mem0 context |
| `capture_to_mem0` | `false` | Whether to add auto-posts to mem0 memory |

### How It Works

- `prompt_directives` → one randomly selected, appended as "Channel purpose:"
- `context_addition` → appended to mem0 context
- `capture_to_mem0` → if true, the auto-post content is stored in mem0

### Loading Functions

```python
from module.auto_post.channel_config_loader import get_channel_config, get_all_channels

cfg = get_channel_config("general")
# Returns: {"prompt_directives": [...], "context_addition": "", "capture_to_mem0": false}

channels = get_all_channels()
# Returns: ["general", "python-help", "ai-ml"]
```

### Attributes

| Attribute | Default | Description |
|-----------|---------|-------------|
| `prompt_directive` | (empty) | Channel purpose/topic; appended to prompt |
| `context_addition` | (empty) | Additional context; appended to mem0 context |
| `capture_to_mem0` | `false` | Whether to add auto-posts to mem0 memory |

### How It Works

- `prompt_directive` → appended to prompt as "Channel purpose:"
- `context_addition` → appended to mem0 context
- `capture_to_mem0` → if true, the auto-post content is stored in mem0

### Loading Functions

```python
from module.auto_post.channel_config_loader import get_channel_config, get_all_channels

cfg = get_channel_config("general")
# Returns: {"prompt_directive": "", "context_addition": "", "capture_to_mem0": true}

channels = get_all_channels()
# Returns: ["general", "python-help", "ai-ml"]
```