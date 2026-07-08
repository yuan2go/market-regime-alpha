"""Small git publisher used by local automation jobs."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import subprocess


@dataclass(frozen=True)
class GitPublishResult:
    changed: bool
    committed: bool
    pushed: bool
    commit_hash: str | None
    message: str


def publish_paths(
    *,
    repo_root: str | Path,
    paths: list[str | Path],
    commit_message: str,
    remote: str = "origin",
    branch: str | None = None,
    push: bool = True,
) -> GitPublishResult:
    """Commit only the requested paths and optionally push them to GitHub."""
    root = Path(repo_root).resolve()
    rel_paths = [_relative_path(root, Path(path)) for path in paths]
    if not rel_paths:
        return GitPublishResult(False, False, False, None, "no paths to publish")

    _run_git(["add", "--", *rel_paths], cwd=root)
    diff = _run_git(["diff", "--cached", "--name-only", "--", *rel_paths], cwd=root).strip()
    if not diff:
        return GitPublishResult(False, False, False, None, "no changes to publish")

    _run_git(["commit", "-m", commit_message, "--", *rel_paths], cwd=root)
    commit_hash = _run_git(["rev-parse", "--short", "HEAD"], cwd=root).strip()
    if not push:
        return GitPublishResult(True, True, False, commit_hash, "committed without push")

    target_branch = branch or _run_git(["branch", "--show-current"], cwd=root).strip()
    if not target_branch:
        raise RuntimeError("cannot push from detached HEAD; pass --git-branch explicitly")

    _run_git(["push", remote, f"HEAD:{target_branch}"], cwd=root, timeout_seconds=60)
    return GitPublishResult(True, True, True, commit_hash, f"pushed to {remote}/{target_branch}")


def _relative_path(root: Path, path: Path) -> str:
    resolved = path if path.is_absolute() else root / path
    return resolved.resolve().relative_to(root).as_posix()


def _run_git(args: list[str], *, cwd: Path, timeout_seconds: int = 30) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout_seconds,
    )
    if completed.returncode != 0:
        details = (completed.stderr or completed.stdout).strip()
        raise RuntimeError(f"git {' '.join(args)} failed: {details}")
    return completed.stdout
