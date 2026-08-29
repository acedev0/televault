# Security policy

## Reporting a vulnerability

Please use the repository's private **Security → Report a vulnerability** feature. Do not post Telegram sessions, API hashes, phone numbers, passwords, database files, master keys, or VPS addresses in a public issue.

## Secrets

TeleVault never needs secrets committed to Git. Runtime secrets belong only in the persistent data directory. The release archive excludes databases, keys, sessions, thumbnails, `.env` files, and test environments.

## HTTP warning

Plain HTTP is supported by request, but it provides no transport encryption. Prefer a private VPN, an IP-restricted firewall, or an SSH tunnel for remote use.

