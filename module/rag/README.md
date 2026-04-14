# RAG Module

Retrieval-Augmented Generation system for providing context to LLM responses.

## What It Does

- Retrieves relevant context from indexed markdown files in `./memory/`
- Searches the web for current information via OpenRouter
- Fetches and extracts text from URLs
- Combines both sources into a unified context for LLM prompts

## Storage

```
memory/                    # Your knowledge base (markdown files)
  server-rules.md
  project-info.md
  faq.md

db/
  memory.sqlite            # Indexed chunks + embeddings
  mem0_db/                 # Mem0 conversational memory
```

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `KNOWLEDGE_PATH` | `./knowledge` | Directory containing markdown files |
| `INDEX_PATH` | `./db/memory.sqlite` | SQLite database for indexed content |
| `INDEX_AUTO_ON_START` | `true` | Auto-index on bot startup |
| `INDEX_WATCH_INTERVAL` | `30` | File watcher interval in seconds (0 = disabled) |

## Commands

| Command | Description | Who |
|---------|-------------|-----|
| `/index` | Re-index all memory files | Admin only |
| `/memory list` | Show indexed files with chunk counts | Everyone |

### Example Output

```
**Indexed files:**
- server-rules.md (42 chunks)
- project-info.md (15 chunks)
- faq.md (8 chunks)

Total: 3 files, 65 chunks, ~12.5 KB
```

## Functions

| Function | Description |
|----------|-------------|
| `initialize()` | Initialize the database for document indexing |
| `retrieve_guild_docs(query, limit_tokens)` | Query indexed documents |
| `search_web(query, limit_tokens)` | Search web via OpenRouter |
| `fetch_url(url, max_chars)` | Fetch and extract text from URL |
| `format_rag_context(query)` | Build combined context (600 tokens docs + 400 tokens web) |

## Usage

### Bot Startup (automatic)

```python
# Auto-indexing happens in bot.py on startup
# if INDEX_AUTO_ON_START=true
```

### Manual Re-indexing

```
/index
```

### Querying in Code

```python
from module.rag import initialize, format_rag_context

# On bot startup
initialize()

# When responding to user
context = await format_rag_context(user_query)
# Use context in LLM prompt
```

## Adding Knowledge

1. Create/edit `.md` files in `./memory/`
2. Run `/index` to re-index
3. Bot will retrieve relevant content automatically

### Tips

- Use clear headings (`#`, `##`) for better chunking
- Keep sections focused (20 lines per chunk)
- Update `/index` after editing files, or wait for file watcher

## Token Budget

- Guild documents: 600 tokens
- Web search results: 400 tokens
- Total: ~1000 tokens per query

## Requirements

- `KNOWLEDGE_PATH` directory exists (created automatically)
- For embeddings: `EMBEDDING_API_KEY` (falls back to FTS5 if not set)
- For web search: OpenRouter API key
