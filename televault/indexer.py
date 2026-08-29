from __future__ import annotations

import asyncio
import inspect
import re
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Awaitable, Callable

from telethon.tl.types import DocumentAttributeFilename, DocumentAttributeVideo

from .database import Database, MediaRecord
from .telegram_client import TelegramMediaClient


ProgressCallback = Callable[["IndexProgress"], Awaitable[None] | None]


@dataclass(frozen=True, slots=True)
class IndexProgress:
    running: bool = False
    scanned_messages: int = 0
    media_found: int = 0
    added: int = 0
    duplicates: int = 0
    thumbnails: int = 0
    current_title: str = ""
    last_error: str = ""
    finished_at: str = ""


def _normalise_title(value: str) -> str:
    value = re.sub(r"\s+", " ", value).strip(" ._-")
    return value[:180] or "Untitled media"


def record_from_message(message: Any, chat_id: int) -> MediaRecord | None:
    file = getattr(message, "file", None)
    photo = getattr(message, "photo", None)
    document = getattr(message, "document", None)
    mime_type = str(getattr(file, "mime_type", "") or "")
    is_video = bool(
        getattr(message, "video", None)
        or getattr(message, "video_note", None)
        or mime_type.startswith("video/")
    )
    if not photo and not is_video:
        return None

    kind = "photo" if photo else "video"
    media_object = photo or document
    media_identifier = getattr(media_object, "id", None)
    if media_identifier is None:
        return None
    dedupe_key = f"{kind}:{media_identifier}"

    filename = str(getattr(file, "name", "") or "")
    width = int(getattr(file, "width", 0) or 0)
    height = int(getattr(file, "height", 0) or 0)
    duration = int(float(getattr(file, "duration", 0) or 0))

    if document:
        for attribute in getattr(document, "attributes", []) or []:
            if isinstance(attribute, DocumentAttributeFilename) and not filename:
                filename = attribute.file_name or ""
            if isinstance(attribute, DocumentAttributeVideo):
                duration = int(float(attribute.duration or duration or 0))
                width = int(attribute.w or width or 0)
                height = int(attribute.h or height or 0)
    elif photo:
        sizes = [size for size in getattr(photo, "sizes", []) or [] if hasattr(size, "w")]
        if sizes:
            largest = max(sizes, key=lambda item: int(getattr(item, "w", 0)) * int(getattr(item, "h", 0)))
            width = int(getattr(largest, "w", 0) or 0)
            height = int(getattr(largest, "h", 0) or 0)

    caption = str(getattr(message, "message", "") or "").strip()
    if filename:
        stem = Path(filename).stem.replace("_", " ").replace("-", " ")
        title = _normalise_title(stem)
    elif caption:
        title = _normalise_title(caption.splitlines()[0])
    else:
        title = f"{'Photo' if kind == 'photo' else 'Video'} {message.id}"
    if not filename:
        extension = ".jpg" if kind == "photo" else ".mp4"
        filename = f"{kind}-{message.id}{extension}"

    date = getattr(message, "date", None) or datetime.now(timezone.utc)
    if date.tzinfo is None:
        date = date.replace(tzinfo=timezone.utc)
    size_bytes = int(getattr(file, "size", 0) or 0)
    if kind == "photo" and not size_bytes:
        size_bytes = max(
            (int(getattr(item, "size", 0) or 0) for item in getattr(photo, "sizes", []) or []),
            default=0,
        )

    return MediaRecord(
        chat_id=chat_id,
        message_id=int(message.id),
        dedupe_key=dedupe_key,
        kind=kind,
        title=title,
        filename=filename[:255],
        caption=caption[:4000],
        mime_type=mime_type or ("image/jpeg" if kind == "photo" else "video/mp4"),
        size_bytes=max(0, size_bytes),
        duration_seconds=max(0, duration),
        width=max(0, width),
        height=max(0, height),
        message_date=date.astimezone(timezone.utc).isoformat(),
    )


