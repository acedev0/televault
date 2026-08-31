import os
from dataclasses import replace
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from televault.config import AppSecrets, SecretVault
from televault.database import Database, MediaRecord
from televault.indexer import IndexManager, record_from_message
from televault.security import hash_password, verify_password


def sample_config() -> AppSecrets:
    return AppSecrets(
        version=1,
        api_id=12345,
        api_hash="a" * 32,
        string_session="session-secret",
        chat_reference="@vault",
        chat_id=-100123,
        chat_title="Vault",
        account_name="Ace",
        web_username="ace",
        password_hash=hash_password("a-long-password"),
        cookie_secret="c" * 64,
        port=8181,
    )


def sample_record(message_id=10, dedupe_key="video:900") -> MediaRecord:
    return MediaRecord(
        chat_id=-100123,
        message_id=message_id,
        dedupe_key=dedupe_key,
        kind="video",
        title="Example video",
        filename="example.mp4",
        caption="caption",
        mime_type="video/mp4",
        size_bytes=4096,
        duration_seconds=42,
        width=1920,
        height=1080,
        message_date="2026-08-29T12:00:00+00:00",
    )


def test_password_hash_and_verify():
    encoded = hash_password("a-long-password")
    assert encoded.startswith("$argon2id$")
    assert verify_password(encoded, "a-long-password")
    assert not verify_password(encoded, "wrong-password")


def test_encrypted_vault_round_trip_and_permissions(tmp_path):
    vault = SecretVault(tmp_path / "state")
    original = sample_config()
    vault.save(original)
    restored = vault.load()
    assert restored.api_hash == original.api_hash
    assert restored.string_session == original.string_session
    assert restored.port == 8181
    assert oct(os.stat(vault.key_path).st_mode & 0o777) == "0o600"
    assert oct(os.stat(vault.secrets_path).st_mode & 0o777) == "0o600"
    assert b"session-secret" not in vault.secrets_path.read_bytes()


def test_database_deduplicates_same_telegram_media(tmp_path):
    database = Database(tmp_path / "media.db")
    database.initialise()
    first_id, first_new, _ = database.upsert_media(sample_record(message_id=10))
    second_id, second_new, _ = database.upsert_media(sample_record(message_id=22))
    assert first_id == second_id
    assert first_new is True
    assert second_new is False
    assert database.stats() == {"total": 1, "videos": 1, "photos": 0}
    assert database.get_media(first_id)["message_id"] == 22


def test_database_search_filter_and_offset_loading(tmp_path):
    database = Database(tmp_path / "media.db")
    database.initialise()
    database.upsert_media(sample_record())
    photo = replace(
        sample_record(message_id=11, dedupe_key="photo:901"),
        kind="photo",
        title="Summer photo",
        filename="summer.jpg",
        mime_type="image/jpeg",
    )
    database.upsert_media(photo)
    rows, total = database.list_media(query="summer", kind="photo")
    assert total == 1
    assert rows[0]["title"] == "Summer photo"
    rows, total = database.list_media(per_page=1, offset=1, sort="newest")
    assert total == 2
    assert len(rows) == 1


def test_random_sort_is_stable_complete_and_has_no_batch_duplicates(tmp_path):
    database = Database(tmp_path / "media.db")
    database.initialise()
    for message_id in range(1, 91):
        database.upsert_media(
            replace(
                sample_record(),
                message_id=message_id,
                dedupe_key=f"video:{message_id}",
                title=f"Video {message_id:03d}",
            )
        )

    first, total = database.list_media(sort="random", seed=123456, per_page=36, offset=0)
    second, _ = database.list_media(sort="random", seed=123456, per_page=36, offset=36)
    third, _ = database.list_media(sort="random", seed=123456, per_page=36, offset=72)
    repeated, _ = database.list_media(sort="random", seed=123456, per_page=36, offset=0)
    different_seed, _ = database.list_media(sort="random", seed=654321, per_page=36, offset=0)

    ids = [row["id"] for row in first + second + third]
    assert total == 90
    assert len(ids) == 90
    assert len(set(ids)) == 90
    assert [row["id"] for row in repeated] == [row["id"] for row in first]
    assert [row["id"] for row in different_seed] != [row["id"] for row in first]
    assert [row["id"] for row in database.playlist(sort="random", seed=123456)] == ids


@pytest.mark.asyncio
async def test_thumbnail_upgrade_refreshes_an_existing_preview(tmp_path):
    database = Database(tmp_path / "media.db")
    database.initialise()
    media_id, _, _ = database.upsert_media(sample_record())
    thumbnail_dir = tmp_path / "thumbnails"
    thumbnail_dir.mkdir()
    existing = thumbnail_dir / f"{media_id}.webp"
    existing.write_bytes(b"old-preview")
    database.set_thumbnail(media_id, existing.name)

    file = SimpleNamespace(
        mime_type="video/mp4",
        name="example.mp4",
        width=1920,
        height=1080,
        duration=42,
        size=4096,
    )
    document = SimpleNamespace(id=900, attributes=[])
    message = SimpleNamespace(
        id=10,
        file=file,
        photo=None,
        document=document,
        video=document,
        video_note=None,
        message="caption",
        date=datetime(2026, 8, 29, 12, 0, tzinfo=timezone.utc),
    )

    class FakeTelegram:
        config = SimpleNamespace(chat_id=-100123)

        def iter_messages(self, **kwargs):
            async def messages():
                yield message

            return messages()

        async def build_thumbnail(self, telegram_message, destination):
            destination.write_bytes(b"new-preview")
            return True

    result = await IndexManager(database, FakeTelegram(), thumbnail_dir).scan(
        full=True,
        rebuild_thumbnails=True,
    )

    assert result.thumbnails == 1
    assert existing.read_bytes() == b"new-preview"


def test_extracts_video_metadata_from_message():
    file = SimpleNamespace(
        mime_type="video/mp4", name="My_Cool_Video.mp4", width=1280, height=720, duration=12.8, size=1234
    )
    document = SimpleNamespace(id=555, attributes=[])
    message = SimpleNamespace(
        id=77,
        file=file,
        photo=None,
        document=document,
        video=document,
        video_note=None,
        message="A caption",
        date=datetime(2026, 8, 29, tzinfo=timezone.utc),
    )
    record = record_from_message(message, -100123)
    assert record is not None
    assert record.kind == "video"
    assert record.dedupe_key == "video:555"
    assert record.title == "My Cool Video"
    assert record.duration_seconds == 12
