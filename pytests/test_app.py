import re
from types import SimpleNamespace

from fastapi.testclient import TestClient

from televault.app import create_app
from televault.config import AppSecrets, SecretVault
from televault.database import Database, MediaRecord
from televault.security import hash_password


VIDEO = bytes(range(256)) * 16
PHOTO = b"photo-bytes"


class FakeTelegram:
    def __init__(self, config):
        self.config = config
        self.connected = False

    async def connect(self):
        self.connected = True

    async def disconnect(self):
        self.connected = False

    async def get_message(self, message_id):
        return SimpleNamespace(id=message_id, media=object()) if message_id in {10, 11} else None

    async def stream(self, message_id, start, end, file_size):
        payload = VIDEO[start : end + 1]
        for index in range(0, len(payload), 137):
            yield payload[index : index + 137]

    async def download_photo(self, message_id):
        if message_id != 11:
            raise FileNotFoundError
        return PHOTO

    def iter_messages(self, **kwargs):
        async def empty():
            if False:
                yield None
        return empty()


def make_config(tmp_path):
    config = AppSecrets(
        version=1,
        api_id=12345,
        api_hash="a" * 32,
        string_session="session",
        chat_reference="@vault",
        chat_id=-100123,
        chat_title="Private Vault",
        account_name="Ace",
        web_username="ace",
        password_hash=hash_password("correct-password"),
        cookie_secret="cookie-secret-" * 5,
        port=8181,
        sync_interval_seconds=3600,
    )
    SecretVault(tmp_path).save(config)
    database = Database(tmp_path / "televault.db")
    database.initialise()
    database.upsert_media(
        MediaRecord(
            chat_id=-100123,
            message_id=10,
            dedupe_key="video:10",
            kind="video",
            title="Range test",
            filename="range.mp4",
            caption="",
            mime_type="video/mp4",
            size_bytes=len(VIDEO),
            duration_seconds=10,
            width=1280,
            height=720,
            message_date="2026-08-29T12:00:00+00:00",
        )
    )
    database.upsert_media(
        MediaRecord(
            chat_id=-100123,
            message_id=11,
            dedupe_key="photo:11",
            kind="photo",
            title="Photo test",
            filename="photo.jpg",
            caption="",
            mime_type="image/jpeg",
            size_bytes=len(PHOTO),
            duration_seconds=0,
            width=640,
            height=360,
            message_date="2026-08-29T12:01:00+00:00",
        )
    )


def extract_csrf(html):
    match = re.search(r'name="csrf" value="([^"]+)"', html)
    assert match
    return match.group(1)


def login(client):
    page = client.get("/login")
    token = extract_csrf(page.text)
    response = client.post(
        "/login",
        data={"username": "ace", "password": "correct-password", "csrf": token},
        follow_redirects=False,
    )
    assert response.status_code == 303


def test_login_library_and_security_headers(tmp_path):
    make_config(tmp_path)
    app = create_app(tmp_path, telegram_factory=FakeTelegram)
    with TestClient(app) as client:
        anonymous = client.get("/", follow_redirects=False)
        assert anonymous.status_code == 303
        login(client)
        response = client.get("/")
        assert response.status_code == 200
        assert "Private Vault" in response.text
        assert "Range test" in response.text
        assert response.headers["x-frame-options"] == "DENY"
        assert "frame-ancestors 'none'" in response.headers["content-security-policy"]


def test_library_uses_infinite_scroll_without_numbered_pages(tmp_path):
    make_config(tmp_path)
    database = Database(tmp_path / "televault.db")
    for message_id in range(12, 55):
        database.upsert_media(
            MediaRecord(
                chat_id=-100123,
                message_id=message_id,
                dedupe_key=f"photo:{message_id}",
                kind="photo",
                title=f"Library item {message_id}",
                filename=f"item-{message_id}.jpg",
                caption="",
                mime_type="image/jpeg",
                size_bytes=message_id * 100,
                duration_seconds=0,
                width=1080 if message_id == 54 else 1920,
                height=1920 if message_id == 54 else 1080,
                message_date="2026-08-29T13:00:00+00:00",
            )
        )
    app = create_app(tmp_path, telegram_factory=FakeTelegram)
    with TestClient(app) as client:
        login(client)
        first_batch = client.get("/")
        assert first_batch.status_code == 200
        assert first_batch.text.count('data-media-id="') == 36
        assert "data-infinite-loader" in first_batch.text
        assert "data-infinite-toggle" in first_batch.text
        assert "data-random-toggle" in first_batch.text
        assert "Infinite scroll" in first_batch.text
        assert "media-card portrait" in first_batch.text
        assert 'aria-label="Pagination"' not in first_batch.text

        second_batch = client.get("/api/media?offset=36")
        assert second_batch.status_code == 200
        assert second_batch.text.count('data-media-id="') == 9
        assert second_batch.headers["x-next-offset"] == "45"
        assert second_batch.headers["x-has-more"] == "false"


