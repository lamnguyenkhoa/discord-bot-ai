# Meme Reaction Module

Automatically responds to funny/meme-worthy messages with GIFs from Giphy or Tenor.

## Components

### MemeManager (`meme_manager.py`)
- Searches GIF APIs (Giphy/Tenor) based on message content
- Caches results for 5 minutes
- Requires API key configuration

### TriggerDecider (`trigger_decider.py`)
- Keyword-based detection: "lol", "haha", "lmao", "omg", "🤣", "😂", etc.
- LLM-based sentiment analysis (emotion intensity 1-5, triggers at 4+)

## Usage

```python
from module.meme_reaction import get_meme_manager, get_trigger_decider

meme_mgr = get_meme_manager()
trigger = get_trigger_decider()

# Check if should trigger
if await trigger.should_trigger_meme(message.content):
    gif_url = await meme_mgr.search_gif(query)
    # send GIF
```

## Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `MEME_TRIGGER_CHANCE` | `5` | Probability (0-100) to check for meme |
| `MEME_API` | `giphy` | API to use: "giphy" or "tenor" |
| `MEME_API_KEY` | (required) | API key for chosen service |
| `MEME_COOLDOWN_SECONDS` | `10` | Seconds between meme responses |

## Flow

1. Bot checks `MEME_TRIGGER_CHANCE` random roll
2. If triggered, `TriggerDecider` checks keywords + sentiment
3. If positive, `MemeManager` searches GIF API
4. GIF is sent as response