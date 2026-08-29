# Contributing to TeleVault

Contributions that improve reliability, security, compatibility, tests, documentation, or the
existing interface are welcome.

## Development setup

```bash
git clone https://github.com/acedev0/televault.git
cd televault
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python -m pytest -q
```

## Before opening a pull request

```bash
.venv/bin/python -m pytest -q
.venv/bin/python -m compileall -q televault
node --check televault/static/js/app.js
bash -n install.sh start.sh scripts/*.sh
```

- Keep originals in Telegram; do not add full-file or permanent chunk storage.
- Preserve authenticated access for thumbnails, photos, video streams, and APIs.
- Never commit credentials, sessions, databases, media, generated runtime files, or real chat data.
- Add or update tests for behavioural changes.
- Keep deployment documentation accurate about persistence and Telegram OTP setup.
- Use concise commits and explain security-sensitive decisions in the pull request.

For vulnerabilities, follow [SECURITY.md](SECURITY.md) instead of opening a public issue.

