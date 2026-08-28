"""Local immutable content-addressed bytes with atomic publication."""

from __future__ import annotations

from datetime import datetime, timezone
import errno
import hashlib
import os
from pathlib import Path
import re
import tempfile

from market_regime_alpha.runtime.ports import ByteVerification, PublishedArtifact
from market_regime_alpha.shared.identity import ContentHash


_MEDIA_TYPE = re.compile(
    r"^[A-Za-z0-9][A-Za-z0-9.+-]+/[A-Za-z0-9][A-Za-z0-9.+-]+$"
)


class ArtifactStoreError(RuntimeError):
    """Local content store operation failed closed."""


class LocalArtifactStore:
    """Filesystem adapter; PostgreSQL remains metadata and binding Authority."""

    def __init__(self, root: Path) -> None:
        resolved = root.expanduser().resolve()
        if not resolved.is_absolute():
            raise ValueError("artifact root must resolve to an absolute path")
        self.root = resolved
        self._objects = resolved / "objects"
        self._staging = resolved / "staging"
        self._quarantine = resolved / "quarantine"
        for directory in (self._objects, self._staging, self._quarantine):
            directory.mkdir(parents=True, exist_ok=True)

    def publish_bytes(
        self,
        content: bytes,
        *,
        media_type: str,
        expected_sha256: str | None = None,
    ) -> PublishedArtifact:
        if not isinstance(content, bytes):
            raise TypeError("content must be exact bytes")
        if not _MEDIA_TYPE.fullmatch(media_type):
            raise ValueError("media_type has an invalid format")
        content_sha256 = hashlib.sha256(content).hexdigest()
        if expected_sha256 is not None:
            ContentHash(expected_sha256)
            if content_sha256 != expected_sha256:
                raise ArtifactStoreError("producer hash does not match exact bytes")
        destination = self.object_path(content_sha256)
        destination.parent.mkdir(parents=True, exist_ok=True)
        descriptor, staging_name = tempfile.mkstemp(
            prefix="publish-",
            suffix=".tmp",
            dir=self._staging,
        )
        staging = Path(staging_name)
        try:
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
            if destination.exists():
                verification = self.verify(
                    content_sha256,
                    expected_size=len(content),
                )
                if verification.result != "VERIFIED":
                    raise ArtifactStoreError(
                        "existing content-addressed object failed verification"
                    )
            else:
                try:
                    os.link(staging, destination)
                except OSError as exc:
                    if exc.errno != errno.EEXIST:
                        raise
                    verification = self.verify(
                        content_sha256,
                        expected_size=len(content),
                    )
                    if verification.result != "VERIFIED":
                        raise ArtifactStoreError(
                            "concurrent content-addressed object failed verification"
                        ) from exc
                _fsync_directory(destination.parent)
        finally:
            staging.unlink(missing_ok=True)
        verification = self.verify(content_sha256, expected_size=len(content))
        if verification.result != "VERIFIED":
            raise ArtifactStoreError("published object failed read-after-write verification")
        return PublishedArtifact(
            content_sha256=content_sha256,
            size_bytes=len(content),
            media_type=media_type,
            locator=self.canonical_locator(content_sha256),
        )

    def verify(self, content_sha256: str, *, expected_size: int) -> ByteVerification:
        ContentHash(content_sha256)
        if isinstance(expected_size, bool) or expected_size < 0:
            raise ValueError("expected_size must be non-negative")
        object_file = self.object_path(content_sha256)
        if object_file.is_symlink():
            raise ArtifactStoreError("content-addressed object cannot be a symbolic link")
        if object_file.exists() and not object_file.is_file():
            raise ArtifactStoreError("content-addressed object path is not a regular file")
        if not object_file.is_file():
            return ByteVerification(
                result="MISSING",
                observed_exists=False,
                observed_size_bytes=None,
                observed_sha256=None,
            )
        observed_size = object_file.stat().st_size
        observed_hash = _hash_file(object_file)
        if observed_size != expected_size:
            result = "SIZE_MISMATCH"
        elif observed_hash != content_sha256:
            result = "HASH_MISMATCH"
        else:
            result = "VERIFIED"
        return ByteVerification(
            result=result,
            observed_exists=True,
            observed_size_bytes=observed_size,
            observed_sha256=observed_hash,
        )

    def read_bytes(self, content_sha256: str, *, expected_size: int) -> bytes:
        """Return exact verified bytes; never repair, substitute, or trust the locator."""

        verification = self.verify(content_sha256, expected_size=expected_size)
        if verification.result != "VERIFIED":
            raise ArtifactStoreError(
                f"content-addressed object cannot be read: {verification.result}"
            )
        content = self.object_path(content_sha256).read_bytes()
        if len(content) != expected_size or hashlib.sha256(content).hexdigest() != content_sha256:
            raise ArtifactStoreError("content-addressed object changed during verified read")
        return content

    def list_objects(self) -> tuple[PublishedArtifact, ...]:
        result: list[PublishedArtifact] = []
        if not self._objects.exists():
            return ()
        for shard in sorted(self._objects.iterdir()):
            if (
                shard.is_symlink()
                or not shard.is_dir()
                or not re.fullmatch(r"[0-9a-f]{2}", shard.name)
            ):
                raise ArtifactStoreError(f"unexpected object-store entry: {shard.name}")
            for object_file in sorted(shard.iterdir()):
                if object_file.is_symlink() or not object_file.is_file():
                    raise ArtifactStoreError(
                        f"unexpected object-store entry: {object_file.relative_to(self.root)}"
                    )
                try:
                    ContentHash(object_file.name)
                except ValueError as exc:
                    raise ArtifactStoreError(
                        f"unexpected object-store entry: {object_file.relative_to(self.root)}"
                    ) from exc
                if shard.name != object_file.name[:2]:
                    raise ArtifactStoreError(
                        f"object-store shard does not match hash: {object_file.name}"
                    )
                result.append(
                    PublishedArtifact(
                        content_sha256=object_file.name,
                        size_bytes=object_file.stat().st_size,
                        media_type="application/octet-stream",
                        locator=self.canonical_locator(object_file.name),
                    )
                )
        return tuple(result)

    def canonical_locator(self, content_sha256: str) -> str:
        return str(self.object_path(content_sha256).relative_to(self.root))

    def object_path(self, content_sha256: str) -> Path:
        ContentHash(content_sha256)
        return self._objects / content_sha256[:2] / content_sha256

    def quarantine_path(self, content_sha256: str) -> Path:
        ContentHash(content_sha256)
        return self._quarantine / content_sha256

    def quarantine(self, content_sha256: str) -> None:
        source = self.object_path(content_sha256)
        destination = self.quarantine_path(content_sha256)
        if destination.exists():
            if source.exists():
                raise ArtifactStoreError("artifact exists in both object and quarantine roots")
            return
        if not source.is_file():
            raise ArtifactStoreError("artifact object is missing before quarantine")
        os.replace(source, destination)
        _fsync_directory(source.parent)
        _fsync_directory(destination.parent)

    def is_quarantined(self, content_sha256: str) -> bool:
        return self.quarantine_path(content_sha256).is_file()

    def list_quarantined_hashes(self) -> tuple[str, ...]:
        result: list[str] = []
        for object_file in sorted(self._quarantine.iterdir()):
            if object_file.is_symlink() or not object_file.is_file():
                raise ArtifactStoreError(
                    f"unexpected quarantine entry: {object_file.name}"
                )
            try:
                ContentHash(object_file.name)
            except ValueError as exc:
                raise ArtifactStoreError(
                    f"unexpected quarantine entry: {object_file.name}"
                ) from exc
            result.append(object_file.name)
        return tuple(result)

    def delete_quarantined(self, content_sha256: str) -> None:
        destination = self.quarantine_path(content_sha256)
        if not destination.is_file():
            raise ArtifactStoreError("artifact is not present in quarantine")
        destination.unlink()
        _fsync_directory(destination.parent)

    def object_modified_at(self, content_sha256: str) -> datetime:
        return datetime.fromtimestamp(
            self.object_path(content_sha256).stat().st_mtime,
            tz=timezone.utc,
        )


def _hash_file(object_file: Path) -> str:
    digest = hashlib.sha256()
    with object_file.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _fsync_directory(directory: Path) -> None:
    descriptor = os.open(directory, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


__all__ = ["ArtifactStoreError", "LocalArtifactStore"]
