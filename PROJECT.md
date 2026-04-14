# Discord Bot AI - Project Summary

## Overview
A Discord bot with AI-powered conversation using LLM (OpenRouter/Ollama), semantic memory (mem0), RAG for guild documents, and interactive features.

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
    └── auto_post/ (proactive messages)
```

## Core Components

### 1. bot.py (Main)
- Discord client with `message_content`, `reactions`, `members` intents
- Commands: `/index`, `/memory`
- `on_message`: handles mentions + watch channels
- `on_raw_reaction_add`: X reaction removal (stub)
- Attachment processing: text, images, PDFs

### 2. llm_client.py
- AsyncOpenAI wrapper for OpenRouter/Ollama
- System prompt from `system_prompt.txt`
- Web search tool via OpenRouter

### 3. mem0_manager.py
- Mem0 Memory with ChromaDB backend
- Per-guild memory (user_id = guild_id)
- In-memory recent buffer (20 messages)
- Semantic search with threshold 0.6

### 4. indexer.py
- SQLite FTS5 full-text search
- Optional OpenAI embeddings (embedding-3-small)
- Sliding window chunking (20 lines, 4 overlap)
- File watcher for auto-reindex

### 5. module/rag/
- Guild doc retrieval (mem0 → indexer fallback)
- Web search via OpenRouter tools
- URL fetch + strip HTML

### 6. module/meme_reaction/
- MemeManager: Giphy/Tenor API search
- TriggerDecider: keywords + LLM sentiment

### 7. module/auto_post/
- Random-trigger proactive messages
- LLM-generated, memory-contextual

## Configuration (config.py)

| Variable | Default | Description |
|----------|---------|-------------|
| DISCORD_TOKEN | required | Discord bot token |
| LLM_BASE_URL | openrouter.ai/api/v1 | LLM endpoint |
| LLM_API_KEY | required | API key |
| MODEL_NAME | openai/gpt-4o-mini | Model |
| WATCH_CHANNELS | "" | Silent observe channels |
| KNOWLEDGE_PATH | ./knowledge | .md files for RAG |
| INDEX_PATH | ./db/memory.sqlite | FTS5 index |
| EMBEDDING_* | optional | Embedding config |
| AUTO_POST_* | disabled | Proactive messages |
| MEME_* | disabled | GIF reactions |
| KILL_WORD | "" | Stop bot word |

## Key Behaviors

1. **Mentioned**: Responds to @bot with LLM + RAG context
2. **Watch channels**: Silent observe, memory capture, auto-post triggers
3. **Watch + meme**: Random GIF reply on laughter keywords/sentiment
4. **Kill word**: Stop bot (allowed user only)
5. **Status**: Online/offline messages to channel

## Dependencies
- discord.py
- openai
- mem0
- aiohttp
- python-dotenv
- pypdf (PDF extraction)

## Database
- `db/memory.sqlite` - FTS5 index (files, chunks tables)
- `index/mem0_db/` - ChromaDB vectors
- `db/mem0_db/` - Production ChromaDB

## Commands
- `/index` - Re-index knowledge files (admin)
- `/memory` - List indexed files