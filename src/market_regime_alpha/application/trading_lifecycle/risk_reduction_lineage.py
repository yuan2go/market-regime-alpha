"""Cross-domain H4/H5/H6 validation for H4.5 exit directives."""

from __future__ import annotations

from datetime import datetime

from market_regime_alpha.application.operational_research.composite_artifact import (
    VerifiedCompositeOperationalManifest,
)
from market_regime_alpha.application.operational_research.composite_manifest import (
    CompositeOperationalCompositionStatus,
)
from market_regime_alpha.data.contracts import DataEligibility
from market_regime_alpha.evidence.canonical import canonical_hash
from market_regime_alpha.evidence.envelope import EvidenceAuthority
from market_regime_alpha.execution.risk_reduction import (
    FORMAL_OOS_ALPHA_NOT_ESTABLISHED,
    FORMAL_PIT_NOT_ESTABLISHED,
    TRADING_AUTHORITY_NOT_GRANTED,
    OperationalExitDirectiveV2,
)
from market_regime_alpha.portfolio.risk_routes import (
    VerifiedRiskReducingDecisionBundle,
)
from market_regime_alpha.position.assessment import ExitAssessment
from market_regime_alpha.position.thesis_health import (
    VerifiedThesisHealthBundle,
)


def build_operational_exit_directive_v2(
    *,
    exit_assessment: ExitAssessment,
    risk_bundle: VerifiedRiskReducingDecisionBundle,
    health_bundle: VerifiedThesisHealthBundle,
    composite: VerifiedCompositeOperationalManifest,
    created_at: datetime,
) -> OperationalExitDirectiveV2:
    """Bind one actionable H5 assessment to verified H4/H6 authority."""

    decision = risk_bundle.decision
    position = risk_bundle.position
    health = health_bundle.observation
    manifest = composite.manifest
    validate_h5_h6_operational_lineage(
        health_bundle=health_bundle,
        composite=composite,
    )
    if (
        exit_assessment.action.value != decision.action.value
        or exit_assessment.position_snapshot_id != position.snapshot_id
        or exit_assessment.position_version != position.version
        or exit_assessment.thesis_id != decision.thesis_id
        or exit_assessment.thesis_version != health.thesis_version
        or exit_assessment.evidence.artifact_id != health.observation_id
        or exit_assessment.evidence.content_hash != health.content_hash
        or decision.position_snapshot_id != position.snapshot_id
        or decision.position_snapshot_hash
        != canonical_hash(position.to_canonical_dict())
        or decision.position_book_id != position.position_book_id
        or decision.thesis_id != position.thesis_id
        or decision.symbol != position.symbol
        or health.thesis_id != decision.thesis_id
        or health.opportunity_id != position.opportunity_id
        or health.symbol != decision.symbol
    ):
        raise ValueError("exit directive H4/H5/Position scope mismatch")
    assert position.position_book_id is not None
    assert position.opportunity_id is not None
    return OperationalExitDirectiveV2.create(
        exit_assessment_id=exit_assessment.assessment_id,
        exit_assessment_hash=canonical_hash(
            exit_assessment.to_canonical_dict()
        ),
        action=exit_assessment.action,
        thesis_id=decision.thesis_id,
        thesis_version=health.thesis_version,
        opportunity_id=position.opportunity_id,
        position_book_id=position.position_book_id,
        symbol=decision.symbol,
        position_snapshot_id=position.snapshot_id,
        position_snapshot_hash=decision.position_snapshot_hash,
        position_snapshot_version=position.version,
        thesis_health_observation_id=health.observation_id,
        thesis_health_observation_hash=health.content_hash,
        composite_manifest_id=manifest.manifest_id,
        composite_manifest_hash=manifest.content_hash,
        created_at=created_at,
        reason_codes=tuple(
            sorted(
                {
                    *exit_assessment.reason_codes,
                    "REDUCING_RISK_DECISION_REQUIRED",
                    "H6_OPERATIONAL_LINEAGE_VERIFIED",
                    FORMAL_PIT_NOT_ESTABLISHED,
                    FORMAL_OOS_ALPHA_NOT_ESTABLISHED,
                    TRADING_AUTHORITY_NOT_GRANTED,
                }
            )
        ),
    )


def validate_h5_h6_operational_lineage(
    *,
    health_bundle: VerifiedThesisHealthBundle,
    composite: VerifiedCompositeOperationalManifest,
) -> None:
    """Fail closed unless current H5 artifacts descend from exact VERIFIED H6."""

    if not health_bundle.is_latest:
        raise ValueError("H4.5 requires the latest H5 Observation")
    manifest = composite.manifest
    if manifest.status is not CompositeOperationalCompositionStatus.VERIFIED:
        raise ValueError("H4.5 requires a VERIFIED H6 Composite Manifest")
    bundle = health_bundle.input_bundle
    base = (
        bundle.market_regime.envelope,
        bundle.theme_rotation.envelope,
        bundle.capital_evolution.envelope,
        bundle.candidate_set.envelope,
    )
    manifest_pair = (manifest.manifest_id, manifest.content_hash)
    for envelope in base:
        lineage = tuple(
            zip(
                envelope.input_artifact_ids,
                envelope.input_content_hashes,
                strict=True,
            )
        )
        if (
            manifest_pair not in lineage
            or envelope.source_manifest_id
            != manifest.daily_source_manifest_id
            or envelope.source_manifest_hash
            != manifest.daily_source_manifest_hash
            or envelope.data_eligibility is not DataEligibility.EXPLORATORY
            or envelope.evidence_authority
            is not EvidenceAuthority.IMMUTABLE_CONTENT_ADDRESSED_ARTIFACT
        ):
            raise ValueError("H5 artifact is not bound to exact H6 lineage")
    candidate_pair = (
        bundle.candidate_set.envelope.artifact_id,
        bundle.candidate_set.envelope.content_hash,
    )
    signal = bundle.signal_snapshot.envelope
    signal_lineage = tuple(
        zip(
            signal.input_artifact_ids,
            signal.input_content_hashes,
            strict=True,
        )
    )
    signal_pair = (signal.artifact_id, signal.content_hash)
    path = bundle.path_forecast.envelope
    path_lineage = tuple(
        zip(
            path.input_artifact_ids,
            path.input_content_hashes,
            strict=True,
        )
    )
    if (
        candidate_pair not in signal_lineage
        or signal_pair not in path_lineage
        or signal.source_manifest_id != manifest.daily_source_manifest_id
        or signal.source_manifest_hash != manifest.daily_source_manifest_hash
        or path.source_manifest_id != manifest.daily_source_manifest_id
        or path.source_manifest_hash != manifest.daily_source_manifest_hash
        or signal.data_eligibility is not DataEligibility.EXPLORATORY
        or path.data_eligibility is not DataEligibility.EXPLORATORY
        or signal.evidence_authority
        is not EvidenceAuthority.IMMUTABLE_CONTENT_ADDRESSED_ARTIFACT
        or path.evidence_authority
        is not EvidenceAuthority.IMMUTABLE_CONTENT_ADDRESSED_ARTIFACT
    ):
        raise ValueError("H5 Signal/Path chain is not bound to H6 artifacts")
