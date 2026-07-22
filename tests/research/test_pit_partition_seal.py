from datetime import date, datetime, timezone

import pytest

from market_regime_alpha.research.pit_partition_v2 import (
    open_persisted_partition,
    persist_partition_seal,
    seal_validation_partition,
)
from tests.research.pit_replication_v2_fixtures import build_test_success_inputs


def test_validation_partition_cannot_overlap_development() -> None:
    inputs = build_test_success_inputs()
    with pytest.raises(ValueError, match="overlap"):
        seal_validation_partition(
            inputs.partition_specification,
            included_sessions=(date(2026, 1, 5), date(2026, 1, 6)),
            excluded_sessions=(),
            development_sessions=(date(2026, 1, 5),),
            calendar_identity="calendar",
            provider_source_hashes=inputs.provider_source_hashes,
            universe_identity="universe",
            sealed_at=datetime.now(timezone.utc),
        )


def test_sealed_partition_cannot_be_resealed() -> None:
    inputs = build_test_success_inputs()
    with pytest.raises(ValueError, match="resealed"):
        seal_validation_partition(
            inputs.partition_specification,
            included_sessions=inputs.partition_seal.included_sessions,
            excluded_sessions=(),
            development_sessions=(),
            calendar_identity="calendar",
            provider_source_hashes=inputs.provider_source_hashes,
            universe_identity="universe",
            sealed_at=datetime.now(timezone.utc),
            existing_partition_ids=frozenset({inputs.partition_specification.partition_id}),
        )


def test_partition_session_outside_frozen_range_fails() -> None:
    inputs = build_test_success_inputs()
    with pytest.raises(ValueError, match="outside"):
        seal_validation_partition(
            inputs.partition_specification,
            included_sessions=(date(2026, 1, 5), date(2026, 1, 7)),
            excluded_sessions=(),
            development_sessions=(),
            calendar_identity="calendar",
            provider_source_hashes=inputs.provider_source_hashes,
            universe_identity="universe",
            sealed_at=datetime.now(timezone.utc),
        )


def test_persisted_partition_has_exactly_one_first_open(tmp_path) -> None:
    inputs = build_test_success_inputs()
    persist_partition_seal(
        output_root=tmp_path,
        specification=inputs.partition_specification,
        seal=inputs.partition_seal,
    )
    receipt = open_persisted_partition(
        output_root=tmp_path,
        seal=inputs.partition_seal,
        opened_at=datetime.now(timezone.utc),
        run_id="test-only-pit-replication-v2-" + "a" * 20,
        reader_implementation_identity="sha256:" + "b" * 64,
    )
    assert receipt.partition_hash == inputs.partition_seal.partition_content_hash
    with pytest.raises(ValueError, match="already been opened"):
        open_persisted_partition(
            output_root=tmp_path,
            seal=inputs.partition_seal,
            opened_at=datetime.now(timezone.utc),
            run_id="test-only-pit-replication-v2-" + "c" * 20,
            reader_implementation_identity="sha256:" + "d" * 64,
        )
    with pytest.raises(ValueError, match="resealed"):
        persist_partition_seal(
            output_root=tmp_path,
            specification=inputs.partition_specification,
            seal=inputs.partition_seal,
        )
