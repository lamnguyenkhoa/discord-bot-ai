import hashlib
import json
import logging
import os
import sqlite3

import config

logger = logging.getLogger(__name__)

_CHUNK_SIZE = 20
_CHUNK_OVERLAP = 4


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
        from openai import AsyncOpenAI
        embed_client = AsyncOpenAI(
            api_key=config.EMBEDDING_API_KEY,
            base_url=config.EMBEDDING_BASE_URL,
        )
        response = await embed_client.embeddings.create(
            model=config.EMBEDDING_MODEL,
            input=texts,
        )
        return [item.embedding for item in response.data]
    except Exception as e:
        logger.warning(f"Embedding failed, using FTS5-only fallback: {e}")
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


async def index_user(user_id: str, db_path: str | None = None) -> None:
    """Re-index all memory files for a user."""
    from memory_manager import get_all_user_files
    for file_path in get_all_user_files(user_id):
        await index_file(file_path, db_path)


async def index_guild(guild_id: str, db_path: str | None = None) -> None:
    """Re-index guild memory file."""
    from memory_manager import get_guild_memory_path
    guild_memory = get_guild_memory_path(guild_id)
    if os.path.exists(guild_memory):
        await index_file(guild_memory, db_path)
