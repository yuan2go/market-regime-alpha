"""Execute every local quality gate and write a commit-bound evidence record."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
from hashlib import sha256
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
from time import monotonic
from typing import Sequence

import psycopg
from psycopg import sql

from market_regime_alpha.application.runtime_operations.verification import (
    CIStatus,
    EngineeringReadiness,
    EngineeringVerificationRecord,
    VerificationGateResult,
    VerificationStatus,
    publish_engineering_verification,
)
from market_regime_alpha.persistence.postgres.migrator import (
    load_packaged_migrations,
)
from market_regime_alpha.persistence.settings import DATABASE_URL_ENV


GATES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("UV_SYNC", ("uv", "sync", "--frozen", "--extra", "dev", "--extra", "postgres")),
    ("DOCS_LINKS", ("uv", "run", "python", "scripts/check_docs_links.py")),
    ("PYTEST", ("uv", "run", "pytest")),
    ("RUFF", ("uv", "run", "ruff", "check", ".")),
    ("MYPY", ("uv", "run", "mypy")),
    ("BUILD", ("uv", "run", "python", "-m", "build")),
    ("GIT_DIFF_CHECK", ("git", "diff", "--check")),
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run local gates and write SHA-bound engineering evidence"
    )
    parser.add_argument("--database-url", default=os.getenv(DATABASE_URL_ENV))
    parser.add_argument("--database-schema", default="market_regime_alpha")
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument(
        "--ci-status",
        choices=tuple(item.value for item in CIStatus),
        default=CIStatus.NOT_RUN.value,
    )
    parser.add_argument("--environment", default="local")
    args = parser.parse_args()
    if not args.database_url:
        parser.error(f"--database-url or {DATABASE_URL_ENV} is required")
    repo_root = Path.cwd().resolve()
    output_root = args.output_root.resolve()
    if repo_root in (output_root, *output_root.parents):
        parser.error("output-root must remain outside the repository")
    output_root.mkdir(parents=True, exist_ok=True)
    build_output = repo_root / "dist"
    if build_output.exists():
        parser.error(
            "repository dist/ must be absent so this run cannot overwrite user artifacts"
        )
    commit_sha = _capture(("git", "rev-parse", "HEAD"), cwd=repo_root).strip()
    if not re.fullmatch(r"[0-9a-f]{40}", commit_sha):
        raise RuntimeError("Git did not return one full commit SHA")
    gates = tuple(
        _run_gate(name, command, repo_root=repo_root, output_root=output_root)
        for name, command in GATES
    )
    if build_output.exists():
        shutil.move(str(build_output), output_root / "build-dist")
    dirty = bool(_capture(("git", "status", "--porcelain"), cwd=repo_root).strip())
    readiness = (
        EngineeringReadiness.ENGINEERING_READY
        if not dirty and all(item.status is VerificationStatus.PASS for item in gates)
        else EngineeringReadiness.ENGINEERING_NOT_READY
    )
    postgres_version, migration_head = _postgres_environment(
        args.database_url,
        args.database_schema,
    )
    record = EngineeringVerificationRecord.create(
        commit_sha=commit_sha,
        python_version=platform.python_version(),
        uv_version=_capture(("uv", "--version"), cwd=repo_root).strip(),
        postgres_version=postgres_version,
        migration_head=migration_head,
        application_schema=args.database_schema,
        environment=args.environment,
        dirty_worktree=dirty,
        gates=gates,
        ci_status=CIStatus(args.ci_status),
        readiness=readiness,
        verified_at=datetime.now(UTC).replace(microsecond=0),
        limitations=(
            "ENGINEERING_EVIDENCE_ONLY",
            "NOT_ALPHA_EVIDENCE",
            "NOT_LIVE_EVIDENCE",
            "NOT_PRODUCTION_AUTHORIZATION",
            "NOT_PROSPECTIVE_EVIDENCE",
        ),
    )
    path = publish_engineering_verification(root=output_root, record=record)
    print(path)
    print(record.readiness.value)
    return 0 if record.readiness is EngineeringReadiness.ENGINEERING_READY else 1


def _run_gate(
    name: str,
    command: tuple[str, ...],
    *,
    repo_root: Path,
    output_root: Path,
) -> VerificationGateResult:
    started = monotonic()
    process = subprocess.run(
        command,
        cwd=repo_root,
        env=os.environ.copy(),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        check=False,
    )
    duration = monotonic() - started
    payload = process.stdout
    log_path = output_root / f"{name.lower()}.log"
    log_path.write_text(payload, encoding="utf-8")
    summary = _gate_summary(name, payload, process.returncode)
    return VerificationGateResult(
        gate=name,
        command=command,
        status=(
            VerificationStatus.PASS
            if process.returncode == 0
            else VerificationStatus.FAIL
        ),
        exit_code=process.returncode,
        duration_seconds=duration,
        output_sha256=sha256(payload.encode("utf-8")).hexdigest(),
        summary=summary,
    )


def _gate_summary(name: str, payload: str, exit_code: int) -> str:
    lines = tuple(line.strip() for line in payload.splitlines() if line.strip())
    if name == "PYTEST":
        matches = tuple(
            line
            for line in lines
            if re.search(r"\b(passed|failed|errors?|skipped)\b", line)
        )
        if matches:
            return matches[-1][:500]
    if lines:
        return lines[-1][:500]
    return f"exit_code={exit_code}; no process output"


def _postgres_environment(database_url: str, schema_name: str) -> tuple[str, int]:
    with psycopg.connect(database_url) as connection:
        connection.execute(
            "SELECT set_config('search_path', %s, false)",
            (f"{schema_name}, pg_catalog",),
        )
        version_row = connection.execute("SHOW server_version").fetchone()
        head_row = connection.execute(
            sql.SQL("SELECT max(version) FROM {}.schema_migrations").format(
                sql.Identifier(schema_name)
            )
        ).fetchone()
    if version_row is None or head_row is None or head_row[0] is None:
        raise RuntimeError("PostgreSQL version or migration head is unavailable")
    migration_head = int(head_row[0])
    packaged_head = max(item.version for item in load_packaged_migrations())
    if migration_head != packaged_head:
        raise RuntimeError(
            f"migration head mismatch: database={migration_head}, packaged={packaged_head}"
        )
    return str(version_row[0]), migration_head


def _capture(command: Sequence[str], *, cwd: Path) -> str:
    return subprocess.run(
        command,
        cwd=cwd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=True,
    ).stdout


if __name__ == "__main__":
    raise SystemExit(main())
