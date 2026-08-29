from __future__ import annotations

import asyncio
import secrets
import time
from collections import defaultdict, deque

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError


_PASSWORD_HASHER = PasswordHasher(
    time_cost=3,
    memory_cost=65536,
    parallelism=2,
    hash_len=32,
    salt_len=16,
)


def hash_password(password: str) -> str:
    if len(password) < 10:
        raise ValueError("The website password must contain at least 10 characters.")
    return _PASSWORD_HASHER.hash(password)


def verify_password(password_hash: str, supplied_password: str) -> bool:
    try:
        return _PASSWORD_HASHER.verify(password_hash, supplied_password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def new_token(length: int = 32) -> str:
    return secrets.token_urlsafe(length)


class LoginRateLimiter:
    """Small in-memory limiter that slows online password guessing."""

    def __init__(self, attempts: int = 5, window_seconds: int = 900):
        self.attempts = attempts
        self.window_seconds = window_seconds
        self._failures: dict[str, deque[float]] = defaultdict(deque)
        self._lock = asyncio.Lock()

    async def allowed(self, identity: str) -> tuple[bool, int]:
        async with self._lock:
            now = time.monotonic()
            failures = self._failures[identity]
            while failures and now - failures[0] > self.window_seconds:
                failures.popleft()
            if len(failures) < self.attempts:
                return True, 0
            retry_after = max(1, int(self.window_seconds - (now - failures[0])))
            return False, retry_after

    async def failure(self, identity: str) -> None:
        async with self._lock:
            self._failures[identity].append(time.monotonic())

    async def success(self, identity: str) -> None:
        async with self._lock:
            self._failures.pop(identity, None)

