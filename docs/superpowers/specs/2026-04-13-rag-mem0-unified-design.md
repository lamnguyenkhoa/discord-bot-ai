# RAG + Mem0 Unified Context Design

**Date:** 2026-04-13
**Status:** Approved

## Overview

Implement a unified RAG system that retrieves relevant context from guild documents and web content, with mem0 as a semantic memory fallback. The goal is low token usage while providing accurate, relevant context for bot replies.

## Architecture

```
User Message
    │
    ├──► RAG Retrieval (1000 token budget)
    │       ├── Guild docs → indexer.py (vector + FTS5 search)
    │       └── Web content → OpenRouter web search + URL scraping
    │
    └──► Mem0 Context (fallback)
            ├── Guild memories (semantic search)
            └── User memories (semantic search)
```

## Components

### 1. indexer.py - Extend for Retrieval

**Current:** `index_file()`, `index_guild()`, `init_db()`

**New functions:**
- `retrieve(query: str, limit_tokens: int = 600) -> list[dict]`
  - Search indexed chunks by semantic similarity
  - Return list of `{"text": str, "file": str, "lines": str, "score": float}`
  - Use embeddings if available, FTS5 fallback
  - Budget for returned text: ~600 tokens

### 2. rag_manager.py - New File

**Functions:**

```python
async def initialize() -> None:
    """Initialize RAG system (call indexer.init_db())."""
    await indexer.init_db()


async def retrieve_guild_docs(query: str, limit_tokens: int = 600) -> list[dict]:
    """
    Retrieve relevant chunks from indexed guild documents.
    
    Args:
        query: Search query (user message)
        limit_tokens: Max tokens for returned text (default 600)
    
    Returns:
        List of {"text": str, "file": str, "line_start": int, "line_end": int, "score": float}
    """
    pass


async def search_web(query: str, limit_tokens: int = 400) -> list[dict]:
    """
    Search the web using OpenRouter web search.
    
    Args:
        query: Search query
        limit_tokens: Max tokens for returned text (default 400)
    
    Returns:
        List of {"title": str, "url": str, "content": str, "source": str}
    """
    pass


async def fetch_url(url: str, max_chars: int = 2000) -> str:
    """
    Fetch and extract text content from a URL.
    
    Args:
        url: URL to fetch
        max_chars: Max characters to return (default 2000)
    
    Returns:
        Extracted text content
    """
    pass


async def format_rag_context(query: str) -> str:
    """
    Build RAG context string for prompt injection.
    Combines guild docs + web results within 1000 token budget.
    
    Args:
        query: Search query (user message)
    
    Returns:
        Formatted context string with RAG results
    """
    pass
```

### 3. bot.py - Integration

**Current:**
```python
# RAG: retrieve relevant memory chunks for context
if guild_id:
    memory_context = mem0_manager.format_context_for_prompt(guild_id, user_id, user_text)
else:
    memory_context = ""
```

**Updated:**
```python
# RAG: retrieve relevant context (guild docs + web)
rag_context = ""
if guild_id:
    rag_context = await rag_manager.format_rag_context(user_text)

# Mem0: fallback if RAG is empty
if rag_context.strip() in ("", "No RAG context available."):
    memory_context = mem0_manager.format_context_for_prompt(guild_id, user_id, user_text)
else:
    memory_context = rag_context
```

## Token Allocation

| Source | Budget |
|--------|--------|
| Guild docs (RAG) | 600 tokens |
| Web results (RAG) | 400 tokens |
| Mem0 fallback | Only if RAG empty |

## Data Storage

- `index/memory.sqlite` - Existing embeddings + FTS5 index
- `index/mem0_db/` - Existing mem0 ChromaDB
- No new storage required

## Error Handling

| Scenario | Behavior |
|----------|----------|
| Embeddings unavailable | Use FTS5-only search |
| Web search fails | Skip web, use guild docs only |
| Empty RAG results | Append mem0 context |
| URL fetch fails | Skip URL, continue with other results |

## Dependencies

- `config.py` - Already configured with EMBEDDING_* settings
- `llm_client.py` - Uses OpenRouter for web search
- `indexer.py` - Already indexes files

## Testing

1. Retrieve guild docs - search indexed file, return top chunks
2. Web search - query returns title + snippet
3. URL fetch - extract text from URL
4. Format context - combine within token budget
5. Integration - RAG first, mem0 fallback

## Implementation Order

1. Extend indexer.py with `retrieve()` function
2. Create rag_manager.py with all functions
3. Update bot.py to call RAG first
4. Test end-to-end