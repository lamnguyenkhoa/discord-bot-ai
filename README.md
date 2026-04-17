# Discord Bot AI

A Discord bot with AI-powered conversation using LLM (OpenRouter/Ollama), semantic memory (mem0), RAG for guild documents, and interactive features.

## Setup

1. Copy `.env` to `.env.local` and fill in your credentials
2. Install dependencies: `pip install -r requirements.txt`
3. Run: `python bot.py`

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `DISCORD_TOKEN` | required | Discord bot token |
| `LLM_BASE_URL` | openrouter.ai/api/v1 | LLM endpoint |
| `OPENROUTER_API_KEY` | required | OpenRouter API key |
| `MODEL_NAME` | openai/gpt-4o-mini | Model |
| `WATCH_CHANNELS` | | Silent observe channels |
| `KNOWLEDGE_PATH` | ./knowledge | .md files for RAG |
| `INDEX_PATH` | ./db/memory.sqlite | FTS5 index |

### Features

| Variable | Default | Description |
|----------|---------|-------------|
| `SUMMARIZE_THRESHOLD` | 50 | Message length before summarization |
| `WEB_SEARCH_ENABLED` | true | Enable web search via OpenRouter |
| `KILL_WORD` | | Stop bot word (allowed user only) |

### Memory / RAG Index

| Variable | Default | Description |
|----------|---------|-------------|
| `INDEX_AUTO_ON_START` | true | Auto-index on startup |
| `INDEX_WATCH_INTERVAL` | 60 | File watcher interval (seconds) |
| `EMBEDDING_API_KEY` | LLM_API_KEY | Embedding API key |
| `EMBEDDING_MODEL` | text-embedding-3-small | Embedding model |

### Auto-post (Proactive Messages)

| Variable | Default | Description |
|----------|---------|-------------|
| `AUTO_POST_ENABLED` | false | Enable proactive messages |
| `AUTO_POST_TRIGGER_MIN` | 3 | Min messages before trigger |
| `AUTO_POST_TRIGGER_MAX` | 10 | Max messages before trigger |
| `AUTO_POST_COOLDOWN_SECONDS` | 60 | Cooldown between posts |
| `AUTO_POST_MAX_LENGTH` | 500 | Max message length |
| `AUTO_POST_SCHEDULED_ENABLED` | false | Enable scheduled posting |
| `AUTO_POST_SCHEDULED_CHANNELS` | | Channels for scheduled posts |
| `AUTO_POST_SCHEDULED_INTERVAL_MINUTES` | 60 | Interval between scheduled posts |

### Meme Reaction

| Variable | Default | Description |
|----------|---------|-------------|
| `MEME_TRIGGER_CHANCE` | 0 | GIF reply trigger chance (0-100) |
| `MEME_API` | tenor | GIF API (giphy/tenor) |
| `MEME_API_KEY` | | API key for GIF service |
| `MEME_COOLDOWN_SECONDS` | 10 | Cooldown between GIFs |

### Follow-Up Chat

| Variable | Default | Description |
|----------|---------|-------------|
| `FOLLOW_UP_CHANCE` | 33 | Chance to send follow-up (0-100) |
| `FOLLOW_UP_COOLDOWN_SECONDS` | 30 | Cooldown between follow-ups |
| `FOLLOW_UP_DELAY_SECONDS` | 3.0 | Delay before sending follow-up |

### Voice Chat

Two-way voice conversation in Discord voice channels.

| Variable | Default | Description |
|----------|---------|-------------|
| `VOICE_ENABLED` | false | Enable voice chat |
| `ELEVENLABS_API_KEY` | | ElevenLabs API key |
| `ELEVENLABS_VOICE_ID` | premade/chat-abcd | Voice preset ID |
| `VOICE_WAKE_WORDS` | Hey Bot\|Hey Mal | Wake words (pipe-separated) |
| `VOICE_SILENCE_TIMEOUT_MS` | 500 | Silence timeout before processing |
| `VOICE_SESSION_TIMEOUT_SECONDS` | 30 | Session timeout |

## Commands

- `/index` - Re-index knowledge files (admin)
- `/memory` - List indexed files
- `/join` - Join your voice channel
- `/leave` - Leave the voice channel

## Architecture

```
bot.py (main entry)
├── config.py (environment config)
├── llm_client.py (OpenAI-compatible LLM client)
├── mem0_manager.py (semantic memory with ChromaDB)
├── indexer.py (FTS5 + embedding RAG index)
└── module/
    ├── rag/ (RAG: guild docs + web search)
    ├── meme_reaction/ (GIF replies on trigger)
    ├── auto_post/ (proactive messages)
    └── follow_up_chat/ (follow-up messages)
```
