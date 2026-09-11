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
from importlib.util import MAGIC_NUMBER, source_hash
from io import BytesIO
import json
import marshal
import os
from pathlib import Path
import re
import stat
import struct
import sys
from types import CodeType
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
    # The directory's inode/mode and complete child roster establish identity;
    # each regular child includes its own modification/change timestamps.
    return str(path), values


def _tree(root: Path) -> tuple[_Identity, ...]:
    result = [_identity(root, root.lstat())]
    pending = [root]
    while pending:
        directory = pending.pop()
        with os.scandir(directory) as entries:
            for entry in entries:
                path = directory / entry.name
                attributes = entry.stat(follow_symlinks=False)
                is_directory = stat.S_ISDIR(attributes.st_mode)
                result.append(_identity(path, attributes))
                if is_directory:
                    pending.append(path)
    return tuple(sorted(result))


def _verify_owned_bytecode(root: Path) -> None:
    """Require every executable cache to equal its current verified source.

    Disabling cache writes alone does not disable Python's cache reads. A valid
    timestamp header can accompany an unrelated code object, so header/hash
    checks must be followed by deterministic source compilation comparison.
    """
    pattern = re.compile(rf"(.+)\.{re.escape(str(sys.implementation.cache_tag))}(?:\.opt-([12]))?\.pyc")
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if "__pycache__" in path.relative_to(root).parts and path.suffix != ".pyc":
            raise ValueError("OPERATION_INSTALLATION_UNEXPECTED_CACHE_CONTENT")
        if path.suffix != ".pyc":
            continue
        if path.parent.name == "__pycache__":
            matched = pattern.fullmatch(path.name)
            if matched is None:
                raise ValueError("OPERATION_BYTECODE_CACHE_IDENTITY_INVALID")
            source = path.parent.parent / f"{matched[1]}.py"
            optimization = int(matched[2]) if matched[2] is not None else 0
        else:
            # Legacy adjacent caches must also retain one exact .py source.
            source, optimization = path.with_suffix(".py"), 0
        if not source.is_file() or source.is_symlink() or source.parent.name == "__pycache__":
            raise ValueError("OPERATION_BYTECODE_SOURCE_UNAVAILABLE")
        content, source_bytes = path.read_bytes(), source.read_bytes()
        if len(content) < 16 or content[:4] != MAGIC_NUMBER:
            raise ValueError("OPERATION_BYTECODE_HEADER_INVALID")
        flags = int.from_bytes(content[4:8], "little")
        if flags == 0:
            attributes = source.stat()
            expected_header = struct.pack("<II", int(attributes.st_mtime) & 0xFFFFFFFF, attributes.st_size & 0xFFFFFFFF)
        elif flags in {1, 3}:
            expected_header = source_hash(source_bytes)
        else:
            raise ValueError("OPERATION_BYTECODE_HEADER_INVALID")
        if content[8:16] != expected_header:
            raise ValueError("OPERATION_BYTECODE_SOURCE_HEADER_MISMATCH")
        try:
            stream = BytesIO(content[16:])
            actual = marshal.load(stream)
            expected = compile(source_bytes, str(source), "exec", dont_inherit=True, optimize=optimization)
            if (not isinstance(actual, CodeType) or stream.read()
                    or not _equivalent_code(actual, expected)):
                raise ValueError("OPERATION_BYTECODE_SOURCE_CODE_MISMATCH")
        except (EOFError, TypeError, ValueError, SyntaxError) as exc:
            raise ValueError("OPERATION_BYTECODE_SOURCE_CODE_MISMATCH") from exc


def _equivalent_code(actual: CodeType, expected: CodeType) -> bool:
    # marshal encodings include object sharing/interning flags, so byte equality
    # is stricter than executable equality. Compare every semantic/code-location
    # field instead; filename aliases must resolve to the same exact source.
    attributes = ("co_argcount", "co_posonlyargcount", "co_kwonlyargcount", "co_nlocals",
                  "co_stacksize", "co_flags", "co_code", "co_names", "co_varnames", "co_name",
                  "co_qualname", "co_firstlineno", "co_linetable", "co_exceptiontable", "co_freevars", "co_cellvars")
    return (Path(actual.co_filename).resolve() == Path(expected.co_filename).resolve()
            and all(getattr(actual, name) == getattr(expected, name) for name in attributes)
            and _equivalent_constant(actual.co_consts, expected.co_consts))


def _equivalent_constant(actual: Any, expected: Any) -> bool:
    if type(actual) is not type(expected):
        return False
    if isinstance(actual, CodeType):
        return _equivalent_code(actual, expected)
    if isinstance(actual, tuple):
        return len(actual) == len(expected) and all(_equivalent_constant(a, b) for a, b in zip(actual, expected, strict=True))
    if isinstance(actual, frozenset):
        def key(value: Any) -> tuple[str, str]:
            return type(value).__name__, repr(value)
        return _equivalent_constant(tuple(sorted(actual, key=key)), tuple(sorted(expected, key=key)))
    if isinstance(actual, float):
        return struct.pack("<d", actual) == struct.pack("<d", expected)
    if isinstance(actual, complex):
        return _equivalent_constant(actual.real, expected.real) and _equivalent_constant(actual.imag, expected.imag)
    return actual == expected if actual is None or actual is Ellipsis or isinstance(actual, (bool, int, str, bytes)) else False


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
            if sys.pycache_prefix is not None:
                raise ValueError("OPERATION_EXTERNAL_BYTECODE_CACHE_UNSUPPORTED")
            # Freeze the bytecode roster before verification can trigger any
            # lazy import. Subsequent imports may read only validated caches.
            sys.dont_write_bytecode = True
            receipt_path = Path(config.deployment_receipt)
            content = receipt_path.read_bytes()
            if sha256(content).hexdigest() != config.deployment_receipt_sha256:
                raise ValueError("DEPLOYMENT_RECEIPT_MISMATCH")
            wheel = Path(json.loads(content)["installation"]["wheel_path"])
            before = _snapshot(wheel, receipt_path)
            receipt = require_installation(config)
            _verify_owned_bytecode(Path(market_regime_alpha.__file__).resolve().parent)
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
        if sys.dont_write_bytecode is not True or sys.pycache_prefix is not None:
            raise ValueError("OPERATION_BYTECODE_POLICY_CHANGED")
        if config.content_sha256 != self.configuration_sha256:
            raise ValueError("OPERATION_INSTALLATION_PROFILE_CHANGED")
        if _snapshot(self.wheel, self.receipt) != self.filesystem_identity:
            raise ValueError("OPERATION_IMPLEMENTATION_CHANGED")
