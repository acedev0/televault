from __future__ import annotations

import asyncio
import io
from pathlib import Path
from typing import Any, AsyncIterator

from PIL import Image, ImageOps
from telethon import TelegramClient, utils
from telethon.sessions import StringSession

from .config import AppSecrets


class TelegramUnavailable(RuntimeError):
    pass


class TelegramMediaClient:
    """One persistent MTProto connection shared by indexing and HTTP streams."""

    def __init__(self, config: AppSecrets, max_streams: int = 4):
        self.config = config
        self.client = TelegramClient(
            StringSession(config.string_session),
            config.api_id,
            config.api_hash,
            sequential_updates=True,
            auto_reconnect=True,
            connection_retries=5,
            request_retries=5,
            retry_delay=2,
            flood_sleep_threshold=60,
        )
        self.entity: Any | None = None
        self.stream_semaphore = asyncio.Semaphore(max_streams)
        self.thumbnail_semaphore = asyncio.Semaphore(4)

    async def connect(self) -> None:
        await self.client.connect()
        if not await self.client.is_user_authorized():
            raise TelegramUnavailable(
                "The Telegram session is no longer authorised. Run TeleVault setup again."
            )
        try:
            self.entity = await self.client.get_entity(self.config.chat_reference)
        except Exception:
            self.entity = await self.client.get_entity(self.config.chat_id)

    async def disconnect(self) -> None:
        await self.client.disconnect()

    def iter_messages(self, *, min_id: int = 0, reverse: bool = True):
        if self.entity is None:
            raise TelegramUnavailable("Telegram is not connected.")
        return self.client.iter_messages(
            self.entity,
            min_id=max(0, min_id),
            reverse=reverse,
        )

    async def get_message(self, message_id: int):
        if self.entity is None:
            raise TelegramUnavailable("Telegram is not connected.")
        message = await self.client.get_messages(self.entity, ids=message_id)
        if not message or not getattr(message, "media", None):
            return None
        return message

    async def download_photo(self, message_id: int) -> bytes:
        async with self.stream_semaphore:
            message = await self.get_message(message_id)
            if message is None or not getattr(message, "photo", None):
                raise FileNotFoundError("The Telegram photo no longer exists.")
            raw = await self.client.download_media(message, file=bytes)
            if not raw:
                raise FileNotFoundError("Telegram returned an empty photo.")
            return bytes(raw)

    async def stream(
        self,
        message_id: int,
        start: int,
        end: int,
        file_size: int,
    ) -> AsyncIterator[bytes]:
        async with self.stream_semaphore:
            message = await self.get_message(message_id)
            if message is None:
                raise FileNotFoundError("The Telegram media no longer exists.")
            remaining = end - start + 1
            iterator = self.client.iter_download(
                message.media,
                offset=start,
                request_size=512 * 1024,
                chunk_size=512 * 1024,
                file_size=file_size,
            )
            async for chunk in iterator:
                if not chunk or remaining <= 0:
                    break
                selected = bytes(chunk[:remaining])
                if selected:
                    remaining -= len(selected)
                    yield selected
                if remaining <= 0:
                    break

    async def build_thumbnail(self, message: Any, destination: Path) -> bool:
        """Download only Telegram's preview when possible, then persist a small WebP."""
        async with self.thumbnail_semaphore:
            try:
                if getattr(message, "photo", None):
                    raw = await self.client.download_media(message, file=bytes)
                else:
                    raw = await self.client.download_media(message, file=bytes, thumb=-1)
            except Exception:
                return False
            if not raw:
                return False
            try:
                with Image.open(io.BytesIO(raw)) as source:
                    image = ImageOps.exif_transpose(source).convert("RGB")
                    image.thumbnail((640, 360), Image.Resampling.LANCZOS)
                    canvas = Image.new("RGB", (640, 360), "#111318")
                    x = (640 - image.width) // 2
                    y = (360 - image.height) // 2
                    canvas.paste(image, (x, y))
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    canvas.save(destination, "WEBP", quality=78, method=4)
                    destination.chmod(0o600)
            except (OSError, ValueError):
                return False
            return True

    async def account_display_name(self) -> str:
        me = await self.client.get_me()
        first = getattr(me, "first_name", "") or ""
        last = getattr(me, "last_name", "") or ""
        username = getattr(me, "username", "") or ""
        return " ".join(part for part in (first, last) if part).strip() or username or "Telegram account"

    async def current_chat_id(self) -> int:
        if self.entity is None:
            raise TelegramUnavailable("Telegram is not connected.")
        return int(utils.get_peer_id(self.entity))
