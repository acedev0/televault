from __future__ import annotations

import argparse
import asyncio
import getpass
import os
import re
import secrets
import socket
import sys
import urllib.request
from pathlib import Path

from telethon import TelegramClient, errors, utils
from telethon.sessions import StringSession

from . import __version__
from .config import AppSecrets, ConfigurationError, SecretVault, resolve_data_dir
from .database import Database
from .indexer import IndexManager, IndexProgress
from .security import hash_password, new_token
from .telegram_client import TelegramMediaClient


USERNAME_PATTERN = re.compile(r"^[A-Za-z0-9_.-]{3,32}$")


def _prompt(label: str, default: str = "") -> str:
    suffix = f" [{default}]" if default else ""
    value = input(f"{label}{suffix}: ").strip()
    return value or default


def _prompt_api_id() -> int:
    while True:
        raw = _prompt("Telegram API ID")
        try:
            value = int(raw)
            if value > 0:
                return value
        except ValueError:
            pass
        print("  Enter the numeric API ID from my.telegram.org.")


def _port_available(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            probe.bind(("0.0.0.0", port))
        except OSError:
            return False
    return True


def _prompt_port() -> int:
    while True:
        raw = _prompt("Website port", "8181")
        try:
            port = int(raw)
        except ValueError:
            print("  Enter a number between 1024 and 65535.")
            continue
        if not 1024 <= port <= 65535:
            print("  Choose a port between 1024 and 65535.")
        elif not _port_available(port):
            print(f"  Port {port} is already in use. Choose another port.")
        else:
            return port


def _prompt_username() -> str:
    while True:
        username = _prompt("Website username")
        if USERNAME_PATTERN.fullmatch(username):
            return username
        print("  Use 3-32 letters, numbers, dots, underscores, or hyphens.")


def _prompt_password() -> str:
    while True:
        password = getpass.getpass("Website password: ")
        if len(password) < 10:
            print("  Use at least 10 characters.")
            continue
        confirmation = getpass.getpass("Confirm website password: ")
        if not secrets.compare_digest(password, confirmation):
            print("  Passwords did not match.")
            continue
        return password


def _public_ip() -> str:
    try:
        request = urllib.request.Request(
            "https://api.ipify.org", headers={"User-Agent": f"TeleVault/{__version__}"}
        )
        with urllib.request.urlopen(request, timeout=5) as response:
            value = response.read(64).decode("ascii").strip()
            if value:
                return value
    except Exception:
        pass
    try:
        return socket.gethostbyname(socket.gethostname())
    except OSError:
        return "SERVER-IP"


async def _telegram_login(api_id: int, api_hash: str, phone: str):
    client = TelegramClient(
        StringSession(),
        api_id,
        api_hash,
        connection_retries=5,
        request_retries=5,
        retry_delay=2,
        flood_sleep_threshold=60,
    )
    await client.connect()
    try:
        sent = await client.send_code_request(phone)
        for attempt in range(3):
            code = _prompt("Telegram login code")
            try:
                await client.sign_in(
                    phone=phone,
                    code=code,
                    phone_code_hash=sent.phone_code_hash,
                )
                break
            except errors.SessionPasswordNeededError:
                password = getpass.getpass("Telegram 2FA password: ")
                await client.sign_in(password=password)
                break
            except errors.PhoneCodeInvalidError:
                if attempt == 2:
                    raise
                print("  That code was invalid. Try again.")
        if not await client.is_user_authorized():
            raise RuntimeError("Telegram login was not completed.")
        return client
    except Exception:
        await client.disconnect()
        raise


async def interactive_setup(data_dir: Path) -> int:
    print()
    print("  TeleVault interactive VPS setup")
    print("  Telegram stores the originals; this server keeps metadata and thumbnails only.")
    print()
    api_id = _prompt_api_id()
    api_hash = getpass.getpass("Telegram API hash: ").strip()
    if len(api_hash) < 16:
        raise RuntimeError("The Telegram API hash does not look valid.")
    phone = _prompt("Telegram phone number with country code")

    print("\n  Requesting a Telegram login code...")
    login_client = await _telegram_login(api_id, api_hash, phone)
    try:
        me = await login_client.get_me()
        account_name = utils.get_display_name(me) or getattr(me, "username", "") or "Telegram account"
        print(f"  Logged in successfully as {account_name}.")

        while True:
            chat_reference = _prompt("Chat username, link, or numeric ID containing the media")
            try:
                entity = await login_client.get_entity(chat_reference)
                break
            except Exception as exc:
                print(f"  Could not open that chat: {exc}")
        chat_id = int(utils.get_peer_id(entity))
        chat_title = utils.get_display_name(entity) or chat_reference
        string_session = login_client.session.save()
        print(f"  Connected to: {chat_title}")
    finally:
        await login_client.disconnect()

    temporary_config = AppSecrets(
        version=1,
        api_id=api_id,
        api_hash=api_hash,
        string_session=string_session,
        chat_reference=chat_reference,
        chat_id=chat_id,
        chat_title=chat_title,
        account_name=account_name,
        web_username="pending",
        password_hash=hash_password(new_token(18)),
        cookie_secret=new_token(48),
    )
    vault = SecretVault(data_dir)
    vault.initialise_directory()
    database = Database(data_dir / "televault.db")
    database.initialise()
    telegram = TelegramMediaClient(temporary_config)
    await telegram.connect()
    indexer = IndexManager(database, telegram, data_dir / "thumbnails")

    last_reported = -1

    def report(progress: IndexProgress) -> None:
        nonlocal last_reported
        if progress.media_found == last_reported and progress.running:
            return
        last_reported = progress.media_found
        line = (
            f"\r  Scanning Telegram... {progress.media_found} media found · "
            f"{progress.added} unique · {progress.duplicates} duplicates skipped"
        )
        print(line.ljust(100), end="" if progress.running else "\n", flush=True)

    try:
        print("\n  Scanning all photos and videos. Large chats can take a few minutes...")
        result = await indexer.scan(full=True, progress=report)
    finally:
        await telegram.disconnect()
    print(
        f"  Scan complete: {result.added} unique media, "
        f"{result.duplicates} duplicate message(s) skipped, "
        f"{result.thumbnails} thumbnail(s) created."
    )

    print()
    port = _prompt_port()
    web_username = _prompt_username()
    password = _prompt_password()
    final_config = AppSecrets(
        version=1,
        api_id=api_id,
        api_hash=api_hash,
        string_session=string_session,
        chat_reference=chat_reference,
        chat_id=chat_id,
        chat_title=chat_title,
        account_name=account_name,
        web_username=web_username,
        password_hash=hash_password(password),
        cookie_secret=new_token(48),
        port=port,
        sync_interval_seconds=900,
    )
    vault.save(final_config)
    runtime_path = data_dir / "runtime.env"
    runtime_path.write_text(
        f"TELEVAULT_DATA_DIR={data_dir}\nTELEVAULT_PORT={port}\n",
        encoding="utf-8",
    )
    os.chmod(runtime_path, 0o600)
    print()
    print("  Configuration saved securely.")
    print(f"  TELEVAULT_READY_URL=http://{_public_ip()}:{port}")
    print(f"  TELEVAULT_PORT={port}")
    return port


async def scan_existing(data_dir: Path, full: bool) -> None:
    config = SecretVault(data_dir).load()
    database = Database(data_dir / "televault.db")
    database.initialise()
    telegram = TelegramMediaClient(config)
    await telegram.connect()
    indexer = IndexManager(database, telegram, data_dir / "thumbnails")

    def report(progress: IndexProgress) -> None:
        print(
            f"\rScanned {progress.scanned_messages} messages · "
            f"{progress.media_found} media · {progress.added} added",
            end="" if progress.running else "\n",
            flush=True,
        )

    try:
        await indexer.scan(full=full, progress=report)
    finally:
        await telegram.disconnect()


async def doctor(data_dir: Path) -> None:
    try:
        config = SecretVault(data_dir).load()
    except ConfigurationError as exc:
        print(f"Configuration: FAILED - {exc}")
        raise SystemExit(1) from exc
    database = Database(data_dir / "televault.db")
    database.initialise()
    print("Configuration: OK")
    print(f"Database: OK ({database.stats()['total']} indexed media)")
    telegram = TelegramMediaClient(config)
    try:
        await telegram.connect()
        print(f"Telegram: OK ({config.chat_title})")
    except Exception as exc:
        print(f"Telegram: FAILED - {exc}")
        raise SystemExit(1) from exc
    finally:
        await telegram.disconnect()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="televault", description="Private Telegram media streaming")
    parser.add_argument("--version", action="version", version=f"TeleVault {__version__}")
    parser.add_argument(
        "--data-dir",
        default=None,
        help="Persistent data directory (default: TELEVAULT_DATA_DIR or ./data)",
    )
    subcommands = parser.add_subparsers(dest="command", required=True)
    subcommands.add_parser("setup", help="Run the interactive Telegram and website setup")
    scan_parser = subcommands.add_parser("scan", help="Index new Telegram media")
    scan_parser.add_argument("--full", action="store_true", help="Read the complete chat history")
    subcommands.add_parser("doctor", help="Check configuration, database, and Telegram access")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    data_dir = resolve_data_dir(args.data_dir)
    try:
        if args.command == "setup":
            asyncio.run(interactive_setup(data_dir))
        elif args.command == "scan":
            asyncio.run(scan_existing(data_dir, bool(args.full)))
        elif args.command == "doctor":
            asyncio.run(doctor(data_dir))
    except KeyboardInterrupt:
        print("\nSetup cancelled.")
        raise SystemExit(130)
    except (ConfigurationError, RuntimeError, errors.RPCError) as exc:
        print(f"\nTeleVault error: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()

