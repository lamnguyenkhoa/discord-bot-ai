# Memory & RAG System — Discord Bot Implementation Spec

> **Purpose:** Implement an OpenClaw-inspired persistent memory + RAG system for a Discord bot.
> Feed this file to Claude Code and ask it to implement the system described below.

---

## What We're Building

A Discord bot that remembers conversations across sessions using:
- **Markdown files** as the source of truth for memory (human-readable, editable)
- **SQLite** as the search index (local, no external DB needed)
- **Hybrid search** (vector similarity + keyword/BM25) for retrieval
- **Per-user and per-guild memory** scoped to Discord identities

---

## File Structure to Create

```
bot/
├── memory/
│   ├── users/
│   │   └── {userId}/
│   │       ├── MEMORY.md          # Long-term facts about this user
│   │       ├── USER.md            # User preferences & profile
│   │       └── logs/
│   │           └── YYYY-MM-DD.md  # Daily conversation logs
│   └── guilds/
│       └── {guildId}/
│           └── MEMORY.md          # Shared guild-level memory
├── index/
│   └── memory.sqlite              # SQLite search index
├── memoryManager.js               # Core memory read/write logic
├── indexer.js                     # Chunking + embedding + SQLite indexer
├── search.js                      # Hybrid search (vector + BM25)
└── bot.js                         # Discord bot entry point
```

---

## SQLite Schema

Create these tables in `memory.sqlite`:

```sql
-- Tracks indexed files to avoid redundant re-indexing
CREATE TABLE files (
  id INTEGER PRIMARY KEY,
  path TEXT UNIQUE NOT NULL,
  mtime INTEGER NOT NULL,
  size INTEGER NOT NULL,
  content_hash TEXT NOT NULL
);

-- Stores text chunks with their embeddings
CREATE TABLE chunks (
  id INTEGER PRIMARY KEY,
  file_id INTEGER REFERENCES files(id) ON DELETE CASCADE,
  text TEXT NOT NULL,
  line_start INTEGER,
  line_end INTEGER,
  embedding BLOB  -- JSON-serialized float array
);

-- Full-text search virtual table
CREATE VIRTUAL TABLE chunks_fts USING fts5(
  text,
  content='chunks',
  content_rowid='id'
);
```

---

## Core Modules to Implement

### 1. `memoryManager.js` — Read & Write Memory

**Responsibilities:**
- `writeLog(userId, text)` — Append a message to today's daily log (`logs/YYYY-MM-DD.md`)
- `writeLongTermMemory(userId, fact)` — Append a fact to the user's `MEMORY.md`
- `writeUserProfile(userId, preference)` — Update `USER.md` with user preferences
- `readMemoryFiles(userId)` — Return all Markdown file paths for a user
- `flushMemory(userId, conversationText)` — Before context gets too long, prompt the LLM to extract important facts and write them to `MEMORY.md` (silent turn — user doesn't see this)

**Key behavior:** After every bot response, append both the user message and bot reply to today's log file. Before a conversation exceeds ~80% of the context window, trigger `flushMemory`.

---

### 2. `indexer.js` — Chunking + Embedding + Indexing

**Responsibilities:**
- `indexFile(filePath)` — Read a Markdown file, chunk it, embed it, store in SQLite
- `indexAll(userId)` — Re-index all memory files for a user
- Skip files where `mtime` and `content_hash` haven't changed (check `files` table first)

**Chunking strategy (sliding window):**
- Split file by lines
- Chunk size: ~20 lines per chunk
- Overlap: 4 lines between consecutive chunks (overlap preservation)
- Store `line_start` and `line_end` per chunk in the `chunks` table

**Embedding:**
- Use OpenAI `text-embedding-3-small` (or any available provider)
- Serialize the embedding float array as JSON and store in the `embedding` column
- Batch embed multiple chunks in a single API call to reduce cost

**Fallback:** If no embedding provider is available, skip vector indexing and fall back to FTS5-only search.

---

### 3. `search.js` — Hybrid Search

**Responsibilities:**
- `search(userId, query, topK = 5)` — Return the top-K most relevant chunks for a query

**Algorithm:**

```
1. Embed the query string → queryVector
2. Run vector search:
   - Load all chunks for this user from SQLite
   - Compute cosine similarity between queryVector and each chunk.embedding
   - Rank by similarity descending → vectorResults[]
3. Run keyword search (FTS5):
   - SELECT rowid, rank FROM chunks_fts WHERE text MATCH ? ORDER BY rank
   - Convert BM25 rank to score: score = 1 / (1 + rank_position)
   → keywordResults[]
4. Fuse scores (union — include results from either method):
   finalScore = 0.7 × vectorScore + 0.3 × keywordScore
5. Sort by finalScore descending, return top K chunks
```

**Note:** Use union not intersection — a chunk that only scores in one method should still be included.

---

### 4. Discord Bot Integration (`bot.js`)

**On every message received:**

```
1. Log the user message to today's daily log file
2. Search memory for relevant context:
   search(userId, userMessage, topK=5)
3. Build the prompt:
   [system prompt]
   + retrieved memory chunks (as context)
   + recent conversation history (last N messages in-window)
   + user message
4. Call LLM API → get response
5. Log the bot response to today's daily log file
6. Send response to Discord
7. Re-index any modified memory files (async, non-blocking)
8. If conversation is getting long → trigger flushMemory()
```

**Memory scoping:**
- Search both `users/{userId}/` and `guilds/{guildId}/` memory
- Write logs to user-scoped memory only
- Write guild-wide facts to `guilds/{guildId}/MEMORY.md`

---

## Memory Flush Logic (Prevent Context Loss)

When the conversation history approaches the model's context limit (~80% full):

1. Run a **silent LLM call** (not shown to the user) with this prompt:

```
The following is a conversation. Extract any important facts, preferences,
or decisions made by the user and write them as concise bullet points.
Only include things worth remembering long-term.

Conversation:
{last N messages}

Respond ONLY with bullet points. No preamble.
```

2. Append the output to `users/{userId}/MEMORY.md`
3. Clear the in-memory conversation history (keep only last 2 messages)

---

## Tech Stack Recommendations

| Component | Recommended library |
|---|---|
| Discord bot | `discord.js` v14 |
| SQLite | `better-sqlite3` |
| Embeddings | OpenAI SDK (`openai` npm package) |
| File I/O | Node.js `fs/promises` |
| Cosine similarity (fallback) | Pure JS — `dot(a,b) / (mag(a) * mag(b))` |

---

## Environment Variables Needed

```env
DISCORD_TOKEN=
DISCORD_CLIENT_ID=
OPENAI_API_KEY=        # For embeddings + LLM calls
ANTHROPIC_API_KEY=     # Alternative LLM provider
MEMORY_BASE_PATH=./memory
INDEX_PATH=./index/memory.sqlite
```

---

## What NOT to Build

- No external vector database (Pinecone, Chroma, Weaviate) — SQLite is enough
- No real-time sync across machines — local-first by design
- No complex auth — Discord userId/guildId are the identity layer

---

## Definition of Done

- [ ] Bot responds to messages in Discord
- [ ] Every conversation is logged to a daily Markdown file
- [ ] Memory files are indexed into SQLite after each session
- [ ] Relevant past context is retrieved and injected into each prompt
- [ ] Long-term facts are extracted and saved before context compaction
- [ ] Memory is scoped per Discord user (and optionally per guild)
- [ ] System works with no embedding provider (FTS5-only fallback)
