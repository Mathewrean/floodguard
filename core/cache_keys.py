"""Memcached-safe, deterministic cache-key construction."""

from hashlib import sha256
from typing import Any


def cache_key(namespace: str, *parts: Any) -> str:
    """Build an ASCII-only key under Memcached's 250-byte key limit.

    Dynamic inputs such as names and user search text are hashed rather than
    interpolated directly. This prevents spaces/control characters and avoids
    leaking user-supplied values into cache infrastructure.
    """
    digest_source = "\x1f".join(str(part) for part in parts)
    digest = sha256(digest_source.encode('utf-8')).hexdigest()
    return f"fg:{namespace}:{digest}"
