"""Filesystem resource observation for bounded archive operations."""

from __future__ import annotations

from pathlib import Path
import shutil


class FilesystemArchiveResourceInspector:
    def __init__(self, artifact_root: Path) -> None:
        root = artifact_root.expanduser().resolve()
        if not root.is_absolute() or not root.exists() or not root.is_dir():
            raise ValueError("archive Artifact root must be an existing absolute directory")
        self._artifact_root = root

    def available_bytes(self) -> int:
        return shutil.disk_usage(self._artifact_root).free


__all__ = ["FilesystemArchiveResourceInspector"]
