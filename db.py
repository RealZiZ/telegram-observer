import aiosqlite
import logging
from datetime import datetime

log = logging.getLogger("tglogger")


class Database:
    def __init__(self, path: str):
        self.path = path
        self._conn: aiosqlite.Connection | None = None

    async def connect(self):
        self._conn = await aiosqlite.connect(self.path)
        self._conn.row_factory = aiosqlite.Row
        await self._migrate()
        log.info("Database ready: %s", self.path)

    async def close(self):
        if self._conn:
            await self._conn.close()

    async def _migrate(self):
        await self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS messages (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                message_id   INTEGER NOT NULL,
                sender_id    INTEGER,
                sender_name  TEXT,
                chat_id      INTEGER,
                chat_name    TEXT,
                text         TEXT,
                media_type   TEXT,
                date         TEXT NOT NULL,
                saved_at     TEXT NOT NULL,
                deleted      INTEGER DEFAULT 0,
                deleted_at   TEXT,
                edited       INTEGER DEFAULT 0,
                edit_count   INTEGER DEFAULT 0,
                last_edited  TEXT
            );

            CREATE TABLE IF NOT EXISTS message_edits (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                message_id  INTEGER NOT NULL,
                chat_id     INTEGER,
                old_text    TEXT,
                new_text    TEXT,
                edited_at   TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS watched_chats (
                chat_id    INTEGER PRIMARY KEY,
                chat_name  TEXT,
                chat_type  TEXT,
                added_at   TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS watched_users (
                user_id      INTEGER PRIMARY KEY,
                username     TEXT,
                display_name TEXT,
                added_at     TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS config (
                key   TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_msg_id ON messages(message_id);
            CREATE INDEX IF NOT EXISTS idx_sender ON messages(sender_id);
            CREATE INDEX IF NOT EXISTS idx_chat   ON messages(chat_id);
            CREATE INDEX IF NOT EXISTS idx_date   ON messages(date);
        """)

        # Safe migrations for existing DBs that predate these columns
        for stmt in [
            "ALTER TABLE messages ADD COLUMN chat_name TEXT",
            "ALTER TABLE message_edits ADD COLUMN chat_id INTEGER",
        ]:
            try:
                await self._conn.execute(stmt)
            except Exception:
                pass

        await self._conn.execute(
            "INSERT OR IGNORE INTO config (key, value) VALUES ('paused', '0')"
        )
        await self._conn.commit()

    # ── Config ────────────────────────────────────────────────────────────────
    async def get_config(self, key: str) -> str | None:
        async with self._conn.execute(
            "SELECT value FROM config WHERE key=?", (key,)
        ) as cur:
            row = await cur.fetchone()
        return row["value"] if row else None

    async def set_config(self, key: str, value: str):
        await self._conn.execute(
            "INSERT OR REPLACE INTO config (key, value) VALUES (?,?)", (key, value)
        )
        await self._conn.commit()

    async def is_paused(self) -> bool:
        return await self.get_config("paused") == "1"

    async def set_paused(self, state: bool):
        await self.set_config("paused", "1" if state else "0")

    # ── Watched chats ─────────────────────────────────────────────────────────
    async def add_watched_chat(self, chat_id: int, chat_name: str, chat_type: str):
        await self._conn.execute(
            "INSERT OR REPLACE INTO watched_chats (chat_id, chat_name, chat_type, added_at) VALUES (?,?,?,?)",
            (chat_id, chat_name, chat_type, str(datetime.now())),
        )
        await self._conn.commit()

    async def remove_watched_chat(self, chat_id: int) -> bool:
        cur = await self._conn.execute(
            "DELETE FROM watched_chats WHERE chat_id=?", (chat_id,)
        )
        await self._conn.commit()
        return cur.rowcount > 0

    async def get_watched_chats(self) -> list:
        async with self._conn.execute(
            "SELECT * FROM watched_chats ORDER BY added_at DESC"
        ) as cur:
            return await cur.fetchall()

    async def is_watched_chat(self, chat_id: int) -> bool:
        async with self._conn.execute(
            "SELECT 1 FROM watched_chats WHERE chat_id=?", (chat_id,)
        ) as cur:
            return await cur.fetchone() is not None

    # ── Watched users ─────────────────────────────────────────────────────────
    async def add_watched_user(self, user_id: int, username: str | None, display_name: str):
        await self._conn.execute(
            "INSERT OR REPLACE INTO watched_users (user_id, username, display_name, added_at) VALUES (?,?,?,?)",
            (user_id, username, display_name, str(datetime.now())),
        )
        await self._conn.commit()

    async def remove_watched_user(self, user_id: int) -> bool:
        cur = await self._conn.execute(
            "DELETE FROM watched_users WHERE user_id=?", (user_id,)
        )
        await self._conn.commit()
        return cur.rowcount > 0

    async def get_watched_users(self) -> list:
        async with self._conn.execute(
            "SELECT * FROM watched_users ORDER BY added_at DESC"
        ) as cur:
            return await cur.fetchall()

    async def is_watched_user(self, user_id: int) -> bool:
        async with self._conn.execute(
            "SELECT 1 FROM watched_users WHERE user_id=?", (user_id,)
        ) as cur:
            return await cur.fetchone() is not None

    # ── Messages ──────────────────────────────────────────────────────────────
    async def save_message(self, *, message_id, sender_id, sender_name,
                           chat_id, chat_name, text, media_type, date):
        await self._conn.execute(
            """INSERT INTO messages
               (message_id, sender_id, sender_name, chat_id, chat_name,
                text, media_type, date, saved_at)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (message_id, sender_id, sender_name, chat_id, chat_name,
             text, media_type, str(date), str(datetime.now())),
        )
        await self._conn.commit()

    async def mark_deleted(self, msg_id: int):
        await self._conn.execute(
            "UPDATE messages SET deleted=1, deleted_at=? WHERE message_id=?",
            (str(datetime.now()), msg_id),
        )
        await self._conn.commit()

    async def save_edit(self, msg_id: int, chat_id: int, new_text: str):
        async with self._conn.execute(
            "SELECT text FROM messages WHERE message_id=? AND chat_id=?", (msg_id, chat_id)
        ) as cur:
            row = await cur.fetchone()
        old_text = row["text"] if row else None

        await self._conn.execute(
            "INSERT INTO message_edits (message_id, chat_id, old_text, new_text, edited_at) VALUES (?,?,?,?,?)",
            (msg_id, chat_id, old_text, new_text, str(datetime.now())),
        )
        await self._conn.execute(
            """UPDATE messages
               SET text=?, edited=1, edit_count=edit_count+1, last_edited=?
               WHERE message_id=? AND chat_id=?""",
            (new_text, str(datetime.now()), msg_id, chat_id),
        )
        await self._conn.commit()

    async def get_message(self, msg_id: int, chat_id: int | None = None):
        if chat_id is not None:
            sql, params = "SELECT * FROM messages WHERE message_id=? AND chat_id=?", (msg_id, chat_id)
        else:
            sql, params = "SELECT * FROM messages WHERE message_id=?", (msg_id,)
        async with self._conn.execute(sql, params) as cur:
            return await cur.fetchone()

    async def get_recent_messages(self, limit: int = 10) -> list:
        async with self._conn.execute(
            "SELECT * FROM messages ORDER BY saved_at DESC LIMIT ?", (limit,)
        ) as cur:
            return await cur.fetchall()

    async def search_messages(self, query: str, limit: int = 20) -> list:
        async with self._conn.execute(
            "SELECT * FROM messages WHERE text LIKE ? ORDER BY date DESC LIMIT ?",
            (f"%{query}%", limit),
        ) as cur:
            return await cur.fetchall()

    async def stats(self) -> dict:
        result = {}
        async with self._conn.execute("SELECT COUNT(*) as n FROM messages") as cur:
            result["total"] = (await cur.fetchone())["n"]
        async with self._conn.execute("SELECT COUNT(*) as n FROM messages WHERE deleted=1") as cur:
            result["deleted"] = (await cur.fetchone())["n"]
        async with self._conn.execute("SELECT COUNT(*) as n FROM messages WHERE edited=1") as cur:
            result["edited"] = (await cur.fetchone())["n"]
        async with self._conn.execute(
            "SELECT MAX(sender_name) as sender_name, COUNT(*) as n FROM messages GROUP BY sender_id ORDER BY n DESC LIMIT 10"
        ) as cur:
            result["top_senders"] = await cur.fetchall()
        return result
