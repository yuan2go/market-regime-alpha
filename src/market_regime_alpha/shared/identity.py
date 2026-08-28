"""Validated identities used at target context boundaries."""

from __future__ import annotations

from dataclasses import dataclass
import re
from uuid import UUID, uuid4


_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_KEY = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,199}$")


@dataclass(frozen=True, slots=True)
class AggregateId:
    value: UUID

    @classmethod
    def new(cls) -> AggregateId:
        return cls(uuid4())

    @classmethod
    def parse(cls, value: str | UUID) -> AggregateId:
        return cls(value if isinstance(value, UUID) else UUID(value))

    def __str__(self) -> str:
        return str(self.value)


@dataclass(frozen=True, slots=True)
class ContentHash:
    value: str

    def __post_init__(self) -> None:
        if not _SHA256.fullmatch(self.value):
            raise ValueError("content hash must be 64 lowercase hexadecimal characters")

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class IdempotencyKey:
    value: str

    def __post_init__(self) -> None:
        if not _KEY.fullmatch(self.value):
            raise ValueError("idempotency key has an invalid format")

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, order=True, slots=True)
class FenceToken:
    value: int

    def __post_init__(self) -> None:
        if isinstance(self.value, bool) or self.value < 1:
            raise ValueError("fence token must be a positive integer")

    def __int__(self) -> int:
        return self.value


__all__ = ["AggregateId", "ContentHash", "FenceToken", "IdempotencyKey"]