class IndexManager:
    def __init__(
        self,
        database: Database,
        telegram: TelegramMediaClient,
        thumbnail_dir: str | Path,
    ):
        self.database = database
        self.telegram = telegram
        self.thumbnail_dir = Path(thumbnail_dir).resolve()
        self._scan_lock = asyncio.Lock()
        self._status = IndexProgress()

    @property
    def status(self) -> IndexProgress:
        return self._status

    async def _report(self, callback: ProgressCallback | None) -> None:
        if callback is None:
            return
        outcome = callback(self._status)
        if inspect.isawaitable(outcome):
            await outcome

    async def _thumbnail_task(self, message: Any, media_id: int) -> bool:
        destination = self.thumbnail_dir / f"{media_id}.webp"
        success = await self.telegram.build_thumbnail(message, destination)
        if success:
            self.database.set_thumbnail(media_id, destination.name)
        return success

    async def scan(
        self,
        *,
        full: bool = False,
        rebuild_thumbnails: bool = False,
        progress: ProgressCallback | None = None,
    ) -> IndexProgress:
        if self._scan_lock.locked():
            return self._status
        async with self._scan_lock:
            self._status = IndexProgress(running=True)
            await self._report(progress)
            last_indexed = 0 if full else int(self.database.get_meta("last_message_id", "0") or 0)
            highest_message_id = last_indexed
            pending: set[asyncio.Task[bool]] = set()
            scheduled_thumbnail_ids: set[int] = set()
            try:
                async for message in self.telegram.iter_messages(min_id=last_indexed, reverse=True):
                    highest_message_id = max(highest_message_id, int(message.id))
                    self._status = replace(
                        self._status,
                        scanned_messages=self._status.scanned_messages + 1,
                    )
                    record = record_from_message(message, self.telegram.config.chat_id)
                    if record is None:
                        if self._status.scanned_messages % 100 == 0:
                            await self._report(progress)
                        continue
                    media_id, is_new, thumbnail_filename = self.database.upsert_media(record)
                    self._status = replace(
                        self._status,
                        media_found=self._status.media_found + 1,
                        added=self._status.added + int(is_new),
                        duplicates=self._status.duplicates + int(not is_new),
                        current_title=record.title,
                    )
                    thumbnail_path = self.thumbnail_dir / (thumbnail_filename or "")
                    needs_thumbnail = (
                        rebuild_thumbnails
                        or not thumbnail_filename
                        or not thumbnail_path.is_file()
                    )
                    if needs_thumbnail and media_id not in scheduled_thumbnail_ids:
                        scheduled_thumbnail_ids.add(media_id)
                        pending.add(asyncio.create_task(self._thumbnail_task(message, media_id)))
                    if len(pending) >= 8:
                        done, pending = await asyncio.wait(
                            pending, return_when=asyncio.FIRST_COMPLETED
                        )
                        completed = sum(1 for task in done if not task.cancelled() and task.result())
                        self._status = replace(
                            self._status,
                            thumbnails=self._status.thumbnails + completed,
                        )
                    if self._status.media_found % 25 == 0:
                        await self._report(progress)

                if pending:
                    results = await asyncio.gather(*pending, return_exceptions=True)
                    completed = sum(result is True for result in results)
                    self._status = replace(
                        self._status,
                        thumbnails=self._status.thumbnails + completed,
                    )
                self.database.set_meta("last_message_id", str(highest_message_id))
                finished = datetime.now(timezone.utc).isoformat()
                self.database.set_meta("last_scan_at", finished)
                self._status = replace(
                    self._status,
                    running=False,
                    current_title="",
                    finished_at=finished,
                )
            except Exception as exc:
                for task in pending:
                    task.cancel()
                self._status = replace(
                    self._status,
                    running=False,
                    current_title="",
                    last_error=str(exc),
                    finished_at=datetime.now(timezone.utc).isoformat(),
                )
                await self._report(progress)
                raise
            await self._report(progress)
            return self._status
