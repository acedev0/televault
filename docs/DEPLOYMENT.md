# TeleVault deployment guide

TeleVault needs a long-running Python process, one persistent data directory, and an interactive
Telegram user login. Use exactly one running instance for each Telegram session and data directory.

## Before deploying

- Create Telegram API credentials at [my.telegram.org](https://my.telegram.org/).
- Keep the API hash, phone number, OTP, 2FA password, master key, and session files private.
- Choose storage that survives restarts.
- Use a private network, firewall restriction, VPN, or SSH tunnel when serving plain HTTP.

## Linux VPS — recommended

Supported: Ubuntu, Debian, AlmaLinux, and Rocky Linux with systemd.

```bash
bash <(curl -fLsS --proto '=https' --tlsv1.2 https://raw.githubusercontent.com/acedev0/televault/main/install.sh)
```

The installer creates:

- application checkout: `/opt/televault/app`
- Python environment: `/opt/televault/.venv`
- persistent state: `/var/lib/televault`
- service: `televault.service`
- management command: `/usr/local/bin/televaultctl`

Open the selected TCP port in your VPS provider's cloud firewall. If UFW is already active, the
installer adds the port automatically.

### Update

```bash
sudo televaultctl update
```

The update keeps `/var/lib/televault` unchanged, including the encrypted Telegram session, selected
chat, port, media index, and website credentials. It checks the Git revision before restarting and
restores the previous app revision if installation fails.

Enable or disable automatic daily update checks:

```bash
sudo televaultctl auto-update enable
sudo televaultctl auto-update status
sudo televaultctl auto-update disable
```

Permanently uninstall the service and all TeleVault data:

```bash
sudo televaultctl uninstall --yes
```

### Private SSH tunnel

```bash
ssh -L 8181:127.0.0.1:8181 root@YOUR-SERVER-IP
```

Open `http://127.0.0.1:8181` locally.

## Replit

Use the public GitHub import URL:

<https://replit.com/github.com/acedev0/televault>

Replit documents the same `replit.com/github.com/<owner>/<repository>` format for quick public
imports. The repository includes `.replit`, `replit.nix`, and `scripts/replit-run.sh`.

1. Import the repository.
2. Press **Run**.
3. Complete the Telegram and website setup in the console.
4. Open the detected web preview.
5. Keep `data/` private and back it up.

For an always-on deployment, choose a **Reserved VM** and one machine. Replit describes Reserved
VMs as dedicated, continuously running machines suitable for always-on API servers. Publishing
creates a separate snapshot of the app, so back up the state directory before republishing and be
prepared to repeat Telegram setup if the deployed state is replaced.

Recommended Replit settings:

| Setting | Value |
| --- | --- |
| Deployment type | Reserved VM |
| Machines/replicas | One |
| Access | Private or password protected |
| Run command | `bash scripts/replit-run.sh` |
| Health path | `/healthz` |

Replit references:

- [Importing from GitHub](https://docs.replit.com/getting-started/quickstarts/import-from-github)
- [Deployment types](https://docs.replit.com/features/publishing/deployment-types)
- [Publishing model](https://docs.replit.com/features/publishing/overview)

## GitHub Codespaces

Open <https://codespaces.new/acedev0/televault?quickstart=1>. The included dev container installs
the development dependencies and forwards private port `8181`.

In the Codespaces terminal:

```bash
./start.sh
```

Complete setup in the terminal and open the forwarded port notification. Codespaces preserves the
repository workspace across stops and rebuilds, but it is a development environment rather than an
always-on production host. GitHub documents `forwardPorts` and port visibility in the
[Codespaces port-forwarding guide](https://docs.github.com/en/codespaces/developing-in-a-codespace/forwarding-ports-in-your-codespace).

## Docker Compose

Build and run the interactive setup:

```bash
docker compose build
docker compose run --rm televault python -m televault --data-dir /data setup
docker compose up -d
docker compose logs -f
```

The Compose file maps `./data` to `/data` and publishes `8181:8181`. If setup uses another port,
change both sides of the Compose port mapping and the container command or keep port `8181` for the
Docker deployment.

Stop without deleting state:

```bash
docker compose down
```

Do not use `docker compose down -v` unless you intentionally want to delete persistent state.

## Manual Linux/macOS setup

```bash
git clone https://github.com/acedev0/televault.git
cd televault
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
./start.sh
```

`start.sh` performs setup when `data/secrets.enc` does not exist. It honours a platform-provided
`PORT` variable, then `TELEVAULT_PORT`, then the saved setup port.

## Backing up or moving TeleVault

Stop TeleVault before copying state:

```bash
sudo systemctl stop televault
sudo tar -C /var/lib -czf televault-data-backup.tar.gz televault
sudo systemctl start televault
```

The data directory must be restored as one unit because it contains the encrypted configuration,
its master key, SQLite metadata, thumbnails, and runtime settings. Apply restrictive permissions
after restoration and never upload the backup publicly.

## Platforms that do not fit

Serverless and static hosts cannot keep the persistent MTProto connection or state required for
range streaming. Do not deploy TeleVault to Vercel functions, GitHub Pages, or static hosting.
