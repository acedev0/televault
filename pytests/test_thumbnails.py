import asyncio
import io
from types import SimpleNamespace

import pytest
from PIL import Image

from televault.telegram_client import TelegramMediaClient


class FakeDownloadClient:
    def __init__(self, payload: bytes):
        self.payload = payload

    async def download_media(self, message, **kwargs):
        return self.payload


def image_bytes(size: tuple[int, int]) -> bytes:
    output = io.BytesIO()
    Image.new("RGB", size, "#d64f6a").save(output, "JPEG")
    return output.getvalue()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("source_size", "expected_size"),
    [((1600, 900), (720, 405)), ((600, 1000), (432, 720))],
)
async def test_thumbnail_preserves_landscape_and_portrait_orientation(
    tmp_path, source_size, expected_size
):
    telegram = object.__new__(TelegramMediaClient)
    telegram.thumbnail_semaphore = asyncio.Semaphore(1)
    telegram.client = FakeDownloadClient(image_bytes(source_size))
    destination = tmp_path / "thumbnail.webp"

    created = await telegram.build_thumbnail(
        SimpleNamespace(photo=object()),
        destination,
    )

    assert created is True
    with Image.open(destination) as thumbnail:
        assert thumbnail.size == expected_size
    assert oct(destination.stat().st_mode & 0o777) == "0o600"
