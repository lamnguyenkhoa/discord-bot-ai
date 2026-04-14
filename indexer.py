import glob
import hashlib
import json
import logging
import os
import sqlite3

import config

logger = logging.getLogger(__name__)

_CHUNK_SIZE = 20
_CHUNK_OVERLAP = 4
_embed_client: "AsyncOpenAI | None" = None


def _get_embed_client() -> "AsyncOpenAI | None":
    global _embed_client
    if _embed_client is None:
        from openai import AsyncOpenAI
        _embed_client = AsyncOpenAI(
            api_key=config.EMBEDDING_API_KEY,
            base_url=config.EMBEDDING_BASE_URL,
        )
    return _embed_client


def _sanitize_fts_query(query: str) -> str:
    """Escape FTS5 special characters."""
    special_chars = ['*', '"', '(', ')', ':', '^', '-', '+']
    for char in special_chars:
        query = query.replace(char, ' ')
    return query.strip()


def _get_db(db_path: str) -> sqlite3.Connection:
    os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db(db_path: str | None = None) -> None:
    if db_path is None:
        db_path = config.INDEX_PATH
    conn = _get_db(db_path)
    with conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS files (
                id INTEGER PRIMARY KEY,
                path TEXT UNIQUE NOT NULL,
                mtime INTEGER NOT NULL,
                size INTEGER NOT NULL,
                content_hash TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS chunks (
                id INTEGER PRIMARY KEY,
                file_id INTEGER REFERENCES files(id) ON DELETE CASCADE,
                text TEXT NOT NULL,
                line_start INTEGER,
                line_end INTEGER,
                embedding BLOB
            );

            CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
                text,
                content='chunks',
                content_rowid='id'
            );
        """)
    conn.close()
    logger.debug(f"SQLite DB initialized at {db_path}")


def _chunk_lines(lines: list[str]) -> list[tuple[int, int, str]]:
    """Sliding window chunking. Returns (line_start, line_end, text) tuples."""
    chunks = []
    i = 0
    while i < len(lines):
        end = min(i + _CHUNK_SIZE, len(lines))
        text = "\n".join(lines[i:end]).strip()
        if text:
            chunks.append((i, end - 1, text))
        if end == len(lines):
            break
        i += _CHUNK_SIZE - _CHUNK_OVERLAP
    return chunks


async def _embed_texts(texts: list[str]) -> list[list[float]] | None:
    """Batch embed texts via OpenAI. Returns None if unavailable."""
    if not config.EMBEDDING_API_KEY:
        return None
    try:
        embed_client = _get_embed_client()
        response = await embed_client.embeddings.create(
            model=config.EMBEDDING_MODEL,
            input=texts,
        )
        return [item.embedding for item in response.data]
    except Exception as e:
        logger.warning(f"Embedding failed, using FTS5-only fallback: {e}")
        return None


async def _embed_query(query: str) -> list[float] | None:
    """Embed a single query. Returns None if unavailable."""
    if not config.EMBEDDING_API_KEY:
        return None
    try:
        embed_client = _get_embed_client()
        response = await embed_client.embeddings.create(
            model=config.EMBEDDING_MODEL,
            input=[query],
        )
        return response.data[0].embedding
    except Exception as e:
        logger.warning(f"Query embedding failed: {e}")
        return None


async def index_file(file_path: str, db_path: str | None = None) -> None:
    """Index a single markdown file. Skips if content unchanged."""
    if db_path is None:
        db_path = config.INDEX_PATH
    if not os.path.exists(file_path):
        return

    stat = os.stat(file_path)
    mtime = int(stat.st_mtime)
    size = stat.st_size

    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()
    content_hash = hashlib.sha256(content.encode()).hexdigest()

    conn = _get_db(db_path)
    try:
        row = conn.execute(
            "SELECT id, mtime, content_hash FROM files WHERE path = ?", (file_path,)
        ).fetchone()

        if row and row[1] == mtime and row[2] == content_hash:
            return  # unchanged — skip

        lines = content.splitlines()
        chunk_tuples = _chunk_lines(lines)
        if not chunk_tuples:
            return

        texts = [c[2] for c in chunk_tuples]
        embeddings = await _embed_texts(texts)

        with conn:
            if row:
                conn.execute("DELETE FROM files WHERE id = ?", (row[0],))

            cur = conn.execute(
                "INSERT INTO files (path, mtime, size, content_hash) VALUES (?, ?, ?, ?)",
                (file_path, mtime, size, content_hash),
            )
            file_id = cur.lastrowid

            for i, (line_start, line_end, text) in enumerate(chunk_tuples):
                emb_blob = json.dumps(embeddings[i]) if embeddings else None
                conn.execute(
                    "INSERT INTO chunks (file_id, text, line_start, line_end, embedding) VALUES (?, ?, ?, ?, ?)",
                    (file_id, text, line_start, line_end, emb_blob),
                )

            # Rebuild FTS index
            conn.execute("INSERT INTO chunks_fts(chunks_fts) VALUES('rebuild')")

        logger.debug(f"Indexed {file_path}: {len(chunk_tuples)} chunk(s)")
    finally:
        conn.close()


async def index_guild(guild_id: str, db_path: str | None = None) -> None:
    """Re-index guild memory file."""
    guild_memory = f"{config.MEMORY_BASE_PATH}/guild_{guild_id}.md"
    if os.path.exists(guild_memory):
        await index_file(guild_memory, db_path)


async def index_all() -> dict:
    """Index all .md files in MEMORY_BASE_PATH. Returns stats dict."""
    memory_path = config.MEMORY_BASE_PATH
    if not os.path.exists(memory_path):
        os.makedirs(memory_path, exist_ok=True)
        logger.info(f"Created memory directory: {memory_path}")
        return {"files": 0, "chunks": 0}

    files = glob.glob(os.path.join(memory_path, "*.md"))
    total_files = 0
    total_chunks = 0

    for file_path in files:
        before_chunks = _count_chunks(file_path)
        await index_file(file_path)
        after_chunks = _count_chunks(file_path)
        if after_chunks > 0 or before_chunks > 0:
            total_files += 1
            total_chunks += after_chunks

    logger.info(f"Indexed {total_files} files, {total_chunks} chunks")
    return {"files": total_files, "chunks": total_chunks}


def _count_chunks(file_path: str, db_path: str | None = None) -> int:
    """Count chunks for a file."""
    if db_path is None:
        db_path = config.INDEX_PATH
    if not os.path.exists(db_path):
        return 0
    conn = _get_db(db_path)
    try:
        row = conn.execute(
            "SELECT COUNT(*) FROM chunks c JOIN files f ON c.file_id = f.id WHERE f.path = ?",
            (file_path,)
        ).fetchone()
        return row[0] if row else 0
    finally:
        conn.close()


def get_stats() -> dict:
    """Get indexing statistics."""
    db_path = config.INDEX_PATH
    if not os.path.exists(db_path):
        return {"files": 0, "chunks": 0, "size_bytes": 0}

    conn = _get_db(db_path)
    try:
        file_count = conn.execute("SELECT COUNT(*) FROM files").fetchone()[0]
        chunk_count = conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
        size_bytes = os.path.getsize(db_path)
        return {
            "files": file_count,
            "chunks": chunk_count,
            "size_bytes": size_bytes,
        }
    finally:
        conn.close()


async def get_indexed_files() -> list[dict]:
    """Get list of indexed files with chunk counts."""
    db_path = config.INDEX_PATH
    if not os.path.exists(db_path):
        return []

    conn = _get_db(db_path)
    try:
        rows = conn.execute("""
            SELECT f.path, COUNT(c.id) as chunk_count
            FROM files f
            LEFT JOIN chunks c ON c.file_id = f.id
            GROUP BY f.id
            ORDER BY f.path
        """).fetchall()
        return [{"path": r[0], "chunks": r[1]} for r in rows]
    finally:
        conn.close()


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
        sanitized_query = _sanitize_fts_query(query)
        rows = conn.execute("""
            SELECT c.text, f.path, c.line_start, c.line_end,
                   bm25(chunks_fts) AS rank
            FROM chunks_fts
            JOIN chunks c ON chunks_fts.rowid = c.id
            JOIN files f ON c.file_id = f.id
            WHERE chunks_fts MATCH ?
            ORDER BY rank
            LIMIT 20
        """, (sanitized_query,)).fetchall()
        
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
