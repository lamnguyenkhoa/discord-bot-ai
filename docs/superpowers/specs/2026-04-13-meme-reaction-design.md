# Meme Reaction Feature Design

**Date:** 2026-04-13

## Overview

Add automatic meme/GIF reactions to messages in watched channels. The bot randomly (5% chance) checks if a message warrants a meme reaction and sends an appropriate GIF.

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                      on_message                            │
├─────────────────────────────────────────────────────────────┤
│  1. Message in watched channel                             │
│  2. Roll random() < MEME_TRIGGER_CHANCE (5%)               │
│     └─ No → skip                                           │
│  3. Check keyword match                                     │
│     └─ Yes → send meme immediately                         │
│  4. LLM sentiment check (if no keyword)                   │
│     └─ Intensity >= 4 → send meme                          │
└─────────────────────────────────────────────────────────────┘
```

## Folder Structure

```
module/
└── meme-reaction/
    ├── __init__.py        # exports public API
    ├── config.py         # meme-specific config
    ├── meme_manager.py   # GIF search + caching
    └── trigger_decider.py # keyword + sentiment logic
```

## Components

### 1. Config (module/meme-reaction/config.py)

| Env Variable | Default | Description |
|--------------|---------|-------------|
| MEME_TRIGGER_CHANCE | 5 | Probability (0-100) to check for meme |
| MEME_API | "giphy" | API to use: "giphy" or "tenor" |
| MEME_API_KEY | (required) | API key for the chosen service |

### 2. meme_manager.py

- `search_gif(query: str) -> str` — Returns GIF URL or None
- Uses Giphy/Tenor API based on config
- Caches recent queries in memory to avoid duplicate API calls

### 3. trigger_decider.py

- `should_trigger_meme(message_text: str) -> bool`
- Checks:
  1. Keyword match (instant trigger)
  2. LLM sentiment analysis (intensity >= 4)
- Keywords: "lol", "haha", "lmao", "omg", "wow", "bro", "that's funny", "kekw", "lul", "pog"
- LLM prompt: Extract emotion (happy, excited, surprised, sad) + intensity 1-5

### 4. Integration (bot.py)

In watched channel handler, after message capture:

```python
if random.randint(1, 100) <= config.MEME_TRIGGER_CHANCE:
    if await meme_trigger_decider.should_trigger_meme(user_text):
        gif_url = await meme_manager.search_gif(user_text)
        if gif_url:
            await message.reply(gif_url)
```

## Meme Sources

### Giphy
- Endpoint: `https://api.giphy.com/v1/gifs/search`
- Free tier: 42 searches/day
- API key required (get from giphy.com/developers)

### Tenor
- Endpoint: `https://tenor.googleapis.com/v2/search`
- Free, rate-limited
- API key optional for higher limits

## Edge Cases

1. **No API key configured** — silently skip, log warning once
2. **API returns no results** — skip sending, don't retry
3. **Rate limited** — backoff for 60s, then resume
4. **Message too long** — truncate to last 200 chars for search
5. **Cooldown** — don't send more than 1 meme per 10 seconds per channel

## Testing

- Unit tests for keyword matching
- Mock LLM responses for sentiment tests
- Mock API responses for GIF search

## Rollout

1. Add config env vars to .env.example
2. Create meme_manager.py
3. Create trigger_decider.py
4. Integrate into bot.py watched channel flow
5. Add unit tests