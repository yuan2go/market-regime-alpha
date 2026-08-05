#!/usr/bin/env python3
"""Create the dedicated local PostgreSQL role, database, schema, and .env."""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field
import os
from pathlib import Path
import secrets
import stat
import sys
import tempfile
from urllib.parse import quote, urlsplit, urlunsplit

import psycopg
from psycopg import sql

from market_regime_alpha.persistence.settings import redact_database_url


TARGET_NAME = "market_regime_alpha"
DATABASE_URL_KEY = "MARKET_REGIME_ALPHA_DATABASE_URL"
ADMIN_DATABASE_URL_KEY = "MARKET_REGIME_ALPHA_ADMIN_DATABASE_URL"


class BootstrapError(RuntimeError):
    """Base class for credential-safe bootstrap failures."""


class BootstrapConflictError(BootstrapError):
    """Raised when an existing resource does not match the approved target."""


@dataclass(frozen=True)
class RoleInspection:
    name: str
    can_login: bool
    is_superuser: bool
    can_create_database: bool
    can_create_role: bool
    can_replicate: bool


@dataclass(frozen=True, repr=False)
class PostgresBootstrapConfiguration:
    admin_database_url: str = field(repr=False)
    env_path: Path
    role_name: str = TARGET_NAME
    database_name: str = TARGET_NAME
    schema_name: str = TARGET_NAME

    def __post_init__(self) -> None:
        parts = urlsplit(self.admin_database_url)
        if parts.scheme not in {"postgres", "postgresql"}:
            raise BootstrapError("administrator connection must use PostgreSQL")
        if not parts.hostname or not parts.path.strip("/"):
            raise BootstrapError(
                "administrator connection requires host and database"
            )
        for label, value in (
            ("role_name", self.role_name),
            ("database_name", self.database_name),
            ("schema_name", self.schema_name),
        ):
            if value != TARGET_NAME:
                raise BootstrapError(f"{label} must be {TARGET_NAME}")
        object.__setattr__(self, "env_path", self.env_path.resolve())

    def __repr__(self) -> str:
        return (
            "PostgresBootstrapConfiguration("
            f"admin={redact_database_url(self.admin_database_url)!r}, "
            f"env_path={str(self.env_path)!r})"
        )


def validate_existing_role(role: RoleInspection) -> None:
    if role.name != TARGET_NAME:
        raise BootstrapConflictError("existing role has an unexpected name")
    unsafe = (
        not role.can_login
        or role.is_superuser
        or role.can_create_database
        or role.can_create_role
        or role.can_replicate
    )
    if unsafe:
        raise BootstrapConflictError(
            "existing market_regime_alpha role has unsafe attributes"
        )


def build_application_database_url(
    *,
    host: str,
    port: int,
    password: str,
) -> str:
    if not host:
        raise BootstrapError("application database host is required")
    if isinstance(port, bool) or not (1 <= port <= 65535):
        raise BootstrapError("application database port is invalid")
    if not password:
        raise BootstrapError("generated application credential is empty")
    encoded_user = quote(TARGET_NAME, safe="")
    encoded_secret = quote(password, safe="")
    host_literal = f"[{host}]" if ":" in host and not host.startswith("[") else host
    return (
        f"postgresql://{encoded_user}:{encoded_secret}@{host_literal}:{port}/"
        f"{TARGET_NAME}"
    )


def upsert_env_database_url(env_path: Path, database_url: str) -> None:
    path = env_path.resolve()
    existing = path.read_text(encoding="utf-8") if path.exists() else ""
    lines = existing.splitlines()
    matching = [
        index
        for index, line in enumerate(lines)
        if line.startswith(f"{DATABASE_URL_KEY}=")
    ]
    if len(matching) > 1:
        raise BootstrapConflictError(
            f"duplicate {DATABASE_URL_KEY} entries in {path}"
        )
    replacement = f"{DATABASE_URL_KEY}={database_url}"
    if matching:
        lines[matching[0]] = replacement
    else:
        lines.append(replacement)
    rendered = "\n".join(lines) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        dir=path.parent,
        text=True,
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(rendered)
            handle.flush()
            os.fsync(handle.fileno())
        temporary.chmod(stat.S_IRUSR | stat.S_IWUSR)
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def render_dry_run(configuration: PostgresBootstrapConfiguration) -> str:
    parts = urlsplit(configuration.admin_database_url)
    host = parts.hostname or "<missing-host>"
    port = parts.port or 5432
    return (
        "bootstrap dry run: "
        f"server={host}:{port} role={configuration.role_name} "
        f"database={configuration.database_name} schema={configuration.schema_name} "
        f"env={configuration.env_path} credential=generated-locally"
    )