def test_random_library_redirects_to_a_seeded_stable_feed(tmp_path):
    make_config(tmp_path)
    database = Database(tmp_path / "televault.db")
    for message_id in range(12, 90):
        database.upsert_media(
            MediaRecord(
                chat_id=-100123,
                message_id=message_id,
                dedupe_key=f"video:{message_id}",
                kind="video",
                title=f"Random item {message_id}",
                filename=f"random-{message_id}.mp4",
                caption="",
                mime_type="video/mp4",
                size_bytes=message_id * 100,
                duration_seconds=30,
                width=1920,
                height=1080,
                message_date=f"2026-08-29T14:{message_id % 60:02d}:00+00:00",
            )
        )
    app = create_app(tmp_path, telegram_factory=FakeTelegram)
    with TestClient(app) as client:
        login(client)
        redirect = client.get("/?kind=video&sort=random", follow_redirects=False)
        assert redirect.status_code == 303
        assert "sort=random" in redirect.headers["location"]
        assert "seed=" in redirect.headers["location"]

        first = client.get("/api/media?kind=video&sort=random&seed=991&offset=0")
        second = client.get("/api/media?kind=video&sort=random&seed=991&offset=36")
        first_ids = set(re.findall(r'data-media-id="(\d+)"', first.text))
        second_ids = set(re.findall(r'data-media-id="(\d+)"', second.text))
        assert len(first_ids) == 36
        assert len(second_ids) == 36
        assert first_ids.isdisjoint(second_ids)


def test_watch_page_has_custom_player_and_ordered_next_video(tmp_path):
    make_config(tmp_path)
    database = Database(tmp_path / "televault.db")
    database.upsert_media(
        MediaRecord(
            chat_id=-100123,
            message_id=12,
            dedupe_key="video:12",
            kind="video",
            title="Next video",
            filename="next.mp4",
            caption="",
            mime_type="video/mp4",
            size_bytes=len(VIDEO),
            duration_seconds=20,
            width=1920,
            height=1080,
            message_date="2026-08-29T12:02:00+00:00",
        )
    )
    app = create_app(tmp_path, telegram_factory=FakeTelegram)
    with TestClient(app) as client:
        login(client)
        response = client.get("/media/1?kind=all&sort=oldest")
        assert response.status_code == 200
        assert 'data-player' in response.text
        assert '/static/js/player.js' in response.text
        assert 'data-player-speed="2"' in response.text
        assert 'data-player-fullscreen' in response.text
        assert 'data-next-url="/media/3?kind=all&amp;sort=oldest"' in response.text
        assert "Keyboard shortcuts" in response.text

        player_script = client.get("/static/js/player.js")
        assert player_script.status_code == 200
        for shortcut in ('key === "arrowleft"', 'key === "arrowright"', 'key === "n"', 'key === "f"'):
            assert shortcut in player_script.text


def test_infinite_scroll_endpoint_requires_login(tmp_path):
    make_config(tmp_path)
    app = create_app(tmp_path, telegram_factory=FakeTelegram)
    with TestClient(app) as client:
        assert client.get("/api/media?offset=36").status_code == 401


def test_invalid_password_rejected(tmp_path):
    make_config(tmp_path)
    app = create_app(tmp_path, telegram_factory=FakeTelegram)
    with TestClient(app) as client:
        token = extract_csrf(client.get("/login").text)
        response = client.post(
            "/login",
            data={"username": "ace", "password": "wrong-password", "csrf": token},
        )
        assert response.status_code == 401
        assert "Invalid username or password" in response.text


def test_video_range_streaming(tmp_path):
    make_config(tmp_path)
    app = create_app(tmp_path, telegram_factory=FakeTelegram)
    with TestClient(app) as client:
        login(client)
        response = client.get("/stream/1", headers={"Range": "bytes=100-699"})
        assert response.status_code == 206
        assert response.content == VIDEO[100:700]
        assert response.headers["content-range"] == f"bytes 100-699/{len(VIDEO)}"
        assert response.headers["content-length"] == "600"
        assert response.headers["accept-ranges"] == "bytes"


def test_invalid_video_range_returns_416(tmp_path):
    make_config(tmp_path)
    app = create_app(tmp_path, telegram_factory=FakeTelegram)
    with TestClient(app) as client:
        login(client)
        response = client.get("/stream/1", headers={"Range": "bytes=99999-"})
        assert response.status_code == 416
        assert response.headers["content-range"] == f"bytes */{len(VIDEO)}"


def test_photo_is_fetched_in_memory(tmp_path):
    make_config(tmp_path)
    app = create_app(tmp_path, telegram_factory=FakeTelegram)
    with TestClient(app) as client:
        login(client)
        response = client.get("/stream/2")
        assert response.status_code == 200
        assert response.content == PHOTO
        assert response.headers["cache-control"] == "private, no-store"


def test_stream_requires_login(tmp_path):
    make_config(tmp_path)
    app = create_app(tmp_path, telegram_factory=FakeTelegram)
    with TestClient(app) as client:
        assert client.get("/stream/1").status_code == 401
