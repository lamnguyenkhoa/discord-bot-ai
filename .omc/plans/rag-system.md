# Plan: RAG Knowledge System

**Date:** 2026-04-02
**Complexity:** MEDIUM (1 new file, 4 files changed)
**Ambiguity:** ~10%

---

## Context

The bot currently stores small extracted facts in `memory/facts.md` (loaded in full on every request). There is no mechanism to store or retrieve larger bodies of knowledge (game rules, streamer lore, etc.). This plan adds a RAG layer:

- `memory/facts.md` keeps its role as a lightweight index and small-tidbit store
- A new ChromaDB-backed store holds chunked document knowledge
- Ingest is triggered by uploading a `.txt` or `.md` file to Discord and @mentioning the bot with "learn" in the message
- Retrieval is similarity-gated: only injected into context when the query is relevant

---

## RALPLAN-DR Summary

### Principles
1. **Minimal extra LLM calls** — embed once at ingest, embed once at query time; no extra calls elsewhere
2. **facts.md as directory** — after ingest, upsert one fact line pointing to the RAG source (topic + chunk count)
3. **Graceful no-op on irrelevance** — if no chunk exceeds the similarity threshold, skip RAG entirely; bot behaves exactly as before
4. **Replace on re-ingest** — uploading a file with the same source name replaces all old chunks; prevents stale knowledge
5. **Fail-safe** — ChromaDB or embed errors never crash the bot; fall back to no RAG context

### Decision Drivers
1. **Retrieval cost** — embedding per query is unavoidable; extra LLM call to judge relevance is not
2. **Persistence** — ChromaDB PersistentClient stores to disk; survives restarts without manual save/load
3. **Integration simplicity** — the existing `AsyncOpenAI` client in `llm_client.py` already supports the embeddings API; no new API client needed

### Options Considered

**Option A: ChromaDB + OpenRouter embeddings (CHOSEN)**
- Persistent local store; cosine similarity search built-in
- Uses existing OpenAI-compatible client for embeddings (`client.embeddings.create`)
- Adds one dependency (`chromadb`)
- Relevance gate: filter by cosine distance threshold (distance < 1 − threshold)

**Option B: FAISS + numpy**
- Fast at scale; no server needed
- Requires manual save/load of index on disk; more brittle on Windows path handling
- Adds two dependencies (`faiss-cpu`, `numpy`)
- Invalidated: more operational complexity than ChromaDB for no speed benefit at this scale

**Option C: sqlite-vec**
- Minimal dependencies (SQLite extension)
- Less mature Python API; less documentation
- Invalidated: ChromaDB is better supported and more battle-tested for this exact use case

---

## Work Objectives

1. Ingest `.txt`/`.md` files uploaded to Discord via @mention + "learn" keyword
2. Chunk, embed, and store them in ChromaDB with source metadata
3. Add a directory entry to `facts.md` after each ingest
4. At reply time, embed the user query, retrieve relevant chunks (above threshold), inject into prompt
5. Replace existing chunks when a source is re-ingested

## Guardrails

**Must Have:**
- Ingest triggered only by @mention with file attachment + "learn" keyword (case-insensitive)
- Only `.txt` and `.md` attachments accepted; others silently ignored with a user reply
- Source name derived from filename stem (e.g. `lol-rules.txt` → `lol-rules`)
- facts.md updated with: `RAG:[source]: [N] chunks` after each ingest
- Retrieval skipped entirely if top similarity below threshold (no empty context injected)
- Re-ingest of same source name replaces all previous chunks for that source
- All ChromaDB and embed operations wrapped in try/except; errors logged, bot continues

**Must NOT Have:**
- No extra LLM call to judge relevance (similarity threshold is the gate)
- No PDF support in v1 (follow-up)
- No slash commands
- No changes to `memory_manager.py` or `facts_manager.py` existing functions

---

## Task Flow

```
Step 1: config.py           — add RAG config vars
    |
Step 2: llm_client.py       — add embed_text() function
    |
Step 3: rag_manager.py      — new file: ingest, chunk, query
    |
Step 4: bot.py              — wire ingest command + RAG retrieval into on_message
    |
Step 5: requirements.txt    — add chromadb
    |
Step 6: Manual verification
```

Steps 1 and 2 are independent and can be done in parallel.

---

## Detailed TODOs

### Step 1: `config.py` additions

Add to the bottom of `config.py`:

```python
# RAG
RAG_DIR = os.path.join(MEMORY_DIR, "rag")
RAG_COLLECTION = "bot_knowledge"
RAG_EMBED_MODEL = os.getenv("RAG_EMBED_MODEL", "openai/text-embedding-3-small")
RAG_CHUNK_SIZE = int(os.getenv("RAG_CHUNK_SIZE", "1500"))   # chars
RAG_CHUNK_OVERLAP = int(os.getenv("RAG_CHUNK_OVERLAP", "200"))  # chars
RAG_TOP_K = int(os.getenv("RAG_TOP_K", "3"))
RAG_SIMILARITY_THRESHOLD = float(os.getenv("RAG_SIMILARITY_THRESHOLD", "0.75"))
```

