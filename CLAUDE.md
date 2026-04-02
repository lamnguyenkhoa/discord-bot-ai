# Discord Bot AI — Project Guide

## Overview
A Discord bot that responds when @mentioned, powered by an LLM via OpenRouter. Maintains rolling daily conversation logs, auto-summarizes them when they grow large, and builds a persistent facts memory from conversations.

## Architecture

| File | Role |
|------|------|
| `bot.py` | Discord client, event handlers (`on_ready`, `on_message`, `on_raw_reaction_add`, `on_disconnect`) |
| `llm_client.py` | OpenRouter API calls (`generate_reply`, `summarize`, `extract_facts`) via `openai` SDK |
| `memory_manager.py` | Daily markdown log files: read, append, summarize-if-needed |
| `facts_manager.py` | Persistent facts store (`memory/facts.md`): upsert/remove user & server facts |
| `config.py` | All config from `.env` via `python-dotenv` |
| `system_prompt.txt` | Bot personality injected as system message |

## Key Flows

**Message handling** (`bot.py:on_message`):
1. Ignore own messages
2. Check for kill word — if matched by allowed user, send "Sayonara.", post offline message, close
3. If message is in a watched channel (and bot is not @mentioned): silently log to memory and extract facts, then return
4. Ignore messages that don't @mention the bot
5. Strip mention tags from user text
6. Load yesterday + today memory context + facts context → pass to LLM
7. Reply, then append exchange to today's log
8. Extract facts from the exchange; upsert user/server facts with cross-user correction guard
9. Summarize today's log if exchange count exceeds `SUMMARIZE_THRESHOLD`

**Facts memory** (`memory/facts.md`):
- Sections: `## User Facts` (keyed by display name) and `## Server Facts`
- Each fact bullet tagged with `<!-- msg:ID -->` for traceability
- Upsert deduplicates via: (1) explicit correction from LLM, (2) keyword overlap ≥ 2 non-stop tokens
- Users can delete facts by reacting ❌ to a bot reply — only the original message author can trigger removal

**Daily memory** (`memory/YYYY-MM-DD.md`):
- Appended per exchange with timestamp and channel
- Summarized in-place (raw backup saved as `.raw.md`) when `count > SUMMARIZE_THRESHOLD`
- Context window: yesterday + today only

**Status messages** (`bot.py:on_ready` / kill word handler):
- On ready: posts `ONLINE_MESSAGE` to `STATUS_CHANNEL` if both are configured
- On graceful shutdown (kill word): posts `OFFLINE_MESSAGE` to `STATUS_CHANNEL` before closing

## Environment Variables (`.env`)

| Variable | Default | Description |
|----------|---------|-------------|
| `DISCORD_TOKEN` | — | Bot token from Discord Developer Portal |
| `OPENROUTER_API_KEY` | — | OpenRouter API key |
| `MODEL_NAME` | `openai/gpt-4o-mini` | LLM model slug |
| `SUMMARIZE_THRESHOLD` | `50` | Exchanges before auto-summarize |
| `WATCH_CHANNELS` | `""` | Comma-separated channel names to silently observe |
| `KILL_WORD` | `""` | Message that triggers graceful shutdown |
| `KILL_WORD_ALLOWED_USER_ID` | `""` | Discord user ID allowed to use the kill word |
| `ONLINE_MESSAGE` | `"I'm back online!"` | Message posted to status channel on ready |
| `OFFLINE_MESSAGE` | `"Going offline now. Goodbye!"` | Message posted before graceful shutdown |
| `STATUS_CHANNEL` | `""` | Channel name for online/offline status messages |

## Running

```bash
pip install -r requirements.txt
python bot.py
```

Bot requires **MESSAGE CONTENT INTENT** enabled in Discord Developer Portal.

## Constraints & Conventions
- Bot only responds to direct @mentions; ignores all other messages (except watched channels and kill word)
- Watched channels: bot passively logs and extracts facts but never replies
- Discord reply limit: 2000 chars (truncated with `...`)
- Memory files are gitignored and stay local
- `memory/` is auto-created on first run
- Fallback reply string is defined in `llm_client.FALLBACK_REPLY` — exchanges using it are not logged
- Avoid circular imports: `llm_client` is lazily imported inside `memory_manager.summarize_if_needed`
- Cross-user fact corrections are blocked: bot ignores corrections where `correction["user"]` doesn't match the message author
- Fact removal via ❌ reaction is authorized only to the user the bot originally replied to

## Dependencies
- `discord.py >= 2.3`
- `openai >= 1.0` (used as OpenRouter client via `base_url`)
- `python-dotenv >= 1.0`
