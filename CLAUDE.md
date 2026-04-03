# Discord Bot AI — Project Guide

## Overview
A Discord bot that responds when @mentioned, powered by an LLM via OpenRouter (or any OpenAI-compatible API). Maintains rolling daily conversation logs per user, auto-summarizes and flushes them when they grow large, builds persistent facts memory, and uses hybrid RAG (vector + FTS5) to retrieve relevant context.

## Architecture

| File | Role |
|------|------|
| `bot.py` | Discord client, event handlers (`on_ready`, `on_message`, `on_raw_reaction_add`, `on_disconnect`) |
| `llm_client.py` | LLM API calls: `generate_reply`, `summarize`, `extract_facts`, `flush_memory` via `openai` SDK |
| `memory_manager.py` | Per-user daily markdown logs: read, append, summarize-if-needed, flush-if-needed |
| `facts_manager.py` | Persistent facts store (markdown files): upsert/remove user & server facts with dedup |
| `indexer.py` | Chunking + vector embedding of memory files into SQLite (`index/memory.sqlite`) |
| `search.py` | Hybrid RAG search: 70% vector cosine + 30% FTS5 keyword, falls back to FTS5-only |
| `config.py` | All config from `.env` via `python-dotenv` |
| `system_prompt.txt` | Bot personality injected as system message |

## Memory Directory Structure

```
memory/
  users/{user_id}/
    MEMORY.md              # persistent long-term facts (flushed from logs)
    logs/{YYYY-MM-DD}.md   # daily conversation log
  guilds/{guild_id}/
    MEMORY.md              # server-level facts

index/
  memory.sqlite            # SQLite: chunked text + embeddings (BLOB JSON) + FTS5 virtual table
```

## Key Flows

**Message handling** (`bot.py:on_message`):
1. Ignore own messages
2. Check for kill word — if matched by allowed user, send "Sayonara.", post offline message, close
3. If message is in a watched channel (and bot is not @mentioned): silently log to memory and extract facts, then return
4. Ignore messages that don't @mention the bot
5. Strip mention tags from user text; process attachments (images, text files, PDFs)
6. RAG search via `search.search()` → top-K relevant memory chunks
7. Load facts via `facts_manager.load_facts()` → user + guild facts string
8. Call `llm_client.generate_reply(user_message, memory_context, channel, facts_context, image_urls)`
9. Reply (truncated to 2000 chars); append exchange to today's log via `memory_manager.append_exchange()`
10. Extract facts from exchange via `llm_client.extract_facts()`; upsert with cross-user correction guard
11. Async post-reply: `memory_manager.flush_memory_if_needed()` (threshold: 20), `summarize_if_needed()` (threshold: 50), `indexer.index_user()` + `indexer.index_guild()`

**Facts memory** (markdown files in `memory/`):
- User facts: `memory/users/{user_id}/MEMORY.md`
- Guild facts: `memory/guilds/{guild_id}/MEMORY.md`
- Each fact bullet tagged with `<!-- msg:ID -->` for traceability
- Upsert deduplicates via: (1) explicit correction from LLM (old_fact substring replace), (2) keyword overlap ≥ 2 non-stop tokens (replaces best match)
- Users can delete facts by reacting ❌ to a bot reply — only the original message author can trigger removal
- Thread-safe writes via `AsyncLock` in `facts_manager`

**Daily memory** (`memory/users/{user_id}/logs/YYYY-MM-DD.md`):
- Appended per exchange: `### [HH:MM] #{channel}\nUser (name): msg\nBot: reply\n`
- `flush_memory_if_needed`: when exchanges > `MEMORY_FLUSH_THRESHOLD` (20), extracts bullet facts → appends to `MEMORY.md`
- `summarize_if_needed`: when exchanges > `SUMMARIZE_THRESHOLD` (50), summarizes in-place (raw backup saved as `.raw.md`)
- Context window passed to LLM: RAG search results from full memory history

**Hybrid RAG search** (`search.py`):
- Vector search (cosine similarity on OpenAI embeddings) weighted 70%
- FTS5 keyword search weighted 30%
- Falls back to FTS5-only if embeddings unavailable
- Scoped to requesting user's directory + guild directory
- Indexing: sliding window chunks (20 lines, 4-line overlap), change-detected via content hash

