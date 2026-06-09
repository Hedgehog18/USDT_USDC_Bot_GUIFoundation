from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any


@dataclass
class CacheEntry:
    value: Any
    created_at: datetime


class MarketDataCache:
    """Простий TTL-кеш для read-only market data."""

    def __init__(self, ttl_seconds: int = 5) -> None:
        if ttl_seconds <= 0:
            raise ValueError("TTL кешу має бути більшим за 0.")
        self.ttl = timedelta(seconds=ttl_seconds)
        self._storage: dict[str, CacheEntry] = {}

    def get(self, key: str) -> Any | None:
        entry = self._storage.get(key)
        if entry is None:
            return None

        if datetime.utcnow() - entry.created_at > self.ttl:
            self._storage.pop(key, None)
            return None

        return entry.value

    def set(self, key: str, value: Any) -> None:
        self._storage[key] = CacheEntry(value=value, created_at=datetime.utcnow())

    def clear(self) -> None:
        self._storage.clear()

    def size(self) -> int:
        self._purge_expired()
        return len(self._storage)

    def _purge_expired(self) -> None:
        now = datetime.utcnow()
        expired = [
            key for key, entry in self._storage.items()
            if now - entry.created_at > self.ttl
        ]
        for key in expired:
            self._storage.pop(key, None)
