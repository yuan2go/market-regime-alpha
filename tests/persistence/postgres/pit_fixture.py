from __future__ import annotations

from datetime import datetime, timedelta, timezone

from market_regime_alpha.core.identity import ArtifactId, ModelId
from market_regime_alpha.data.contracts import DataEligibility
from market_regime_alpha.data.pit_authority import (
    FormalPITValidationRequest,
    PITArtifactReference,
    PITFactKind,
    PITFactRevision,
    PITRequiredFact,
    PITSourceAuthorityStatus,
    PITSourceQualification,
    PITValidationLineage,
)
from market_regime_alpha.data.postgres_pit_authority import PostgresPITAuthority


UTC = timezone.utc
DECISION_TIME = datetime(2026, 8, 8, 6, 45, tzinfo=UTC)
INGEST_TIME = datetime(2026, 8, 8, 6, 42, tzinfo=UTC)
NOW = datetime(2026, 8, 8, 7, 0, tzinfo=UTC)
HASH_A = "sha256:" + "a" * 64
HASH_B = "sha256:" + "b" * 64
HASH_C = "sha256:" + "c" * 64


class MutableClock:
    def __init__(self, value: datetime) -> None:
        self.value = value

    def __call__(self) -> datetime:
        return self.value


def ref(kind: str, name: str, item_hash: str = HASH_A) -> PITArtifactReference:
    return PITArtifactReference(kind, ArtifactId(name), item_hash)


def pit_lineage(*, adjustment_mode: str = "RAW") -> PITValidationLineage:
    return PITValidationLineage(
        model_id=ModelId("model-a"),
        definition_hash="d" * 64,
        model_lineage_id=ArtifactId("model-lineage-a"),
        model_lineage_hash=HASH_A,
        dataset=ref("DATASET", "dataset-a"),
        source_manifests=(ref("SOURCE_MANIFEST", "source-manifest-a", HASH_B),),
        universe=ref("UNIVERSE", "universe-a"),
        eligibility=ref("ELIGIBILITY", "eligibility-a"),
        feature_definition_ids=("feature-a",),
        feature_materializations=(ref("FEATURE_MATERIALIZATION", "feature-run-a"),),
        configuration=ref("CONFIGURATION", "configuration-a"),
        code_revision="commit-a",
        code_hash=HASH_C,
        validation_protocol=ref("VALIDATION_PROTOCOL", "formal-pit-v1"),
        adjustment_mode=adjustment_mode,
    )


def required_facts() -> tuple[PITRequiredFact, ...]:
    entries = (
        ("calendar:2026-08-08", PITFactKind.TRADING_CALENDAR, "XSHG"),
        ("market:600000.SH:2026-08-08T06:44:00Z", PITFactKind.MARKET_DATA, "600000.SH"),
        ("universe:600000.SH", PITFactKind.UNIVERSE_MEMBERSHIP, "600000.SH"),
        ("trading-status:600000.SH", PITFactKind.TRADING_STATUS, "600000.SH"),
        ("st-status:600000.SH", PITFactKind.ST_STATUS, "600000.SH"),
        ("listing-status:600000.SH", PITFactKind.LISTING_STATUS, "600000.SH"),
        ("eligibility:600000.SH", PITFactKind.TRADING_ELIGIBILITY, "600000.SH"),
        ("feature:feature-run-a", PITFactKind.FEATURE_MATERIALIZATION, "feature-a"),
    )
    return tuple(PITRequiredFact(*entry) for entry in entries)


def _artifact(kind: PITFactKind) -> PITArtifactReference:
    if kind is PITFactKind.MARKET_DATA:
        return pit_lineage().dataset
    if kind is PITFactKind.UNIVERSE_MEMBERSHIP:
        return pit_lineage().universe
    if kind in {
        PITFactKind.TRADING_STATUS,
        PITFactKind.ST_STATUS,
        PITFactKind.LISTING_STATUS,
        PITFactKind.TRADING_ELIGIBILITY,
    }:
        return pit_lineage().eligibility
    if kind is PITFactKind.FEATURE_MATERIALIZATION:
        return pit_lineage().feature_materializations[0]
    return ref(kind.value, f"artifact-{kind.value.lower()}")


def pit_fact(
    required: PITRequiredFact,
    *,
    revision: int = 1,
    supersedes_fact_id: ArtifactId | None = None,
    event_time: datetime | None = None,
    effective_from: datetime | None = None,
    available_at: datetime | None = None,
    recorded_at: datetime | None = None,
    value_json: str = '{"value":true}',
    eligibility: DataEligibility = DataEligibility.FORMAL_RESEARCH,
    artifact: PITArtifactReference | None = None,
    source_manifest: PITArtifactReference | None = None,
) -> PITFactRevision:
    event = event_time or DECISION_TIME - timedelta(minutes=5)
    available = available_at or event + timedelta(seconds=1)
    recorded = recorded_at or available + timedelta(seconds=1)
    return PITFactRevision.create(
        scope_id="daily:2026-08-08",
        logical_key=required.logical_key,
        fact_kind=required.fact_kind,
        subject=required.subject,
        revision=revision,
        supersedes_fact_id=supersedes_fact_id,
        event_time=event,
        effective_from=effective_from or event,
        effective_to=None,
        available_at=available,
        recorded_at=recorded,
        artifact=artifact or _artifact(required.fact_kind),
        source_manifest=source_manifest or pit_lineage().source_manifests[0],
        provider_id="formal-provider",
        provider_contract="formal-provider-contract-v1",
        value_json=value_json,
        data_eligibility=eligibility,
    )


def source_qualification(
    *,
    source_manifest: PITArtifactReference | None = None,
    provider_id: str = "formal-provider",
    provider_contract: str = "formal-provider-contract-v1",
    status: PITSourceAuthorityStatus = PITSourceAuthorityStatus.QUALIFIED,
    revision: int = 1,
    supersedes_qualification_id: ArtifactId | None = None,
) -> PITSourceQualification:
    return PITSourceQualification.create(
        source_manifest=source_manifest or pit_lineage().source_manifests[0],
        provider_id=provider_id,
        provider_contract=provider_contract,
        status=status,
        evidence_references=(
            ref("SOURCE_AUTHORITY_EVIDENCE", f"source-authority-evidence-{revision}"),
        ),
        revision=revision,
        supersedes_qualification_id=supersedes_qualification_id,
        effective_at=INGEST_TIME - timedelta(minutes=2),
        recorded_at=INGEST_TIME - timedelta(minutes=1),
        actor="source-governance-operator",
        reason="explicit test source qualification",
    )


def authorize_source(
    authority: PostgresPITAuthority,
    *,
    source_manifest: PITArtifactReference | None = None,
    idempotency_key: str = "authorize-default-source",
) -> PITSourceQualification:
    return authority.record_source_qualification(
        source_qualification(source_manifest=source_manifest),
        idempotency_key=idempotency_key,
    )


def pit_request(
    *,
    facts: tuple[PITRequiredFact, ...] | None = None,
    adjustment_mode: str = "RAW",
    idempotency_key: str = "validate-pit-a",
) -> FormalPITValidationRequest:
    return FormalPITValidationRequest.create(
        scope_id="daily:2026-08-08",
        decision_time=DECISION_TIME,
        symbols=("600000.SH",),
        required_facts=facts if facts is not None else required_facts(),
        lineage=pit_lineage(adjustment_mode=adjustment_mode),
        actor="pit-validator",
        reason="validate formal PIT",
        idempotency_key=idempotency_key,
    )