**Attachment handling** (`bot.py:process_attachments`):
- Images (`.png .jpg .jpeg .gif .webp`): URL passed to vision-capable LLM
- Text files (`.txt .md .py .js .ts .json .yaml .yml .csv .html .css .xml .log .sh .c .cpp .h .java .rb .go .rs .toml .ini .cfg`): downloaded, truncated to `ATTACHMENT_MAX_CHARS`
- PDFs (`.pdf`): extracted via `pypdf`, limited by `PDF_MAX_BYTES` and `PDF_MAX_PAGES`
- All extracted text appended to `user_text` before LLM call

**Status messages** (`bot.py:on_ready` / kill word handler):
- On ready: posts `ONLINE_MESSAGE` to `STATUS_CHANNEL` if both are configured
- On graceful shutdown (kill word): posts `OFFLINE_MESSAGE` to `STATUS_CHANNEL` before closing

## Environment Variables (`.env`)

| Variable | Default | Description |
|----------|---------|-------------|
| `DISCORD_TOKEN` | — | Bot token from Discord Developer Portal |
| `OPENROUTER_API_KEY` | — | OpenRouter API key (alias for `LLM_API_KEY`) |
| `LLM_API_KEY` | — | LLM API key (alternative to `OPENROUTER_API_KEY`) |
| `LLM_BASE_URL` | `https://openrouter.ai/api/v1` | LLM API base URL (change for Ollama etc.) |
| `MODEL_NAME` | `openai/gpt-4o-mini` | LLM model slug |
| `WEB_SEARCH_ENABLED` | `true` | Enable OpenRouter web search plugin |
| `SUMMARIZE_THRESHOLD` | `50` | Exchanges before auto-summarize |
| `MEMORY_FLUSH_THRESHOLD` | `20` | Exchanges before flushing facts to MEMORY.md |
| `MEMORY_SEARCH_TOP_K` | `5` | Number of RAG chunks returned per search |
| `ATTACHMENT_MAX_BYTES` | `524288` | Max file size for text attachments (512 KB) |
| `ATTACHMENT_MAX_CHARS` | `8000` | Max extracted chars passed to LLM from any attachment |
| `PDF_MAX_BYTES` | `5242880` | Max file size for PDF attachments (5 MB) |
| `PDF_MAX_PAGES` | `20` | Max pages extracted from a PDF |
| `INDEX_PATH` | `./index/memory.sqlite` | Path to SQLite search index |
| `EMBEDDING_API_KEY` | (LLM_API_KEY) | API key for embeddings (defaults to LLM key) |
| `EMBEDDING_BASE_URL` | `https://api.openai.com/v1` | Embeddings API base URL |
| `EMBEDDING_MODEL` | `text-embedding-3-small` | Embedding model name |
| `WATCH_CHANNELS` | `""` | Comma-separated channel names to silently observe |
| `KILL_WORD` | `""` | Message that triggers graceful shutdown |
| `KILL_WORD_ALLOWED_USER_ID` | `""` | Discord user ID allowed to use the kill word |
| `ONLINE_MESSAGE` | `"I'm back online!"` | Message posted to status channel on ready |
| `OFFLINE_MESSAGE` | `"Going offline now. Goodbye!"` | Message posted before graceful shutdown |
| `STATUS_CHANNEL` | `""` | Channel name for online/offline status messages |
| `MEMORY_BASE_PATH` | `./memory` | Root directory for all memory files |

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
- Memory files are gitignored and stay local; `memory/` and `index/` are auto-created on first run
- Fallback reply string is defined in `llm_client.FALLBACK_REPLY` — exchanges using it are not logged
- **Circular imports**: `llm_client` is lazily imported inside `memory_manager` (lines 107, 123) to avoid circular deps
- **Concurrency**: `facts_manager` uses `AsyncLock` for thread-safe file writes
- **Cross-user fact corrections blocked**: bot ignores corrections where `correction["user"]` doesn't match the message author
- Fact removal via ❌ reaction is authorized only to the user the bot originally replied to
- **Embeddings are optional**: both `indexer.py` and `search.py` gracefully fall back to FTS5-only if embedding API is unavailable
- `os.environ.pop("SSL_CERT_FILE", None)` at top of `bot.py` — workaround for local/Ollama SSL issues

## Dependencies
- `discord.py >= 2.3`
- `openai >= 1.0` (used as OpenRouter/Ollama client via `base_url`)
- `python-dotenv >= 1.0`
- `pypdf >= 4.0` (PDF text extraction)
- `aiohttp` (attachment downloads)
