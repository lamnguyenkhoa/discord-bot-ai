# RAG Module

Retrieval-Augmented Generation system for providing context to LLM responses.

## What It Does

- Retrieves relevant context from indexed guild documents
- Searches the web for current information via OpenRouter
- Fetches and extracts text from URLs
- Combines both sources into a unified context for LLM prompts

## Functions

| Function | Description |
|----------|-------------|
| `initialize()` | Initialize the database for document indexing |
| `retrieve_guild_docs(query, limit_tokens)` | Query indexed guild documents |
| `search_web(query, limit_tokens)` | Search web via OpenRouter |
| `fetch_url(url, max_chars)` | Fetch and extract text from URL |
| `format_rag_context(query)` | Build combined context (600 tokens docs + 400 tokens web) |

## Usage

```python
from module.rag import initialize, format_rag_context

# On bot startup
initialize()

# When responding to user
context = await format_rag_context(user_query)
# Use context in LLM prompt
```

## Requirements

- OpenRouter API key in `LLM_API_KEY` with base URL containing "openrouter"
- Guild docs indexed via `indexer.py`

## Configuration

No module-specific config. Uses existing:
- `LLM_API_KEY` - Must be OpenRouter key
- `LLM_BASE_URL` - Must contain "openrouter"
- `ModelName` - For web search calls

## Token Budget

- Guild documents: 600 tokens
- Web search results: 400 tokens
- Total: ~1000 tokens per query