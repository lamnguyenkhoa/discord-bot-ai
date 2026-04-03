import sqlite3
import logging
import config

logger = logging.getLogger(__name__)


def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(config.INDEX_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_aura_db():
    conn = _get_conn()
    try:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS aura (
                guild_id TEXT NOT NULL,
                user_id  TEXT NOT NULL,
                points   INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (guild_id, user_id)
            );

            CREATE TABLE IF NOT EXISTS aura_log (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id      TEXT NOT NULL,
                user_id       TEXT NOT NULL,
                delta         INTEGER NOT NULL,
                reason        TEXT,
                source        TEXT,
                source_msg_id TEXT,
                created_at    TEXT NOT NULL DEFAULT (datetime('now'))
            );

            CREATE INDEX IF NOT EXISTS idx_aura_log_user ON aura_log(guild_id, user_id);
        """)
        conn.commit()
        logger.info("Aura DB initialized")
    finally:
        conn.close()


def change_aura(
    guild_id: str,
    user_id: str,
    delta: int,
    reason: str = None,
    source: str = "llm",
    source_msg_id: str = None,
) -> int:
    """Atomically update aura points and log the change. Returns the new total."""
    conn = _get_conn()
    try:
        conn.execute(
            """
            INSERT INTO aura (guild_id, user_id, points) VALUES (?, ?, ?)
            ON CONFLICT(guild_id, user_id) DO UPDATE SET points = points + excluded.points
            """,
            (guild_id, user_id, delta),
        )
        conn.execute(
            """
            INSERT INTO aura_log (guild_id, user_id, delta, reason, source, source_msg_id)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (guild_id, user_id, delta, reason, source, source_msg_id),
        )
        conn.commit()
        row = conn.execute(
            "SELECT points FROM aura WHERE guild_id = ? AND user_id = ?",
            (guild_id, user_id),
        ).fetchone()
        return row["points"] if row else 0
    finally:
        conn.close()


def get_aura(guild_id: str, user_id: str) -> int:
    conn = _get_conn()
    try:
        row = conn.execute(
            "SELECT points FROM aura WHERE guild_id = ? AND user_id = ?",
            (guild_id, user_id),
        ).fetchone()
        return row["points"] if row else 0
    finally:
        conn.close()


def get_leaderboard(guild_id: str, limit: int = 10) -> list[tuple[str, int]]:
    conn = _get_conn()
    try:
        rows = conn.execute(
            "SELECT user_id, points FROM aura WHERE guild_id = ? ORDER BY points DESC LIMIT ?",
            (guild_id, limit),
        ).fetchall()
        return [(row["user_id"], row["points"]) for row in rows]
    finally:
        conn.close()