**Acceptance criteria:**
- All vars have sensible defaults; none crash if missing from `.env`
- `RAG_DIR` nests under `MEMORY_DIR` so it stays gitignored

---

### Step 2: `llm_client.py` — add `embed_text`

Add after `load_system_prompt()`:

```python
async def embed_text(text: str) -> list:
    """Embed text using the configured embedding model via OpenRouter.
    Returns the embedding vector. Raises on error (caller handles)."""
    response = await client.embeddings.create(
        model=config.RAG_EMBED_MODEL,
        input=text,
    )
    return response.data[0].embedding
```

- Uses the existing module-level `AsyncOpenAI` client (`client`) — no new client needed
- Does NOT catch exceptions here; callers in `rag_manager.py` catch and handle
- Must be `async` because it awaits the API call

**Acceptance criteria:**
- Returns a list of floats
- Uses `config.RAG_EMBED_MODEL` (not hardcoded)
- No exception handling here — caller handles

---

### Step 3: `rag_manager.py` (new file)

```python
import asyncio
import logging
import os
import chromadb
import config
import llm_client

logger = logging.getLogger(__name__)

_client = None
_collection = None
_rag_lock = asyncio.Lock()


def _get_collection():
    global _client, _collection
    if _collection is None:
        os.makedirs(config.RAG_DIR, exist_ok=True)
        _client = chromadb.PersistentClient(path=config.RAG_DIR)
        _collection = _client.get_or_create_collection(
            name=config.RAG_COLLECTION,
            metadata={"hnsw:space": "cosine"},
        )
    return _collection
```

**`_chunk_text(text, chunk_size, overlap) -> list[str]`:**
- Split `text` into chunks of at most `chunk_size` chars with `overlap` char overlap
- Split on paragraph boundaries (`\n\n`) first; accumulate paragraphs until chunk_size reached, then start a new chunk with the last `overlap` chars carried over
- Minimum chunk length: 50 chars (skip empty/tiny chunks)

**`async def ingest(text: str, source_name: str) -> int`:**
1. Acquire `_rag_lock`
2. Call `_get_collection()`
3. Delete any existing documents where `metadata.source == source_name`:
   - `col.delete(where={"source": source_name})`
4. Chunk the text using `_chunk_text(text, config.RAG_CHUNK_SIZE, config.RAG_CHUNK_OVERLAP)`
5. For each chunk, call `await llm_client.embed_text(chunk)` to get embedding
6. Add all chunks in one batch: `col.add(documents=chunks, embeddings=embeddings, ids=ids, metadatas=metadatas)`
   - IDs: `f"{source_name}_{i}"` for each chunk index `i`
   - Metadata: `{"source": source_name}`
7. Release lock; return chunk count
8. On any exception: log error, return 0

**`async def query(query_text: str) -> str | None`:**
1. Call `_get_collection()`
2. Embed `query_text` via `await llm_client.embed_text(query_text)`
3. Query: `col.query(query_embeddings=[embedding], n_results=config.RAG_TOP_K, include=["documents", "distances"])`
4. Filter results: keep only chunks where `distance < (1 - config.RAG_SIMILARITY_THRESHOLD)`
5. If no results pass the filter: return `None`
6. Format passing chunks:
   ```
   [source: {metadata.source}]
   {chunk text}
   ---
   ```
   Join with newline, return the string
7. On any exception (ChromaDB error, embed error): log and return `None`

**Acceptance criteria:**
- `ingest("...", "lol-rules")` called twice deletes old chunks then adds new ones (no duplicates)
- `query("how many players in LoL")` returns formatted chunk text when relevant content exists
- `query("what did you eat for lunch")` returns `None` when no chunk exceeds threshold
- Empty or whitespace-only text passed to `ingest` returns 0 without crashing
- All ChromaDB/embed errors are caught; no exception propagates to caller

---

### Step 4: `bot.py` — ingest command + RAG retrieval

**4a. Ingest command detection** (in `on_message`, BEFORE the existing `client.user not in message.mentions` check):

After stripping the mention from user_text, check for ingest command:

```python
# RAG ingest: @mention + file attachment + "learn" keyword
if client.user in message.mentions and message.attachments and "learn" in user_text.lower():
    for attachment in message.attachments:
        name = attachment.filename.lower()
        if not (name.endswith(".txt") or name.endswith(".md")):
            await message.reply(f"I can only learn from .txt or .md files. `{attachment.filename}` was skipped.")
            continue
        try:
            raw = await attachment.read()
            text = raw.decode("utf-8", errors="replace")
        except Exception as e:
            logger.error(f"Failed to read attachment {attachment.filename}: {e}")
            await message.reply(f"Failed to read `{attachment.filename}`.")
            continue
        source_name = os.path.splitext(attachment.filename)[0]
        count = await rag_manager.ingest(text, source_name)
        if count > 0:
            await facts_manager.upsert_server_fact(
                f"RAG:{source_name}: {count} chunks stored", msg_id=message.id
            )
            await message.reply(f"Learned `{source_name}` — {count} chunks stored.")
        else:
            await message.reply(f"Failed to ingest `{attachment.filename}`. Check logs.")
    return  # Don't fall through to normal reply flow
```

