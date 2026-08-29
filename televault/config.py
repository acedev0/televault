from __future__ import annotations

import base64
import json
import os
import secrets
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from cryptography.fernet import Fernet, InvalidToken


class ConfigurationError(RuntimeError):
    """Raised when TeleVault configuration is missing or cannot be decrypted."""


@dataclass(slots=True)
class AppSecrets:
    version: int
    api_id: int
    api_hash: str
    string_session: str
    chat_reference: str
    chat_id: int
    chat_title: str
    account_name: str
    web_username: str
    password_hash: str
    cookie_secret: str
    port: int = 8181
    sync_interval_seconds: int = 900

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "AppSecrets":
        try:
            return cls(
                version=int(value.get("version", 1)),
                api_id=int(value["api_id"]),
                api_hash=str(value["api_hash"]),
                string_session=str(value["string_session"]),
                chat_reference=str(value["chat_reference"]),
                chat_id=int(value["chat_id"]),
                chat_title=str(value.get("chat_title") or value["chat_reference"]),
                account_name=str(value.get("account_name") or "Telegram account"),
                web_username=str(value["web_username"]),
                password_hash=str(value["password_hash"]),
                cookie_secret=str(value["cookie_secret"]),
                port=int(value.get("port", 8181)),
                sync_interval_seconds=int(value.get("sync_interval_seconds", 900)),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ConfigurationError("The encrypted configuration is incomplete.") from exc


class SecretVault:
    """Encrypt configuration and Telegram authorization using a local master key."""

    def __init__(self, data_dir: str | Path):
        self.data_dir = Path(data_dir).expanduser().resolve()
        self.key_path = self.data_dir / ".master_key"
        self.secrets_path = self.data_dir / "secrets.enc"

    def initialise_directory(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        os.chmod(self.data_dir, 0o700)
        (self.data_dir / "thumbnails").mkdir(parents=True, exist_ok=True)
        os.chmod(self.data_dir / "thumbnails", 0o700)

    def _load_or_create_key(self) -> bytes:
        self.initialise_directory()
        if self.key_path.exists():
            key = self.key_path.read_bytes().strip()
            try:
                Fernet(key)
            except (ValueError, TypeError) as exc:
                raise ConfigurationError("The TeleVault master key is invalid.") from exc
            return key

        key = base64.urlsafe_b64encode(secrets.token_bytes(32))
        self._atomic_write(self.key_path, key + b"\n", 0o600)
        return key

    @staticmethod
    def _atomic_write(path: Path, payload: bytes, mode: int) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        file_descriptor, temporary_name = tempfile.mkstemp(
            dir=path.parent, prefix=f".{path.name}.", suffix=".tmp"
        )
        temporary_path = Path(temporary_name)
        try:
            with os.fdopen(file_descriptor, "wb") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.chmod(temporary_path, mode)
            os.replace(temporary_path, path)
        finally:
            if temporary_path.exists():
                temporary_path.unlink()

    def save(self, config: AppSecrets) -> None:
        key = self._load_or_create_key()
        payload = json.dumps(
            asdict(config), separators=(",", ":"), ensure_ascii=False
        ).encode("utf-8")
        encrypted = Fernet(key).encrypt(payload)
        self._atomic_write(self.secrets_path, encrypted + b"\n", 0o600)

    def load(self) -> AppSecrets:
        if not self.key_path.exists() or not self.secrets_path.exists():
            raise ConfigurationError(
                "TeleVault is not configured. Run the interactive setup first."
            )
        try:
            key = self.key_path.read_bytes().strip()
            encrypted = self.secrets_path.read_bytes().strip()
            payload = Fernet(key).decrypt(encrypted)
            value = json.loads(payload.decode("utf-8"))
        except (InvalidToken, ValueError, OSError, json.JSONDecodeError) as exc:
            raise ConfigurationError(
                "TeleVault could not decrypt its configuration. Restore the matching master key."
            ) from exc
        if not isinstance(value, dict):
            raise ConfigurationError("The encrypted configuration format is invalid.")
        return AppSecrets.from_dict(value)


def resolve_data_dir(explicit: str | Path | None = None) -> Path:
    selected = explicit or os.environ.get("TELEVAULT_DATA_DIR") or "./data"
    return Path(selected).expanduser().resolve()

