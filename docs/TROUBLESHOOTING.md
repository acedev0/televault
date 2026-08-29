# TeleVault troubleshooting

Start with the built-in checks:

```bash
sudo televaultctl status
sudo televaultctl doctor
sudo televaultctl logs
```

## The website does not open

1. Confirm the service is active with `sudo televaultctl status`.
2. Check the selected port in `/var/lib/televault/runtime.env`.
3. Allow that TCP port in the VPS provider firewall.
4. If UFW is active, run `sudo ufw status`.
5. Test locally on the VPS: `curl -i http://127.0.0.1:PORT/healthz`.

## Telegram authorization expired

Run:

```bash
sudo televaultctl configure
```

Complete the phone, OTP, optional 2FA, chat, and website prompts again. Do not paste an OTP into a
public issue or log.

## New media is missing

```bash
sudo televaultctl sync
```

If the incremental scan does not find it:

```bash
sudo televaultctl full-sync
```

Duplicate Telegram media is intentionally represented once.

## A thumbnail is missing

Run a full sync. TeleVault regenerates a preview when its recorded thumbnail file is absent. Some
Telegram documents do not include a usable preview; the protected placeholder is then expected.

## A video downloads but does not play

TeleVault forwards the original container and codec without transcoding. MP4 with H.264 video and
AAC audio has broad browser support. MKV, HEVC, unusual audio codecs, or malformed metadata may not
play even when Telegram can deliver every byte.

## Seeking fails or streaming pauses

- Check `televaultctl logs` for Telegram flood waits or reconnects.
- Avoid several simultaneous streams from the same account.
- Confirm the original file size in Telegram has not changed.
- Test a common MP4/H.264 file to separate browser-codec problems from network problems.

## Replit does not expose the web preview

The launcher honours Replit's `PORT` environment variable. Stop and press **Run** again after setup.
If publishing, choose a web service/Reserved VM and use `bash scripts/replit-run.sh` as the run
command.

## Update failed

```bash
curl -fLsS --proto '=https' --tlsv1.2 https://raw.githubusercontent.com/acedev0/televault/main/install.sh | sudo bash
```

The installer keeps an existing encrypted configuration. If Git cannot fast-forward because files
inside `/opt/televault/app` were edited manually, preserve those edits elsewhere before repairing
the checkout.

## Asking for support

Read [SUPPORT.md](../SUPPORT.md). Remove all credentials, phone numbers, session data, IP addresses,
private chat names, and media titles before sharing logs.