Add `import rag_manager` to imports.
Add `import os` is already present.

**4b. RAG retrieval in normal reply flow** (in `on_message`, after `memory_context` and `facts_context` are loaded, before `generate_reply`):

```python
rag_context = await rag_manager.query(user_text)
```

Then pass `rag_context` to `generate_reply`:

```python
reply = await llm_client.generate_reply(
    user_message=user_text,
    memory_context=memory_context,
    channel_name=str(message.channel),
    facts_context=facts_context,
    rag_context=rag_context or "",
)
```

**4c. Update `generate_reply` in `llm_client.py`** to accept and inject `rag_context`:

```python
async def generate_reply(user_message, memory_context, channel_name, facts_context="", rag_context="") -> str:
    system_content = load_system_prompt() + "\n\n## Recent Memory\n" + memory_context
    if facts_context:
        system_content += "\n\n## Persistent Memory\n" + facts_context
    if rag_context:
        system_content += "\n\n## Retrieved Knowledge\n" + rag_context
    ...
```

**Acceptance criteria:**
- @mention + `.txt` attachment + "learn" triggers ingest, not normal reply
- @mention + `.pdf` attachment + "learn" replies with unsupported message
- @mention + attachment but no "learn" keyword falls through to normal reply flow
- After ingest, facts.md has a `RAG:{source}: N chunks` entry
- Normal @mention without attachment queries RAG; if relevant, context appears in prompt
- Normal @mention without attachment queries RAG; if irrelevant, `rag_context` is empty, prompt unchanged

---

### Step 5: `requirements.txt`

Add:
```
chromadb>=0.5,<1.0
```

---

### Step 6: Manual Verification

| # | Test | Steps | Expected |
|---|------|-------|----------|
| 1 | Ingest .txt | Upload `lol-rules.txt` (paste some game rules), @bot learn | Reply confirms N chunks; facts.md has `RAG:lol-rules: N chunks` |
| 2 | Relevant query | @bot "how many kills to get an S rank in LoL?" | Reply uses retrieved chunk context |
| 3 | Irrelevant query | @bot "what did you have for dinner?" | No RAG context in prompt (verify via debug log) |
| 4 | Re-ingest | Upload `lol-rules.txt` again with updated content, @bot learn | Old chunks replaced; no duplicates in ChromaDB |
| 5 | Unsupported file | Upload `.pdf` + @bot learn | Bot replies "can only learn from .txt or .md" |
| 6 | Bot restart | Restart bot, ask a question relevant to ingested knowledge | Retrieval still works (ChromaDB persisted to disk) |
| 7 | Ingest fail-safe | Temporarily set invalid embed model, @bot learn | Bot replies with failure message; no crash |
| 8 | RAG fail-safe | Delete RAG dir mid-session, ask question | query() logs error, returns None; bot replies normally |

---

## Success Criteria

- [ ] File ingest triggered by @mention + attachment + "learn" keyword
- [ ] Chunks stored in ChromaDB under `memory/rag/`
- [ ] facts.md updated with directory entry per source
- [ ] Re-ingest replaces old chunks (no accumulation)
- [ ] RAG context injected only when similarity threshold exceeded
- [ ] Bot replies unchanged when RAG returns no relevant results
- [ ] ChromaDB persists across restarts
- [ ] All errors caught; bot never crashes due to RAG failure
- [ ] `.md` and `.txt` supported; other formats rejected with user message

---

## ADR

**Decision:** ChromaDB + OpenRouter embeddings API, similarity-threshold retrieval gate

**Drivers:** Minimal extra LLM calls, persistent local store, integration with existing client

**Alternatives considered:**
- FAISS + numpy — more manual persistence, two extra deps, no benefit at this scale
- sqlite-vec — less mature, less documentation

**Why chosen:** ChromaDB handles persistence and cosine search natively. The existing `AsyncOpenAI` client already speaks the embeddings API. One dependency added for significant capability gain.

**Consequences:**
- `chromadb` adds ~50MB to install size
- First ingest requires one embed API call per chunk (small cost)
- PDF ingestion not supported in v1

**Follow-ups:**
- PDF support via `pypdf` or `pdfminer`
- Allow topic name override in the "learn" command (e.g. `@bot learn as "LoL Rules"`)
- Per-source refresh command (`@bot forget lol-rules`)
