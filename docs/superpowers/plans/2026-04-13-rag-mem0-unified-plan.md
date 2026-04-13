# RAG + Mem0 Unified Context Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement a unified RAG system that retrieves relevant context from guild documents and web content, with mem0 as semantic memory fallback.

**Architecture:** RAG retrieval (1000 token budget) runs first, fetching from guild docs (indexed files) and web content. If RAG returns empty, mem0 context provides fallback.

**Tech Stack:** Python, SQLite (FTS5), OpenAI embeddings, OpenRouter web search, mem0

---

## File Structure

| File | Responsibility |
|------|----------------|
| `indexer.py` | Extend with `retrieve()` for vector search |
| `rag_manager.py` | New - RAG orchestration (guild docs + web) |
| `bot.py` | Update to call RAG first, mem0 fallback |

---

### Task 1: Extend indexer.py with Retrieval

**Files:**
- Modify: `indexer.py`

- [ ] **Step 1: Add `_embed_query()` function**

Add after `_embed_texts()` (around line 88):

```python
async def _embed_query(query: str) -> list[float] | None:
    """Embed a single query. Returns None if unavailable."""
    if not config.EMBEDDING_API_KEY:
        return None
    try:
        from openai import AsyncOpenAI
        embed_client = AsyncOpenAI(
            api_key=config.EMBEDDING_API_KEY,
            base_url=config.EMBEDDING_BASE_URL,
        )
        response = await embed_client.embeddings.create(
            model=config.EMBEDDING_MODEL,
            input=[query],
        )
        return response.data[0].embedding
    except Exception as e:
        logger.warning(f"Query embedding failed: {e}")
        return None
```

- [ ] **Step 2: Add `retrieve()` function**

Add at end of file (after `index_guild()`):

```python
async def retrieve(query: str, limit_tokens: int = 600, db_path: str | None = None) -> list[dict]:
    """
    Search indexed chunks by semantic similarity or FTS5.
    
    Args:
        query: Search query
        limit_tokens: Max tokens for returned text (default 600)
        db_path: Optional path to index DB
    
    Returns:
        List of {"text": str, "file": str, "line_start": int, "line_end": int, "score": float}
    """
    if db_path is None:
        db_path = config.INDEX_PATH
    
    conn = _get_db(db_path)
    try:
        # Try semantic search with embeddings
        query_embedding = await _embed_query(query)
        if query_embedding:
            # Cosine similarity search
            emb_json = json.dumps(query_embedding)
            rows = conn.execute("""
                SELECT c.text, f.path, c.line_start, c.line_end,
                       (c.embedding <-> ?) AS similarity
                FROM chunks c
                JOIN files f ON c.file_id = f.id
                WHERE c.embedding IS NOT NULL
                ORDER BY similarity ASC
                LIMIT 20
            """, (emb_json,)).fetchall()
            
            if rows:
                results = []
                total_chars = 0
                char_budget = limit_tokens * 4  # rough: 4 chars per token
                for row in rows:
                    text = row[0]
                    if total_chars + len(text) > char_budget:
                        continue
                    results.append({
                        "text": text,
                        "file": row[1],
                        "line_start": row[2],
                        "line_end": row[3],
                        "score": 1.0 - row[4],  # convert distance to similarity
                    })
                    total_chars += len(text)
                return results
        
        # Fallback: FTS5 search
        rows = conn.execute("""
            SELECT c.text, f.path, c.line_start, c.line_end,
                   bm25(chunks_fts) AS rank
            FROM chunks_fts
            JOIN chunks c ON chunks_fts.rowid = c.id
            JOIN files f ON c.file_id = f.id
            WHERE chunks_fts MATCH ?
            ORDER BY rank
            LIMIT 20
        """, (query,)).fetchall()
        
        if not rows:
            return []
        
        results = []
        total_chars = 0
        char_budget = limit_tokens * 4
        for row in rows:
            text = row[0]
            if total_chars + len(text) > char_budget:
                continue
            results.append({
                "text": text,
                "file": row[1],
                "line_start": row[2],
                "line_end": row[3],
                "score": 1.0 / (1.0 + abs(row[4])),  # convert BM25 to similarity-like score
            })
            total_chars += len(text)
        return results
    finally:
        conn.close()
```

- [ ] **Step 3: Commit**

```bash
git add indexer.py
git commit -m "feat: add retrieve() function for semantic search"
```

---

### Task 2: Create rag_manager.py

**Files:**
- Create: `rag_manager.py`

- [ ] **Step 1: Write rag_manager.py**