def bootstrap_postgres(
    configuration: PostgresBootstrapConfiguration,
) -> str:
    parts = urlsplit(configuration.admin_database_url)
    host = parts.hostname
    assert host is not None
    port = parts.port or 5432
    application_secret = secrets.token_urlsafe(32)
    application_url = build_application_database_url(
        host=host,
        port=port,
        password=application_secret,
    )
    try:
        with psycopg.connect(
            configuration.admin_database_url,
            autocommit=True,
        ) as admin_connection:
            _ensure_role(admin_connection, application_secret)
            _ensure_database(admin_connection)
        target_admin_url = _replace_database(
            configuration.admin_database_url,
            TARGET_NAME,
        )
        with psycopg.connect(target_admin_url, autocommit=True) as target_connection:
            _ensure_schema_and_privileges(target_connection)
        with psycopg.connect(application_url) as application_connection:
            row = application_connection.execute(
                "SELECT current_user, current_database(), current_schema()"
            ).fetchone()
            if row != (TARGET_NAME, TARGET_NAME, TARGET_NAME):
                raise BootstrapConflictError(
                    "application connection did not resolve approved authority"
                )
    except BootstrapError:
        raise
    except (psycopg.Error, OSError, ValueError) as exc:
        locator = redact_database_url(configuration.admin_database_url)
        raise BootstrapError(
            f"PostgreSQL bootstrap failed through {locator}"
        ) from exc
    upsert_env_database_url(configuration.env_path, application_url)
    return redact_database_url(application_url)


def _ensure_role(
    connection: psycopg.Connection[tuple[object, ...]],
    application_secret: str,
) -> None:
    row = connection.execute(
        """
        SELECT rolname, rolcanlogin, rolsuper, rolcreatedb, rolcreaterole, rolreplication
        FROM pg_roles
        WHERE rolname = %s
        """,
        (TARGET_NAME,),
    ).fetchone()
    if row is not None:
        validate_existing_role(
            RoleInspection(
                name=str(row[0]),
                can_login=bool(row[1]),
                is_superuser=bool(row[2]),
                can_create_database=bool(row[3]),
                can_create_role=bool(row[4]),
                can_replicate=bool(row[5]),
            )
        )
        connection.execute(
            sql.SQL("ALTER ROLE {} PASSWORD {}").format(
                sql.Identifier(TARGET_NAME),
                sql.Literal(application_secret),
            )
        )
        return
    connection.execute(
        sql.SQL(
            "CREATE ROLE {} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE "
            "NOREPLICATION PASSWORD {}"
        ).format(
            sql.Identifier(TARGET_NAME),
            sql.Literal(application_secret),
        )
    )


def _ensure_database(
    connection: psycopg.Connection[tuple[object, ...]],
) -> None:
    row = connection.execute(
        """
        SELECT database_owner.rolname
        FROM pg_database AS database
        JOIN pg_roles AS database_owner ON database_owner.oid = database.datdba
        WHERE database.datname = %s
        """,
        (TARGET_NAME,),
    ).fetchone()
    if row is not None:
        if str(row[0]) != TARGET_NAME:
            raise BootstrapConflictError(
                "existing market_regime_alpha database has a foreign owner"
            )
        return
    connection.execute(
        sql.SQL(
            "CREATE DATABASE {} OWNER {} ENCODING 'UTF8' TEMPLATE template0"
        ).format(
            sql.Identifier(TARGET_NAME),
            sql.Identifier(TARGET_NAME),
        )
    )


def _ensure_schema_and_privileges(
    connection: psycopg.Connection[tuple[object, ...]],
) -> None:
    row = connection.execute(
        """
        SELECT schema_owner.rolname
        FROM pg_namespace AS namespace
        JOIN pg_roles AS schema_owner ON schema_owner.oid = namespace.nspowner
        WHERE namespace.nspname = %s
        """,
        (TARGET_NAME,),
    ).fetchone()
    if row is None:
        connection.execute(
            sql.SQL("CREATE SCHEMA {} AUTHORIZATION {}").format(
                sql.Identifier(TARGET_NAME),
                sql.Identifier(TARGET_NAME),
            )
        )
    elif str(row[0]) != TARGET_NAME:
        raise BootstrapConflictError(
            "existing market_regime_alpha schema has a foreign owner"
        )
    connection.execute("REVOKE CREATE ON SCHEMA public FROM PUBLIC")
    connection.execute(
        sql.SQL("ALTER ROLE {} IN DATABASE {} SET search_path TO {}, pg_catalog").format(
            sql.Identifier(TARGET_NAME),
            sql.Identifier(TARGET_NAME),
            sql.Identifier(TARGET_NAME),
        )
    )


def _replace_database(database_url: str, database_name: str) -> str:
    parts = urlsplit(database_url)
    return urlunsplit(
        (
            parts.scheme,
            parts.netloc,
            f"/{database_name}",
            parts.query,
            parts.fragment,
        )
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Bootstrap the dedicated market-regime-alpha PostgreSQL authority."
    )
    parser.add_argument(
        "--admin-database-url",
        default=os.getenv(ADMIN_DATABASE_URL_KEY),
        help=f"Administrator DSN; prefer {ADMIN_DATABASE_URL_KEY}.",
    )
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    parser.add_argument("--dry-run", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if not args.admin_database_url:
        print(
            f"{ADMIN_DATABASE_URL_KEY} or --admin-database-url is required",
            file=sys.stderr,
        )
        return 2
    try:
        configuration = PostgresBootstrapConfiguration(
            admin_database_url=str(args.admin_database_url),
            env_path=args.env_file,
        )
        if args.dry_run:
            print(render_dry_run(configuration))
            return 0
        locator = bootstrap_postgres(configuration)
    except BootstrapError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(f"PostgreSQL authority bootstrapped: {locator}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
