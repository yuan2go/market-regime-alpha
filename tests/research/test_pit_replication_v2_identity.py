import pytest

from market_regime_alpha.research.pit_replication_v2_artifacts import (
    PIT_REPLICATION_V2_IMPLEMENTATION_MODULES,
    PITReplicationRunIdentityV2,
    build_pit_replication_v2_identity,
)
from market_regime_alpha.research.pit_replication_v2_preflight import (
    preflight_xuntou_replication_v2,
)
from market_regime_alpha.research.pit_replication_v2_protocol import (
    frozen_pit_replication_v2_protocol,
)
from market_regime_alpha.research.prr_artifact_schemas import (
    PIT_REPLICATION_BLOCKED_V2_SCHEMA,
    PIT_REPLICATION_INVALID_V2_SCHEMA,
    PIT_REPLICATION_SUCCESS_V2_SCHEMA,
)


def test_pit_v2_identity_owns_an_exact_implementation_module_set() -> None:
    identity = build_pit_replication_v2_identity(
        protocol=frozen_pit_replication_v2_protocol(),
        preflight=preflight_xuntou_replication_v2(None),
    )
    assert set(identity.implementation_module_hashes) == set(PIT_REPLICATION_V2_IMPLEMENTATION_MODULES)
    payload = identity.to_canonical_dict()
    payload["implementation_module_hashes"] = {}
    with pytest.raises(ValueError, match="module set"):
        PITReplicationRunIdentityV2.from_canonical_dict(payload)


def test_pit_v2_status_schemas_have_distinct_exact_file_sets() -> None:
    schemas = (
        PIT_REPLICATION_BLOCKED_V2_SCHEMA,
        PIT_REPLICATION_INVALID_V2_SCHEMA,
        PIT_REPLICATION_SUCCESS_V2_SCHEMA,
    )
    assert len({schema.schema_version for schema in schemas}) == 3
    assert len({schema.required_files for schema in schemas}) == 3
    assert "blocker.json" in PIT_REPLICATION_BLOCKED_V2_SCHEMA.required_files
    assert "validation_errors.json" in PIT_REPLICATION_INVALID_V2_SCHEMA.required_files
    assert "daily_replication_metrics.parquet" in PIT_REPLICATION_SUCCESS_V2_SCHEMA.required_files
