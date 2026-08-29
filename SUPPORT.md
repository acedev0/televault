# TeleVault support

## Before opening an issue

1. Read [Troubleshooting](docs/TROUBLESHOOTING.md).
2. Run `sudo televaultctl doctor`.
3. Check the latest service logs with `sudo journalctl -u televault -n 100 --no-pager`.
4. Confirm the problem still occurs on the current `main` branch.

## Include

- operating system and version
- Python version
- TeleVault version or commit
- deployment type: VPS, Docker, Replit, or Codespaces
- exact steps to reproduce
- sanitized error text
- whether the media is a photo/video and its container/codec when relevant

## Never include

- Telegram API ID or API hash
- phone number, OTP, or 2FA password
- StringSession/session files
- `.master_key`, `secrets.enc`, database, or data-directory archives
- website password or cookie
- private IP/domain, chat name, username, captions, filenames, or thumbnails

Security reports belong in GitHub's private **Security → Report a vulnerability** flow described in
[SECURITY.md](SECURITY.md).

