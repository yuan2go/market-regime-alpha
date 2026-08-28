"""Typed failures shared by target Application and Infrastructure boundaries."""

from __future__ import annotations


class MraError(RuntimeError):
    """Base failure with a stable machine-readable code."""

    code = "MRA_ERROR"

    def __init__(self, message: str) -> None:
        super().__init__(f"{self.code}: {message}")


class IntegrityError(MraError):
    """Canonical data or content does not satisfy its declared identity."""

    code = "INTEGRITY_ERROR"


class ConflictError(MraError):
    """A concurrent or identity conflict must fail closed."""

    code = "CONFLICT"


class NotFoundError(MraError):
    """A required canonical identity does not exist."""

    code = "NOT_FOUND"


__all__ = ["ConflictError", "IntegrityError", "MraError", "NotFoundError"]
