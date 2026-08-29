from __future__ import annotations

import sqlite3
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class MediaRecord:
    chat_id: int
    message_id: int
    dedupe_key: str
    kind: str
    title: str
    filename: str
    caption: str
    mime_type: str
    size_bytes: int
    duration_seconds: int
    width: int
    height: int
    message_date: str


class Database:
    def __init__(self, path: str | Path):
        self.path = Path(path).expanduser().resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA busy_timeout=30000")
        return connection

    def initialise(self) -> None:
        with self.connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS media (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chat_id INTEGER NOT NULL,
                    message_id INTEGER NOT NULL,
                    dedupe_key TEXT NOT NULL,
                    kind TEXT NOT NULL CHECK(kind IN ('video', 'photo')),
                    title TEXT NOT NULL,
                    filename TEXT NOT NULL,
                    caption TEXT NOT NULL DEFAULT '',
                    mime_type TEXT NOT NULL,
                    size_bytes INTEGER NOT NULL DEFAULT 0,
                    duration_seconds INTEGER NOT NULL DEFAULT 0,
                    width INTEGER NOT NULL DEFAULT 0,
                    height INTEGER NOT NULL DEFAULT 0,
                    message_date TEXT NOT NULL,
                    thumbnail_filename TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(chat_id, message_id),
                    UNIQUE(chat_id, dedupe_key)
                );
                CREATE INDEX IF NOT EXISTS idx_media_date
                    ON media(message_date DESC, id DESC);
                CREATE INDEX IF NOT EXISTS idx_media_kind_date
                    ON media(kind, message_date DESC);
                CREATE INDEX IF NOT EXISTS idx_media_title
                    ON media(title COLLATE NOCASE);
                CREATE TABLE IF NOT EXISTS app_meta (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                """
            )

    def upsert_media(self, record: MediaRecord) -> tuple[int, bool, str | None]:
        now = datetime.now(timezone.utc).isoformat()
        values = asdict(record)
        with self.connect() as connection:
            existing = connection.execute(
                "SELECT id, thumbnail_filename FROM media WHERE chat_id = ? AND dedupe_key = ?",
                (record.chat_id, record.dedupe_key),
            ).fetchone()
            connection.execute(
                "DELETE FROM media WHERE chat_id = ? AND message_id = ? AND dedupe_key <> ?",
                (record.chat_id, record.message_id, record.dedupe_key),
            )
            if existing:
                connection.execute(
                    """
                    UPDATE media SET
                        message_id = :message_id,
                        kind = :kind,
                        title = :title,
                        filename = :filename,
                        caption = :caption,
                        mime_type = :mime_type,
                        size_bytes = :size_bytes,
                        duration_seconds = :duration_seconds,
                        width = :width,
                        height = :height,
                        message_date = :message_date,
                        updated_at = :updated_at
                    WHERE chat_id = :chat_id AND dedupe_key = :dedupe_key
                    """,
                    {**values, "updated_at": now},
                )
                return int(existing["id"]), False, existing["thumbnail_filename"]

            cursor = connection.execute(
                """
                INSERT INTO media (
                    chat_id, message_id, dedupe_key, kind, title, filename,
                    caption, mime_type, size_bytes, duration_seconds, width,
                    height, message_date, created_at, updated_at
                ) VALUES (
                    :chat_id, :message_id, :dedupe_key, :kind, :title, :filename,
                    :caption, :mime_type, :size_bytes, :duration_seconds, :width,
                    :height, :message_date, :created_at, :updated_at
                )
                """,
                {**values, "created_at": now, "updated_at": now},
            )
            return int(cursor.lastrowid), True, None

    def set_thumbnail(self, media_id: int, filename: str) -> None:
        with self.connect() as connection:
            connection.execute(
                "UPDATE media SET thumbnail_filename = ?, updated_at = ? WHERE id = ?",
                (filename, datetime.now(timezone.utc).isoformat(), media_id),
            )

    def get_media(self, media_id: int) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute("SELECT * FROM media WHERE id = ?", (media_id,)).fetchone()
        return dict(row) if row else None

    def get_by_message(self, chat_id: int, message_id: int) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM media WHERE chat_id = ? AND message_id = ?",
                (chat_id, message_id),
            ).fetchone()
        return dict(row) if row else None

    def list_media(
        self,
        *,
        query: str = "",
        kind: str = "all",
        page: int = 1,
        per_page: int = 36,
        sort: str = "newest",
    ) -> tuple[list[dict[str, Any]], int]:
        clauses: list[str] = []
        parameters: list[Any] = []
        if kind in {"video", "photo"}:
            clauses.append("kind = ?")
            parameters.append(kind)
        if query.strip():
            term = f"%{query.strip()}%"
            clauses.append("(title LIKE ? OR filename LIKE ? OR caption LIKE ?)")
            parameters.extend((term, term, term))
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        order_by = {
            "oldest": "message_date ASC, id ASC",
            "name": "title COLLATE NOCASE ASC, id DESC",
            "largest": "size_bytes DESC, id DESC",
        }.get(sort, "message_date DESC, id DESC")
        offset = max(0, page - 1) * per_page
        with self.connect() as connection:
            total = int(
                connection.execute(
                    f"SELECT COUNT(*) FROM media {where}", parameters
                ).fetchone()[0]
            )
            rows = connection.execute(
                f"SELECT * FROM media {where} ORDER BY {order_by} LIMIT ? OFFSET ?",
                (*parameters, per_page, offset),
            ).fetchall()
        return [dict(row) for row in rows], total

    def related(self, media_id: int, kind: str, limit: int = 10) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM media
                WHERE id <> ?
                ORDER BY CASE WHEN kind = ? THEN 0 ELSE 1 END,
                         message_date DESC, id DESC
                LIMIT ?
                """,
                (media_id, kind, limit),
            ).fetchall()
        return [dict(row) for row in rows]

    def stats(self) -> dict[str, int]:
        with self.connect() as connection:
            row = connection.execute(
                """
                SELECT COUNT(*) AS total,
                       SUM(CASE WHEN kind = 'video' THEN 1 ELSE 0 END) AS videos,
                       SUM(CASE WHEN kind = 'photo' THEN 1 ELSE 0 END) AS photos
                FROM media
                """
            ).fetchone()
        return {
            "total": int(row["total"] or 0),
            "videos": int(row["videos"] or 0),
            "photos": int(row["photos"] or 0),
        }

    def set_meta(self, key: str, value: str) -> None:
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO app_meta(key, value) VALUES(?, ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value
                """,
                (key, value),
            )

    def get_meta(self, key: str, default: str = "") -> str:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT value FROM app_meta WHERE key = ?", (key,)
            ).fetchone()
        return str(row[0]) if row else default

