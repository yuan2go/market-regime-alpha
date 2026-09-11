"""Process-local change detection after a complete installed-wheel verification.

Content hashes establish the initial trust; filesystem identities only detect a
change to that already verified installation. Every action re-enumerates the
complete owned resource roster and distribution metadata. File ctime/inode are
trusted OS observations, not protection against an administrator who can modify
the kernel, interpreter or running process. No business or privilege state is
cached here. A detected change requires a new, fully verified process.
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
import os
from pathlib import Path
import stat
import sys
from typing import Any

import market_regime_alpha
from market_regime_alpha.interfaces.deployment_profile import require_installation
from market_regime_alpha.interfaces.prospective_operations import ProspectiveOperationConfig


_Identity = tuple[str, tuple[int, ...]]


def _identity(path: Path, attributes: os.stat_result) -> _Identity:
    mode = attributes.st_mode
    if not (stat.S_ISREG(mode) or stat.S_ISDIR(mode)):
        raise ValueError("OPERATION_INSTALLATION_NON_REGULAR_PATH")
    values: tuple[int, ...] = (attributes.st_dev, attributes.st_ino, mode, attributes.st_uid, attributes.st_gid)
    if stat.S_ISREG(mode):
        values += (attributes.st_size, attributes.st_mtime_ns, attributes.st_ctime_ns)
    # Directory timestamps also change when Python writes ignored bytecode.
    # Their inode/mode and recursively enumerated child roster remain checked.
    return str(path), values


def _tree(root: Path) -> tuple[_Identity, ...]:
    result = [_identity(root, root.lstat())]
    pending = [(root, False)]
    while pending:
        directory, bytecode_directory = pending.pop()
        with os.scandir(directory) as entries:
            for entry in entries:
                path = directory / entry.name
                attributes = entry.stat(follow_symlinks=False)
                is_directory = stat.S_ISDIR(attributes.st_mode)
                if bytecode_directory or entry.name == "__pycache__":
                    if is_directory:
                        pending.append((path, True))
                    elif not (stat.S_ISREG(attributes.st_mode) and entry.name.endswith(".pyc")):
                        raise ValueError("OPERATION_INSTALLATION_UNEXPECTED_CACHE_CONTENT")
                    continue
                if stat.S_ISREG(attributes.st_mode) and entry.name.endswith(".pyc"):
                    continue
                result.append(_identity(path, attributes))
                if is_directory:
                    pending.append((path, False))
    return tuple(sorted(result))


def _metadata_roots() -> tuple[Path, ...]:
    """Match installed metadata discovery without reading RECORD or METADATA."""
    roots: set[Path] = set()
    for name in sys.path:
        path = Path(name or os.getcwd()).resolve()
        if path.is_file():
            # A distribution may be discovered in a sys.path zip archive.
            roots.add(path)
        elif path.is_dir():
            with os.scandir(path) as entries:
                for entry in entries:
                    if entry.name.endswith((".dist-info", ".egg-info")):
                        roots.add(path / entry.name)
    return tuple(sorted(roots))


def _snapshot(wheel: Path, receipt: Path) -> tuple[tuple[str, ...], tuple[_Identity, ...]]:
    try:
        root = Path(market_regime_alpha.__file__).resolve().parent
        identities = list(_tree(root))
        for metadata in _metadata_roots():
            attributes = metadata.lstat()
            identities.extend(_tree(metadata) if stat.S_ISDIR(attributes.st_mode)
                              else (_identity(metadata, attributes),))
        identities.extend((_identity(path, path.lstat()) for path in (wheel, receipt)))
        # A new lookup path must not bypass the frozen metadata search scope.
        search_path = tuple(str(Path(name or os.getcwd()).resolve()) for name in sys.path)
        return search_path, tuple(sorted(identities))
    except OSError as exc:
        raise ValueError("OPERATION_INSTALLATION_UNAVAILABLE") from exc


@dataclass(frozen=True, slots=True)
class VerifiedInstallation:
    configuration_sha256: str
    wheel: Path
    receipt: Path
    principal_name: str
    principal_oid: int
    filesystem_identity: tuple[tuple[str, ...], tuple[_Identity, ...]]

    @classmethod
    def verify(cls, config: ProspectiveOperationConfig) -> VerifiedInstallation:
        """Always perform complete content verification, including on restart."""
        try:
            receipt_path = Path(config.deployment_receipt)
            content = receipt_path.read_bytes()
            if sha256(content).hexdigest() != config.deployment_receipt_sha256:
                raise ValueError("DEPLOYMENT_RECEIPT_MISMATCH")
            wheel = Path(json.loads(content)["installation"]["wheel_path"])
            before = _snapshot(wheel, receipt_path)
            receipt = require_installation(config)
            after = _snapshot(wheel, receipt_path)
            if before != after:
                raise ValueError("OPERATION_INSTALLATION_CHANGED_DURING_VERIFICATION")
            principal = receipt["runtime_principal"]
            return cls(config.content_sha256, wheel, receipt_path, principal["name"], principal["oid"], after)
        except (OSError, KeyError, TypeError, json.JSONDecodeError) as exc:
            raise ValueError("DEPLOYMENT_RECEIPT_UNREADABLE") from exc

    @property
    def runtime_principal(self) -> dict[str, Any]:
        return {"name": self.principal_name, "oid": self.principal_oid}

    def require_unchanged(self, config: ProspectiveOperationConfig) -> None:
        if config.content_sha256 != self.configuration_sha256:
            raise ValueError("OPERATION_INSTALLATION_PROFILE_CHANGED")
        if _snapshot(self.wheel, self.receipt) != self.filesystem_identity:
            raise ValueError("OPERATION_IMPLEMENTATION_CHANGED")