```python
"""
RAG Manager - Retrieval-Augmented Generation for Discord bot.

Retrieves context from:
- Guild documents (indexed via indexer.py)
- Web content (OpenRouter web search + URL scraping)
"""

import asyncio
import logging
import re
from typing import Optional

import config
import indexer

logger = logging.getLogger(__name__)

_MAX_URL_LENGTH = 2000


async def initialize() -> None:
    """Initialize RAG system."""
    await indexer.init_db()
    logger.info("RAG system initialized")


async def retrieve_guild_docs(query: str, limit_tokens: int = 600) -> list[dict]:
    """
    Retrieve relevant chunks from indexed guild documents.
    """
    try:
        results = await indexer.retrieve(query, limit_tokens)
        return results
    except Exception as e:
        logger.error(f"Error retrieving guild docs: {e}")
        return []


async def search_web(query: str, limit_tokens: int = 400) -> list[dict]:
    """
    Search the web using OpenRouter web search.
    """
    if not config.LLM_API_KEY or "openrouter" not in config.LLM_BASE_URL:
        logger.debug("Web search not available - no OpenRouter")
        return []
    
    try:
        from openai import AsyncOpenAI
        client = AsyncOpenAI(
            api_key=config.LLM_API_KEY,
            base_url=config.LLM_BASE_URL,
        )
        response = await client.chat.completions.create(
            model=config.MODEL_NAME,
            messages=[
                {"role": "system", "content": "Search the web for information and provide a concise summary. Return the results in this format:\n\nTitle: <title>\nURL: <url>\nSummary: <brief summary>\n\nSearch query: " + query}
            ],
            tools=[{"type": "openrouter:web_search"}],
            tool_choice={"type": "web_search"},
        )
        
        output = response.choices[0].message.content or ""
        if not output:
            return []
        
        # Parse web search results
        results = []
        char_budget = limit_tokens * 4
        
        # Simple parsing - split by double newlines or markers
        entries = re.split(r'\n(?=Title:|URL:)', output)
        for entry in entries:
            if "URL:" in entry:
                match = re.search(r'Title: (.+)', entry)
                title = match.group(1).strip() if match else "No title"
                match = re.search(r'URL: (.+)', entry)
                url = match.group(1).strip() if match else ""
                match = re.search(r'Summary: (.+)', entry, re.DOTALL)
                summary = match.group(1).strip() if match else entry
                
                if len(summary) > char_budget // 3:
                    summary = summary[:char_budget // 3] + "..."
                
                results.append({
                    "title": title,
                    "url": url,
                    "content": summary,
                    "source": "web_search",
                })
        
        return results
    except Exception as e:
        logger.error(f"Web search error: {e}")
        return []


async def fetch_url(url: str, max_chars: int = 2000) -> str:
    """
    Fetch and extract text content from a URL.
    """
    import aiohttp
    
    if len(url) > _MAX_URL_LENGTH:
        logger.warning(f"URL too long: {url[:50]}...")
        return ""
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status != 200:
                    logger.warning(f"URL fetch failed: {resp.status}")
                    return ""
                
                text = await resp.text()
                
                # Basic HTML strip
                text = re.sub(r'<script[^>]*>.*?</script>', '', text, flags=re.DOTALL | re.IGNORECASE)
                text = re.sub(r'<style[^>]*>.*?</style>', '', text, flags=re.DOTALL | re.IGNORECASE)
                text = re.sub(r'<[^>]+>', '', text)
                text = re.sub(r'\s+', ' ', text)
                text = text.strip()
                
                if len(text) > max_chars:
                    text = text[:max_chars] + "..."
                
                return text
    except Exception as e:
        logger.error(f"URL fetch error: {e}")
        return ""


async def format_rag_context(query: str) -> str:
    """
    Build RAG context string combining guild docs + web results.
    Token budget: 1000 tokens (600 guild docs, 400 web)
    """
    parts = []
    
    # Guild docs (600 tokens)
    guild_docs = await retrieve_guild_docs(query, limit_tokens=600)
    if guild_docs:
        doc_parts = []
        for doc in guild_docs:
            lines = f"lines {doc['line_start']}-{doc['line_end']}"
            doc_parts.append(f"- [{doc['file']} {lines}]\n{doc['text']}")
        parts.append("## Guild Documents\n" + "\n\n".join(doc_parts))
    
    # Web results (400 tokens)
    web_results = await search_web(query, limit_tokens=400)
    if web_results:
        web_parts = []
        for result in web_results:
            content = result.get("content", "")
            if result.get("url"):
                content += f"\n(Source: {result['url']})"
            web_parts.append(f"- *{result['title']}*\n{content}")
        parts.append("## Web Search\n" + "\n\n".join(web_parts))
    
    if not parts:
        return "No RAG context available."
    
    return "\n\n".join(parts)
```

- [ ] **Step 2: Commit**

```bash
git add rag_manager.py
git commit -m "feat: add rag_manager.py for RAG orchestration"
```

---

### Task 3: Update bot.py for RAG Integration

**Files:**
- Modify: `bot.py`

- [ ] **Step 1: Import rag_manager**

Add after other imports (around line 10):

```python
import rag_manager
```

- [ ] **Step 2: Update on_ready to initialize RAG**

Modify `on_ready()` (around line 57-61):

```python
@client.event
async def on_ready():
    logger.info(f"Logged in as {client.user} (ID: {client.user.id})")
    indexer.init_db()
    await rag_manager.initialize()  # Add this
    await mem0_manager.initialize()
```

- [ ] **Step 3: Update on_message RAG logic**

Replace current RAG section (lines 212-218):

```python
    # RAG: retrieve relevant context (guild docs + web) first
    rag_context = ""
    if guild_id:
        rag_context = await rag_manager.format_rag_context(user_text)

    # Mem0: fallback if RAG is empty
    if rag_context.strip() in ("", "No RAG context available."):
        memory_context = mem0_manager.format_context_for_prompt(guild_id, user_id, user_text)
    else:
        memory_context = rag_context
```

- [ ] **Step 4: Commit**

```bash
git add bot.py
git commit -m "feat: integrate RAG before mem0 fallback"
```

---

### Task 4: Verify and Test

**Files:**
- Test: Manual verification

- [ ] **Step 1: Check imports work**

```bash
python -c "import rag_manager; import indexer; print('imports ok')"
```

- [ ] **Step 2: Test retrieve function**

Add a test file to memory/ directory, then test:

```bash
python -c "import asyncio; from indexer import retrieve; print(asyncio.run(retrieve('test query')))"
```

- [ ] **Step 3: Run bot and verify startup**

Start the bot and check no import errors in logs.

---

## Implementation Complete

**Summary of changes:**
- `indexer.py` - Added `retrieve()` for semantic/FTS5 search
- `rag_manager.py` - New file with RAG orchestration
- `bot.py` - RAG first, mem0 fallback