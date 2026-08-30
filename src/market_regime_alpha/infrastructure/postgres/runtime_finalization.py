"""PostgreSQL adapter for the shared narrow Runtime command finalization port."""

from typing import Any
from uuid import UUID

import psycopg

from market_regime_alpha.infrastructure.postgres.repositories.runtime import (
    PostgresRuntimeRepository,
)
from market_regime_alpha.runtime.ports import AttemptClaim


class PostgresRuntimeCommandFinalization:
    def __init__(self, connection: psycopg.Connection[Any]) -> None:
        self._runtime = PostgresRuntimeRepository(connection)

    def lock_live(self, claim: AttemptClaim) -> None:
        self._runtime.lock_live_claim(claim)

    def lock_live_for_step(
        self,
        claim: AttemptClaim,
        *,
        expected_step_kind: str,
    ) -> None:
        self._runtime.lock_live_claim(
            claim,
            expected_step_kind=expected_step_kind,
        )

    def succeed(
        self,
        claim: AttemptClaim,
        *,
        receipt_id: UUID,
        result_hash: str,
    ) -> tuple[int, int]:
        return self._runtime.succeed_attempt(
            claim,
            receipt_id=receipt_id,
            result_hash=result_hash,
        )

    def fail(
        self,
        claim: AttemptClaim,
        *,
        receipt_id: UUID,
        error_class: str,
        error_code: str,
    ) -> tuple[str, int, int]:
        return self._runtime.fail_attempt(
            claim,
            receipt_id=receipt_id,
            error_class=error_class,
            error_code=error_code,
        )


__all__ = ["PostgresRuntimeCommandFinalization"]
