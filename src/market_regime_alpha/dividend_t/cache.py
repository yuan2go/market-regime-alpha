"""Realtime state cache abstractions."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class MemoryRealtimeCache:
    values: dict[str, Any] = field(default_factory=dict)

    def get(self, key: str) -> Any:
        return self.values.get(key)

    def set(self, key: str, value: Any) -> None:
        self.values[key] = value


class RedisRealtimeCache:
    def __init__(self, url: str) -> None:
        try:
            import redis
        except ImportError as exc:
            raise RuntimeError("Install redis to use RedisRealtimeCache.") from exc
        self.client = redis.Redis.from_url(url, decode_responses=True)

    def get(self, key: str) -> str | None:
        return self.client.get(key)

    def set(self, key: str, value: str) -> None:
        self.client.set(key, value)
