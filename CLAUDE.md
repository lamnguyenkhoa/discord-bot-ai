# Discord Bot AI — Project Guide

## Overview
A Discord bot that responds when @mentioned, powered by an LLM via OpenRouter. Maintains rolling daily conversation logs and auto-summarizes them when they grow large.

## Architecture

| File | Role |
|------|------|
| `bot.py` | Discord client, event handlers (`on_ready`, `on_message`) |
| `llm_client.py` | OpenRouter API calls (`generate_reply`, `summarize`) via `openai` SDK |
| `memory_manager.py` | Daily markdown log files: read, append, summarize-if-needed |
| `config.py` | All config from `.env` via `python-dotenv` |
| `system_prompt.txt` | Bot personality injected as system message |

## Key Flows

**Message handling** (`bot.py:on_message`):
1. Ignore messages that don't @mention the bot
2. Strip the mention tag from user text
3. Load yesterday + today memory context → pass to LLM
4. Reply, then append exchange to today's log
5. Summarize today's log if exchange count exceeds `SUMMARIZE_THRESHOLD`

**Memory** (`memory/YYYY-MM-DD.md`):
- Appended per exchange with timestamp and channel
- Summarized in-place (raw backup saved as `.raw.md`) when `count > SUMMARIZE_THRESHOLD`
- Context window: yesterday + today only

## Environment Variables (`.env`)

| Variable | Default | Description |
|----------|---------|-------------|
| `DISCORD_TOKEN` | — | Bot token from Discord Developer Portal |
| `OPENROUTER_API_KEY` | — | OpenRouter API key |
| `MODEL_NAME` | `openai/gpt-4o-mini` | LLM model slug |
| `SUMMARIZE_THRESHOLD` | `50` | Exchanges before auto-summarize |

## Running

```bash
pip install -r requirements.txt
python bot.py
```

Bot requires **MESSAGE CONTENT INTENT** enabled in Discord Developer Portal.

## Constraints & Conventions
- Bot only responds to direct @mentions; ignores all other messages
- Discord reply limit: 2000 chars (truncated with `...`)
- Memory files are gitignored and stay local
- `memory/` is auto-created on first run
- Fallback reply string is defined in `llm_client.FALLBACK_REPLY` — exchanges using it are not logged
- Avoid circular imports: `llm_client` is lazily imported inside `memory_manager.summarize_if_needed`

## Dependencies
- `discord.py >= 2.3`
- `openai >= 1.0` (used as OpenRouter client via `base_url`)
- `python-dotenv >= 1.0`
