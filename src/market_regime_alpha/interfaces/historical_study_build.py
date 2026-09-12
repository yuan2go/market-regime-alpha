"""Verify an exact research implementation before publishing owner declarations."""

from dataclasses import dataclass
from email.parser import BytesParser
from hashlib import sha256
from pathlib import Path
import subprocess
from zipfile import ZipFile


@dataclass(frozen=True, slots=True)
class HistoricalBuild:
    content: bytes
    wheel_sha256: str
    lockfile_sha256: str
    ridge_sha256: str
    baseline_sha256: str
    version: str
    package_manager_version: str


def verify_historical_build(*, wheel: Path, lockfile: Path, source_checkout: Path, code_sha: str) -> HistoricalBuild:
    if len(code_sha) != 40 or any(c not in "0123456789abcdef" for c in code_sha):
        raise ValueError("study requires a full implementation Git SHA")
    def git(*args: str) -> str:
        return subprocess.check_output(["git", "-C", str(source_checkout), *args], text=True, stderr=subprocess.PIPE).strip()
    if git("rev-parse", "HEAD") != code_sha or git("diff", "--name-only", "HEAD", "--", "src", "pyproject.toml", "uv.lock"):
        raise ValueError("study source must match the exact committed implementation")
    lock = lockfile.read_bytes()
    if lock != (source_checkout / "uv.lock").read_bytes():
        raise ValueError("study lockfile differs from the committed implementation")
    content = wheel.read_bytes()
    package_root = Path(__file__).resolve().parents[1]
    checkout_root = source_checkout / "src/market_regime_alpha"
    with ZipFile(wheel) as archive:
        packaged = {name.removeprefix("market_regime_alpha/") for name in archive.namelist()
                    if name.startswith("market_regime_alpha/") and name.endswith((".py", ".sql"))}
        for root in (package_root, checkout_root):
            source_files = {path.relative_to(root).as_posix() for path in root.rglob("*")
                            if path.is_file() and path.suffix in {".py", ".sql"}}
            if packaged != source_files:
                raise ValueError("study wheel source roster differs from the executing installation or checkout")
            if any((root / name).read_bytes() != archive.read("market_regime_alpha/" + name) for name in packaged):
                raise ValueError("study wheel bytes differ from the executing installation or checkout")
        metadata_names = [name for name in archive.namelist() if name.endswith(".dist-info/METADATA")]
        if len(metadata_names) != 1:
            raise ValueError("study wheel metadata is ambiguous")
        metadata = BytesParser().parsebytes(archive.read(metadata_names[0]))
        if metadata["Name"] != "market-regime-alpha" or not metadata["Version"]:
            raise ValueError("study wheel distribution identity is invalid")
        ridge_hash = sha256(archive.read("market_regime_alpha/research_qualification/application/deterministic_linear.py")).hexdigest()
        baseline_hash = sha256(archive.read("market_regime_alpha/infrastructure/models/research_baselines.py")).hexdigest()
    return HistoricalBuild(content, sha256(content).hexdigest(), sha256(lock).hexdigest(), ridge_hash, baseline_hash,
        str(metadata["Version"]), subprocess.check_output(["uv", "--version"], text=True).split()[1])
