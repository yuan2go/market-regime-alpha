"""PostgreSQL Authority for exact Phase E historical package owners."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from psycopg.types.json import Jsonb

from market_regime_alpha.application.controlled_operation.longitudinal_index import (
    encode_artifact_root_locator,
    resolve_artifact_root_locator,
)
from market_regime_alpha.application.historical_corpus.artifacts import (
    VerifiedHistoricalPackage,
    load_verified_historical_package,
    publish_historical_package,
)
from market_regime_alpha.application.historical_corpus.contracts import (
    HistoricalArtifactKind,
    HistoricalDataOwner,
)
from market_regime_alpha.application.research_validation.common import (
    ValidationArtifactReference,
)
from market_regime_alpha.persistence.postgres.connection import (
    PostgresConnectionFactory,
)
from market_regime_alpha.persistence.postgres.migrator import PostgresMigrator


class HistoricalCorpusOwnerNotFound(KeyError):
    """Raised when an exact PostgreSQL owner reference is absent."""


class HistoricalCorpusIntegrityError(ValueError):
    """Raised for owner, locator, package or projection divergence."""


class PostgresHistoricalCorpusRepository:
    def __init__(
        self,
        factory: PostgresConnectionFactory,
        *,
        artifact_root: Path,
        apply_migrations: bool = True,
    ) -> None:
        self._factory = factory
        self._artifact_root = artifact_root.resolve()
        self._artifact_root.mkdir(parents=True, exist_ok=True)
        if apply_migrations:
            PostgresMigrator().apply_all(factory)

    def publish_and_register(
        self,
        owner: HistoricalDataOwner,
    ) -> VerifiedHistoricalPackage:
        package = publish_historical_package(
            artifact_root=self._artifact_root,
            owner=owner,
        )
        verified = load_verified_historical_package(package)
        self.register(verified)
        return self.load(owner.reference)

    def register(self, package: VerifiedHistoricalPackage) -> None:
        """Register only a fully verified package; all filesystem I/O is pre-transaction."""

        verified = load_verified_historical_package(package.root)
        if verified != package:
            raise HistoricalCorpusIntegrityError(
                "Historical package changed between verification and registration"
            )
        owner = verified.owner
        locator = encode_artifact_root_locator(
            artifact_root=self._artifact_root,
            path=verified.root,
        )
        checksum_by_path = dict(verified.checksums)

        def operation(connection: Any) -> None:
            if owner.parent_reference is not None:
                parent = connection.execute(
                    """
                    SELECT artifact_kind, content_hash
                    FROM historical_corpus_owner
                    WHERE owner_id = %s AND content_hash = %s
                    """,
                    (
                        str(owner.parent_reference.artifact_id),
                        owner.parent_reference.content_hash,
                    ),
                ).fetchone()
                if parent is None or str(parent[0]) != owner.parent_reference.artifact_kind:
                    raise HistoricalCorpusIntegrityError(
                        "Historical parent owner reference mismatch"
                    )
            connection.execute(
                """
                INSERT INTO historical_corpus_owner(
                    owner_id, content_hash, artifact_kind, provider_id,
                    schema_version, normalization_version,
                    parent_owner_id, parent_owner_hash, package_locator,
                    physical_hash, availability_basis, data_eligibility,
                    formal_pit_status, first_market_date, last_market_date,
                    retrieved_at, created_at, coverage_json, manifest_json
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s, %s, %s, %s
                ) ON CONFLICT (owner_id) DO NOTHING
                """,
                (
                    str(owner.owner_id),
                    owner.content_hash,
                    owner.artifact_kind.value,
                    owner.provider_id,
                    owner.schema_version,
                    owner.normalization_version,
                    (
                        str(owner.parent_reference.artifact_id)
                        if owner.parent_reference is not None
                        else None
                    ),
                    (
                        owner.parent_reference.content_hash
                        if owner.parent_reference is not None
                        else None
                    ),
                    locator,
                    verified.physical_hash,
                    owner.availability_basis,
                    owner.data_eligibility,
                    owner.formal_pit_status,
                    owner.first_market_date,
                    owner.last_market_date,
                    owner.retrieved_at,
                    owner.created_at,
                    Jsonb(owner.coverage.to_canonical_dict()),
                    Jsonb(owner.to_canonical_dict()),
                ),
            )
            stored = connection.execute(
                """
                SELECT content_hash, artifact_kind, package_locator, physical_hash,
                       manifest_json
                FROM historical_corpus_owner WHERE owner_id = %s
                """,
                (str(owner.owner_id),),
            ).fetchone()
            if stored is None or (
                str(stored[0]) != owner.content_hash
                or str(stored[1]) != owner.artifact_kind.value
                or str(stored[2]) != locator
                or str(stored[3]) != verified.physical_hash
                or not isinstance(stored[4], Mapping)
                or dict(stored[4]) != owner.to_canonical_dict()
            ):
                raise HistoricalCorpusIntegrityError(
                    "Historical PostgreSQL owner identity conflict"
                )
            for ordinal, partition in enumerate(owner.partitions, 1):
                checksum = checksum_by_path.get(partition.relative_path)
                if checksum is None:
                    raise HistoricalCorpusIntegrityError(
                        "Historical package omits partition checksum"
                    )
                connection.execute(
                    """
                    INSERT INTO historical_corpus_partition(
                        owner_id, owner_hash, ordinal, partition_id,
                        partition_hash, timeframe, first_market_date,
                        last_market_date, symbol_bucket, bucket_count,
                        row_count, symbol_count, relative_path,
                        physical_checksum, partition_json
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s, %s, %s
                    ) ON CONFLICT (owner_id, ordinal) DO NOTHING
                    """,
                    (
                        str(owner.owner_id),
                        owner.content_hash,
                        ordinal,
                        str(partition.partition_id),
                        partition.content_hash,
                        partition.timeframe.value,
                        partition.first_market_date,
                        partition.last_market_date,
                        partition.symbol_bucket,
                        partition.bucket_count,
                        partition.row_count,
                        partition.symbol_count,
                        partition.relative_path,
                        checksum,
                        Jsonb(partition.reference_dict()),
                    ),
                )
            rows = connection.execute(
                """
                SELECT ordinal, partition_json, physical_checksum
                FROM historical_corpus_partition
                WHERE owner_id = %s AND owner_hash = %s
                ORDER BY ordinal
                """,
                (str(owner.owner_id), owner.content_hash),
            ).fetchall()
            expected = tuple(
                (
                    ordinal,
                    partition.reference_dict(),
                    checksum_by_path[partition.relative_path],
                )
                for ordinal, partition in enumerate(owner.partitions, 1)
            )
            actual = tuple(
                (int(row[0]), dict(row[1]), str(row[2])) for row in rows
            )
            if actual != expected:
                raise HistoricalCorpusIntegrityError(
                    "Historical PostgreSQL partition projection conflict"
                )

        self._factory.run_transaction(operation)

    def load(
        self,
        reference: ValidationArtifactReference,
    ) -> VerifiedHistoricalPackage:
        if reference.artifact_kind not in {
            item.value
            for item in (
                HistoricalArtifactKind.RAW_PROVIDER_ARCHIVE,
                HistoricalArtifactKind.NORMALIZED_DATASET,
            )
        }:
            raise HistoricalCorpusIntegrityError(
                "Historical owner reference kind is unsupported"
            )
        with self._factory.connection(read_only=True) as connection:
            row = connection.execute(
                """
                SELECT content_hash, artifact_kind, package_locator, physical_hash,
                       manifest_json
                FROM historical_corpus_owner
                WHERE owner_id = %s AND content_hash = %s
                """,
                (str(reference.artifact_id), reference.content_hash),
            ).fetchone()
            if row is None:
                raise HistoricalCorpusOwnerNotFound(str(reference.artifact_id))
            partition_rows = connection.execute(
                """
                SELECT ordinal, partition_json, physical_checksum
                FROM historical_corpus_partition
                WHERE owner_id = %s AND owner_hash = %s
                ORDER BY ordinal
                """,
                (str(reference.artifact_id), reference.content_hash),
            ).fetchall()
        if str(row[1]) != reference.artifact_kind:
            raise HistoricalCorpusIntegrityError("Historical owner kind mismatch")
        locator = str(row[2])
        package_path = resolve_artifact_root_locator(
            artifact_root=self._artifact_root,
            locator=locator,
        )
        verified = load_verified_historical_package(package_path)
        owner = verified.owner
        if (
            owner.reference != reference
            or owner.to_canonical_dict() != dict(row[4])
            or owner.content_hash != str(row[0])
            or verified.physical_hash != str(row[3])
        ):
            raise HistoricalCorpusIntegrityError(
                "Historical owner and immutable package diverged"
            )
        checksum_by_path = dict(verified.checksums)
        expected_partitions = tuple(
            (
                ordinal,
                partition.reference_dict(),
                checksum_by_path[partition.relative_path],
            )
            for ordinal, partition in enumerate(owner.partitions, 1)
        )
        actual_partitions = tuple(
            (int(item[0]), dict(item[1]), str(item[2])) for item in partition_rows
        )
        if actual_partitions != expected_partitions:
            raise HistoricalCorpusIntegrityError(
                "Historical partition Authority projection diverged"
            )
        return verified


__all__ = [
    "HistoricalCorpusIntegrityError",
    "HistoricalCorpusOwnerNotFound",
    "PostgresHistoricalCorpusRepository",
]
