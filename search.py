import json
import logging
import math
import os
import sqlite3

import config

logger = logging.getLogger(__name__)


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    mag_a = math.sqrt(sum(x * x for x in a))
    mag_b = math.sqrt(sum(x * x for x in b))
    if mag_a == 0 or mag_b == 0:
        return 0.0
    return dot / (mag_a * mag_b)


async def _embed_query(query: str) -> list[float] | None:
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
        logger.warning(f"Query embedding failed, using FTS5-only: {e}")
        return None


def _get_scoped_file_ids(
    conn: sqlite3.Connection,
    user_id: str,
    guild_id: str | None,
) -> list[int]:
    """Return file IDs for all memory files belonging to the given user and guild."""
    from memory_manager import _user_dir, _guild_dir
    patterns = [_user_dir(user_id) + "%"]
    if guild_id:
        patterns.append(_guild_dir(guild_id) + "%")

    ids = []
    for pattern in patterns:
        rows = conn.execute("SELECT id FROM files WHERE path LIKE ?", (pattern,)).fetchall()
        ids.extend(r[0] for r in rows)
    return ids


async def search(
    user_id: str,
    guild_id: str | None,
    query: str,
    top_k: int | None = None,
) -> list[str]:
    """
    Hybrid search over user + guild memory.

    Returns up to top_k text chunks, ranked by:
        finalScore = 0.7 * vectorScore + 0.3 * keywordScore
    Falls back to FTS5-only when no embeddings are available.
    """
    if top_k is None:
        top_k = config.MEMORY_SEARCH_TOP_K

    db_path = config.INDEX_PATH
    if not os.path.exists(db_path):
        return []

    conn = sqlite3.connect(db_path)
    try:
        file_ids = _get_scoped_file_ids(conn, user_id, guild_id)
        if not file_ids:
            return []

        placeholders = ",".join("?" * len(file_ids))

        # --- Vector search ---
        query_vec = await _embed_query(query)
        vector_scores: dict[int, float] = {}
        if query_vec:
            rows = conn.execute(
                f"SELECT id, text, embedding FROM chunks"
                f" WHERE file_id IN ({placeholders}) AND embedding IS NOT NULL",
                file_ids,
            ).fetchall()
            for chunk_id, _text, emb_blob in rows:
                if emb_blob:
                    emb = json.loads(emb_blob)
                    vector_scores[chunk_id] = _cosine_similarity(query_vec, emb)

        # --- FTS5 keyword search ---
        keyword_scores: dict[int, float] = {}
        scope_ids: set[int] = {
            r[0]
            for r in conn.execute(
                f"SELECT id FROM chunks WHERE file_id IN ({placeholders})", file_ids
            ).fetchall()
        }
        try:
            fts_rows = conn.execute(
                "SELECT rowid, rank FROM chunks_fts WHERE text MATCH ? ORDER BY rank LIMIT 50",
                (query,),
            ).fetchall()
            for pos, (chunk_id, _rank) in enumerate(fts_rows):
                if chunk_id in scope_ids:
                    keyword_scores[chunk_id] = 1.0 / (1.0 + pos)
        except sqlite3.OperationalError as e:
            logger.debug(f"FTS5 search error (ignored): {e}")

        # --- Fuse scores (union) ---
        all_ids = set(vector_scores) | set(keyword_scores)
        if not all_ids:
            return []

        chunk_texts: dict[int, str] = {
            r[0]: r[1]
            for r in conn.execute(
                f"SELECT id, text FROM chunks WHERE id IN ({','.join('?' * len(all_ids))})",
                list(all_ids),
            ).fetchall()
        }

        fused: list[tuple[float, int, str]] = []
        for chunk_id in all_ids:
            v_score = vector_scores.get(chunk_id, 0.0)
            k_score = keyword_scores.get(chunk_id, 0.0)
            final_score = 0.7 * v_score + 0.3 * k_score
            text = chunk_texts.get(chunk_id, "")
            if text:
                fused.append((final_score, chunk_id, text))

        fused.sort(reverse=True)
        return [text for _, _, text in fused[:top_k]]

    finally:
        conn.close()
