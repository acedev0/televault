# TeleVault

A private, YouTube-style media library backed directly by one Telegram chat.

- Originals remain in Telegram.
- The VPS stores metadata, small WebP thumbnails, and an encrypted Telegram session.
- Videos support HTTP byte ranges, so browsers can seek without downloading the complete file.
- Photos are fetched into memory when viewed and are never saved as originals.
- Exact Telegram media duplicates are collapsed into one library item.

## One-command VPS installation

For a public repository, log in to a fresh VPS as root and run:

```bash
bash <(curl -Ls https://raw.githubusercontent.com/acedev0/televault/main/install.sh)
```

While the repository is private, install and authenticate GitHub CLI on the VPS, then run:

```bash
export GH_TOKEN="$(gh auth token)"; bash <(gh api -H "Accept: application/vnd.github.raw+json" repos/acedev0/televault/contents/install.sh)
```

The token is passed to Git through a temporary `GIT_ASKPASS` helper and is not inserted into the Git remote URL.

The installer asks for, in order:

1. Telegram API ID
2. Telegram API hash
3. Phone number
4. Telegram login code and optional 2FA password
5. Chat username, link, or numeric ID
6. A full photo/video scan
7. Website port — default `8181`
8. Website username and password

It installs a hardened system service and prints the final address:

```text
http://YOUR-SERVER-IP:8181
```

Supported VPS systems: Ubuntu, Debian, AlmaLinux, and Rocky Linux with systemd.

## Get Telegram API credentials

1. Sign in at [my.telegram.org](https://my.telegram.org/).
2. Open **API development tools**.
3. Create an application.
4. Copy the API ID and API hash into the installer.

Keep the API hash private. It cannot be revoked independently.

## Management commands

```bash
televaultctl status
televaultctl logs
televaultctl restart
televaultctl sync
televaultctl full-sync
televaultctl doctor
televaultctl configure
televaultctl update
```

`sync` checks only newer messages. `full-sync` re-reads the entire chat while retaining duplicate protection.

## What is stored on the VPS

Default persistent directory: `/var/lib/televault`

| Item | Stored? |
| --- | --- |
| Original videos | No |
| Original photos | No |
| Small thumbnails | Yes |
| Search metadata | Yes, SQLite |
| Telegram authorization | Yes, encrypted |
| API hash | Yes, encrypted |
| Website password | Argon2id hash only |

The encryption key and encrypted data live on the same VPS with `0600` permissions. This protects copied files and casual disclosure, but a root-level VPS compromise can access a running service. Back up the entire data directory together and protect it like a password vault.

## Streaming behaviour

TeleVault forwards browser byte-range requests to Telegram through Telethon's offset-based downloader. It does not create a complete temporary video file or permanent chunk cache.

The browser must support the video's existing codec and container. MP4 with H.264/AAC is broadly supported. Formats such as MKV or uncommon codecs may download correctly but fail to play in a browser because TeleVault intentionally does not transcode them.

Telegram may temporarily limit download speed or return flood-wait responses under heavy use. TeleVault uses one persistent account session, retry handling, and a conservative stream concurrency limit.

## Security and HTTP

TeleVault supports plain HTTP because it is designed for a private server, but HTTP does **not** encrypt the website password or streamed media while crossing the network.

For remote access, restrict the VPS firewall to your IP, use WireGuard/Tailscale, or use an SSH tunnel:

```bash
ssh -L 8181:127.0.0.1:8181 root@YOUR-SERVER-IP
```

Then open `http://127.0.0.1:8181`.

Built-in safeguards include:

- Argon2id password hashing
- Signed, HTTP-only, SameSite session cookies
- CSRF protection on login, logout, and sync
- Login rate limiting
- Content Security Policy and anti-framing headers
- Protected thumbnails and stream URLs
- Encrypted Telegram session/API credentials
- A locked-down, non-root systemd service

## Local development

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python -m televault --data-dir ./data setup
./start.sh
```

Run tests:

```bash
.venv/bin/python -m pytest -q
```

## Docker

Run setup interactively first and choose port `8181`:

```bash
docker compose build
docker compose run --rm televault python -m televault --data-dir /data setup
docker compose up -d
```

Open `http://YOUR-SERVER-IP:8181`.

## Architecture

```text
Browser ──HTTP Range──> FastAPI ──offset chunks──> Telegram MTProto
   │                       │
   └── protected UI        ├── SQLite metadata
                           ├── WebP thumbnails
                           └── encrypted StringSession
```

Telegram access is performed using your own user account. Use TeleVault only with media you are authorised to access and follow Telegram's Terms of Service and applicable copyright law.

## License

MIT — see [LICENSE](LICENSE).
