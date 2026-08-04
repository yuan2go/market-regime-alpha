"""Crash-safe publication for immutable content-addressed text files."""

from __future__ import annotations

import os
from pathlib import Path
import tempfile


def publish_immutable_text(
    *,
    path: Path,
    payload: str,
    collision_message: str,
) -> Path:
    """Atomically install complete content without overwriting an identity."""

    if not isinstance(path, Path):
        raise TypeError("path must be a Path")
    if not isinstance(payload, str) or not payload:
        raise ValueError("payload must be non-empty text")
    if not isinstance(collision_message, str) or not collision_message.strip():
        raise ValueError("collision_message must be non-empty")
    path.parent.mkdir(parents=True, exist_ok=True)
    file_descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=path.parent,
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(file_descriptor, "w", encoding="utf-8") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.link(temporary_path, path)
        except FileExistsError:
            if path.read_text(encoding="utf-8") != payload:
                raise ValueError(collision_message) from None
        else:
            _fsync_directory(path.parent)
    finally:
        temporary_path.unlink(missing_ok=True)
    return path


def _fsync_directory(directory: Path) -> None:
    descriptor = os.open(directory, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
