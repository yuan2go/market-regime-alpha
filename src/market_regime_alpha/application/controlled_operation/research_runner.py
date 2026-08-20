"""Controlled Platform research with static Features and no B0/B1 dependency."""

from __future__ import annotations

from dataclasses import dataclass, replace
from decimal import Decimal
from hashlib import sha256
import json
import os
from pathlib import Path
import shutil
import tempfile
from typing import Any, Mapping

from market_regime_alpha.application.controlled_operation.research_config import (
    ControlledCandidateDiscoveryConfig,
    ControlledResearchPipelineConfig,
)
from market_regime_alpha.application.controlled_operation.research_input import (
    ControlledOperationalResearchInput,
)
from market_regime_alpha.core.identity import ArtifactId, FeatureDefinitionId
from market_regime_alpha.core.time import DecisionTime
from market_regime_alpha.data.contracts import DataEligibility
from market_regime_alpha.evidence.canonical import canonical_json, require_sha256
from market_regime_alpha.evidence.envelope import ArtifactEnvelope, EvidenceAuthority
from market_regime_alpha.features.materialization_v2 import VerifiedFeatureBundleV2
from market_regime_alpha.features.technical.catalog import (
    CAPITAL_VOLUME_FEATURE_ID,
    PRICE_ACTION_FEATURE_ID,
)
from market_regime_alpha.features.technical.observables import FeatureValueState
from market_regime_alpha.research.candidate_discovery.contracts import (
    CandidateRecord,
    CandidateSelectionStatus,
    CandidateSet,
)
from market_regime_alpha.research.cross_sectional_ranking import competition_ranks
from market_regime_alpha.research.capital_evolution.contracts import (
    CapitalEvolutionSnapshot,
    CapitalEvolutionState,
)
from market_regime_alpha.research.capital_evolution.model import (
    evaluate_capital_evolution_v0,
)
from market_regime_alpha.research.market_regime.contracts import (
    MarketRegimeSnapshot,
    TradePermission,
)
from market_regime_alpha.research.market_regime.model import evaluate_market_regime_v0
from market_regime_alpha.research.platform_v2.artifact import ResearchLayerStatus
from market_regime_alpha.research.platform_v2.inputs import ResearchContextView
from market_regime_alpha.research.theme_rotation.contracts import (
    RotationState,
    ThemeRotationSnapshot,
)
from market_regime_alpha.research.theme_rotation.model import evaluate_theme_rotation_v0


CONTROLLED_RESEARCH_ARTIFACT_SCHEMA = "controlled-platform-research-artifact-v1"
CONTROLLED_RESEARCH_PACKAGE_SCHEMA = "controlled-platform-research-package-v1"
CONTROLLED_RESEARCH_PACKAGE_FILES = (
    "SHA256SUMS.json",
    "artifact.json",
    "manifest.json",
)

_QUALIFIED_ROTATION = {
    RotationState.STARTING,
    RotationState.STRENGTHENING,
    RotationState.LEADING,
}
_QUALIFIED_CAPITAL = {
    CapitalEvolutionState.ACCUMULATION,
    CapitalEvolutionState.IGNITION,
    CapitalEvolutionState.DIFFUSION,
    CapitalEvolutionState.ACCELERATION,
}


@dataclass(frozen=True, slots=True)
class ResolvedCandidateFeature:
    """One typed Feature value resolved from an exact immutable owner."""

    artifact_id: ArtifactId
    content_hash: str
    value: float | None

    def __post_init__(self) -> None:
        require_sha256("Candidate Feature content hash", self.content_hash)


@dataclass(frozen=True, slots=True)
class ControlledResearchArtifact:
    schema_version: str
    envelope: ArtifactEnvelope
    inputs: ControlledOperationalResearchInput
    configuration: ControlledResearchPipelineConfig
    market_regime: MarketRegimeSnapshot
    theme_rotation: ThemeRotationSnapshot
    capital_evolution: CapitalEvolutionSnapshot
    candidate_set: CandidateSet
    research_status: ResearchLayerStatus
    reason_codes: tuple[str, ...]
    limitations: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.schema_version != CONTROLLED_RESEARCH_ARTIFACT_SCHEMA:
            raise ValueError("unsupported Controlled Research Artifact schema")
        if self.envelope.status != self.research_status.value:
            raise ValueError("Controlled Research status and Envelope mismatch")
        if "B0_B1_PREDICTION_RUNS_NOT_USED" not in self.limitations:
            raise ValueError("Controlled Research B0/B1 authority boundary is missing")
        component_ids = {
            self.market_regime.envelope.artifact_id,
            self.theme_rotation.envelope.artifact_id,
            self.capital_evolution.envelope.artifact_id,
            self.candidate_set.envelope.artifact_id,
        }
        if not component_ids.issubset(set(self.envelope.input_artifact_ids)):
            raise ValueError("Controlled Research Envelope omits component lineage")
        self.envelope.verify_payload(self.artifact_payload())

    @property
    def artifact_id(self) -> ArtifactId:
        return self.envelope.artifact_id

    @property
    def content_hash(self) -> str:
        return self.envelope.content_hash

    def artifact_payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "input_bundle_id": str(self.inputs.input_bundle_id),
            "input_bundle_hash": self.inputs.content_hash,
            "configuration_id": str(self.configuration.configuration_id),
            "configuration_hash": self.configuration.configuration_hash,
            "market_regime_id": str(self.market_regime.envelope.artifact_id),
            "market_regime_hash": self.market_regime.envelope.content_hash,
            "theme_rotation_id": str(self.theme_rotation.envelope.artifact_id),
            "theme_rotation_hash": self.theme_rotation.envelope.content_hash,
            "capital_evolution_id": str(self.capital_evolution.envelope.artifact_id),
            "capital_evolution_hash": self.capital_evolution.envelope.content_hash,
            "candidate_set_id": str(self.candidate_set.envelope.artifact_id),
            "candidate_set_hash": self.candidate_set.envelope.content_hash,
            "research_status": self.research_status.value,
            "reason_codes": list(self.reason_codes),
            "limitations": list(self.limitations),
        }

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "envelope": self.envelope.to_canonical_dict(),
            "inputs": self.inputs.to_canonical_dict(),
            "configuration": self.configuration.to_canonical_dict(),
            "market_regime": self.market_regime.to_canonical_dict(),
            "theme_rotation": self.theme_rotation.to_canonical_dict(),
            "capital_evolution": self.capital_evolution.to_canonical_dict(),
            "candidate_set": self.candidate_set.to_canonical_dict(),
            "research_status": self.research_status.value,
            "reason_codes": list(self.reason_codes),
            "limitations": list(self.limitations),
        }

    @classmethod
    def from_canonical_dict(cls, payload: Mapping[str, Any]) -> ControlledResearchArtifact:
        expected = {
            "schema_version",
            "envelope",
            "inputs",
            "configuration",
            "market_regime",
            "theme_rotation",
            "capital_evolution",
            "candidate_set",
            "research_status",
            "reason_codes",
            "limitations",
        }
        if set(payload) != expected:
            raise ValueError("Controlled Research Artifact fields mismatch")
        return cls(
            schema_version=str(payload["schema_version"]),
            envelope=ArtifactEnvelope.from_canonical_dict(_object(payload["envelope"], "envelope")),
            inputs=ControlledOperationalResearchInput.from_canonical_dict(_object(payload["inputs"], "inputs")),
            configuration=ControlledResearchPipelineConfig.from_canonical_dict(_object(payload["configuration"], "configuration")),
            market_regime=MarketRegimeSnapshot.from_canonical_dict(_dict(payload["market_regime"], "market regime")),
            theme_rotation=ThemeRotationSnapshot.from_canonical_dict(_dict(payload["theme_rotation"], "theme rotation")),
            capital_evolution=CapitalEvolutionSnapshot.from_canonical_dict(_dict(payload["capital_evolution"], "capital evolution")),
            candidate_set=CandidateSet.from_canonical_dict(_dict(payload["candidate_set"], "candidate set")),
            research_status=ResearchLayerStatus(str(payload["research_status"])),
            reason_codes=_strings(payload["reason_codes"], "reason codes"),
            limitations=_strings(payload["limitations"], "limitations"),
        )


@dataclass(frozen=True, slots=True)
class VerifiedControlledResearchArtifact:
    root: Path
    artifact: ControlledResearchArtifact
    checksums_hash: str


class ControlledPlatformResearchRunner:
    """Reusable Platform components plus Controlled Candidate Discovery V1."""

    def run(
        self,
        *,
        inputs: ControlledOperationalResearchInput,
        static_feature_bundle: VerifiedFeatureBundleV2,
        configuration: ControlledResearchPipelineConfig,
        output_root: Path,
        code_revision: str,
    ) -> VerifiedControlledResearchArtifact:
        artifact = self.compute(
            inputs=inputs,
            static_feature_bundle=static_feature_bundle,
            configuration=configuration,
            code_revision=code_revision,
        )
        path = publish_controlled_research_artifact(root=output_root, artifact=artifact)
        verified = load_verified_controlled_research_artifact(path)
        if verified.artifact != artifact:
            raise ValueError("published Controlled Research semantic mismatch")
        return verified

    def compute(
        self,
        *,
        inputs: ControlledOperationalResearchInput,
        static_feature_bundle: VerifiedFeatureBundleV2,
        configuration: ControlledResearchPipelineConfig,
        code_revision: str,
    ) -> ControlledResearchArtifact:
        _validate_static_feature_authority(inputs, static_feature_bundle)
        market = evaluate_market_regime_v0(inputs, configuration.market_regime, code_revision=code_revision)
        themes = evaluate_theme_rotation_v0(inputs, configuration.theme_rotation, code_revision=code_revision)
        capital = evaluate_capital_evolution_v0(
            inputs,
            themes,
            configuration.capital_evolution,
            code_revision=code_revision,
        )
        candidates = discover_controlled_candidates(
            inputs=inputs,
            static_feature_bundle=static_feature_bundle,
            market_regime=market,
            theme_rotation=themes,
            capital_evolution=capital,
            configuration=configuration.candidate_discovery,
            code_revision=code_revision,
        )
        blocked = not candidates.selected
        status = (
            ResearchLayerStatus.RESEARCH_BLOCKED
            if blocked
            else ResearchLayerStatus.RESEARCH_RESTRICTED
            if market.trade_permission is not TradePermission.ALLOW
            else ResearchLayerStatus.RESEARCH_READY
        )
        reasons = tuple(
            sorted(
                {
                    f"RESEARCH_STATUS_{status.value}",
                    *candidates.reason_codes,
                    "CONTROLLED_CANDIDATE_DISCOVERY_WITHOUT_B0_B1",
                }
            )
        )
        limitations = tuple(
            sorted(
                {
                    *inputs.limitations,
                    *configuration.assumptions,
                    "B0_B1_PREDICTION_RUNS_NOT_USED",
                    "FORMAL_OOS_ALPHA_NOT_ESTABLISHED",
                    "FORMAL_PIT_NOT_ESTABLISHED",
                    "TRADING_AUTHORITY_NOT_GRANTED",
                }
            )
        )
        payload = {
            "schema_version": CONTROLLED_RESEARCH_ARTIFACT_SCHEMA,
            "input_bundle_id": str(inputs.input_bundle_id),
            "input_bundle_hash": inputs.content_hash,
            "configuration_id": str(configuration.configuration_id),
            "configuration_hash": configuration.configuration_hash,
            "market_regime_id": str(market.envelope.artifact_id),
            "market_regime_hash": market.envelope.content_hash,
            "theme_rotation_id": str(themes.envelope.artifact_id),
            "theme_rotation_hash": themes.envelope.content_hash,
            "capital_evolution_id": str(capital.envelope.artifact_id),
            "capital_evolution_hash": capital.envelope.content_hash,
            "candidate_set_id": str(candidates.envelope.artifact_id),
            "candidate_set_hash": candidates.envelope.content_hash,
            "research_status": status.value,
            "reason_codes": list(reasons),
            "limitations": list(limitations),
        }
        component_pairs = tuple(
            sorted(
                (
                    (inputs.input_bundle_id, inputs.content_hash),
                    (market.envelope.artifact_id, market.envelope.content_hash),
                    (themes.envelope.artifact_id, themes.envelope.content_hash),
                    (capital.envelope.artifact_id, capital.envelope.content_hash),
                    (candidates.envelope.artifact_id, candidates.envelope.content_hash),
                ),
                key=lambda item: str(item[0]),
            )
        )
        envelope = ArtifactEnvelope.create(
            artifact_type="CONTROLLED_RESEARCH_LAYER_ARTIFACT",
            artifact_payload=payload,
            decision_date=static_feature_bundle.artifact.decision_time.date(),
            decision_time=DecisionTime(static_feature_bundle.artifact.decision_time),
            created_at=inputs.created_at,
            code_revision=code_revision,
            configuration_id=configuration.configuration_id,
            configuration_hash=configuration.configuration_hash,
            source_manifest_id=inputs.source_manifest.source_manifest_id,
            source_manifest_hash=inputs.source_manifest.content_hash,
            input_artifact_ids=tuple(item[0] for item in component_pairs),
            input_content_hashes=tuple(item[1] for item in component_pairs),
            model_id=None,
            model_version=None,
            data_eligibility=DataEligibility.EXPLORATORY,
            evidence_authority=EvidenceAuthority.IMMUTABLE_CONTENT_ADDRESSED_ARTIFACT,
            status=status.value,
            reason_codes=reasons,
            limitations=limitations,
        )
        return ControlledResearchArtifact(
            schema_version=CONTROLLED_RESEARCH_ARTIFACT_SCHEMA,
            envelope=envelope,
            inputs=inputs,
            configuration=configuration,
            market_regime=market,
            theme_rotation=themes,
            capital_evolution=capital,
            candidate_set=candidates,
            research_status=status,
            reason_codes=reasons,
            limitations=limitations,
        )

    def replay(
        self,
        *,
        path: Path,
        static_feature_bundle: VerifiedFeatureBundleV2,
    ) -> VerifiedControlledResearchArtifact:
        verified = load_verified_controlled_research_artifact(path)
        artifact = verified.artifact
        replayed = self.compute(
            inputs=artifact.inputs,
            static_feature_bundle=static_feature_bundle,
            configuration=artifact.configuration,
            code_revision=artifact.envelope.code_revision,
        )
        if replayed != artifact:
            raise ValueError("Controlled Research replay divergence")
        return verified


def discover_controlled_candidates(
    *,
    inputs: ControlledOperationalResearchInput,
    static_feature_bundle: VerifiedFeatureBundleV2,
    market_regime: MarketRegimeSnapshot,
    theme_rotation: ThemeRotationSnapshot,
    capital_evolution: CapitalEvolutionSnapshot,
    configuration: ControlledCandidateDiscoveryConfig,
    code_revision: str,
    dynamic_pool_membership: Mapping[str, bool] | None = None,
    dynamic_pool_reference: tuple[ArtifactId, str] | None = None,
) -> CandidateSet:
    resolved: dict[tuple[str, str, str], ResolvedCandidateFeature] = {}
    for symbol in inputs.operational_universe.symbols:
        for feature_id, output_id in (
            (PRICE_ACTION_FEATURE_ID, "return_3"),
            (CAPITAL_VOLUME_FEATURE_ID, "amount_ratio_5"),
        ):
            artifact, value = _decimal_feature(
                static_feature_bundle,
                symbol,
                feature_id,
                output_id,
            )
            if artifact is not None:
                resolved[(symbol, feature_id, output_id)] = ResolvedCandidateFeature(
                    artifact_id=artifact.artifact_id,
                    content_hash=artifact.content_hash,
                    value=value,
                )
    return discover_controlled_candidates_from_resolved_features(
        inputs=inputs,
        universe_symbols=inputs.operational_universe.symbols,
        resolved_features=resolved,
        feature_bundle_reference=(
            static_feature_bundle.artifact.bundle_id,
            static_feature_bundle.artifact.content_hash,
        ),
        decision_time=DecisionTime(static_feature_bundle.artifact.decision_time),
        market_regime=market_regime,
        theme_rotation=theme_rotation,
        capital_evolution=capital_evolution,
        configuration=configuration,
        code_revision=code_revision,
        dynamic_pool_membership=dynamic_pool_membership,
        dynamic_pool_reference=dynamic_pool_reference,
    )


def discover_controlled_candidates_from_resolved_features(
    *,
    inputs: ResearchContextView,
    universe_symbols: tuple[str, ...],
    resolved_features: Mapping[tuple[str, str, str], ResolvedCandidateFeature],
    feature_bundle_reference: tuple[ArtifactId, str],
    decision_time: DecisionTime,
    market_regime: MarketRegimeSnapshot,
    theme_rotation: ThemeRotationSnapshot,
    capital_evolution: CapitalEvolutionSnapshot,
    configuration: ControlledCandidateDiscoveryConfig,
    code_revision: str,
    dynamic_pool_membership: Mapping[str, bool] | None = None,
    dynamic_pool_reference: tuple[ArtifactId, str] | None = None,
) -> CandidateSet:
    """Run the canonical Candidate gates over owner-resolved Feature values."""

    if universe_symbols != tuple(sorted(set(universe_symbols))):
        raise ValueError("Candidate Universe symbols must be unique and sorted")
    require_sha256("Candidate Feature bundle hash", feature_bundle_reference[1])
    if (dynamic_pool_membership is None) != (dynamic_pool_reference is None):
        raise ValueError(
            "Dynamic Pool membership and lineage reference must be supplied together"
        )
    if dynamic_pool_membership is not None and set(dynamic_pool_membership) != set(
        universe_symbols
    ):
        raise ValueError("Dynamic Pool must preserve the complete Universe cross section")
    theme_by_id = {item.theme_id: item for item in theme_rotation.themes}
    capital_by_symbol = {item.symbol: item for item in capital_evolution.symbols}
    membership_by_symbol = {item.symbol: item for item in inputs.theme_memberships}
    observations = {item.symbol: item for item in inputs.symbol_observations}
    records: list[CandidateRecord] = []
    for symbol in universe_symbols:
        membership = membership_by_symbol.get(symbol)
        observation = observations.get(symbol)
        theme = theme_by_id.get(membership.primary_theme_id) if membership else None
        capital = capital_by_symbol.get(symbol)
        price_feature = resolved_features.get(
            (symbol, PRICE_ACTION_FEATURE_ID, "return_3")
        )
        volume_feature = resolved_features.get(
            (symbol, CAPITAL_VOLUME_FEATURE_ID, "amount_ratio_5")
        )
        price = price_feature.value if price_feature is not None else None
        volume = volume_feature.value if volume_feature is not None else None
        input_ids = tuple(
            sorted(
                {
                    item.artifact_id
                    for item in (price_feature, volume_feature)
                    if item is not None
                },
                key=str,
            )
        )
        feature_ids = tuple(FeatureDefinitionId(value) for value in (PRICE_ACTION_FEATURE_ID, CAPITAL_VOLUME_FEATURE_ID))
        reasons: tuple[str, ...]
        state = CandidateSelectionStatus.DATA_INSUFFICIENT
        score: float | None = None
        if (
            dynamic_pool_membership is not None
            and not dynamic_pool_membership[symbol]
        ):
            state = CandidateSelectionStatus.REJECTED
            reasons = ("DYNAMIC_POOL_EXCLUDED",)
        elif market_regime.trade_permission is TradePermission.PROHIBIT:
            state = CandidateSelectionStatus.REJECTED
            reasons = ("MARKET_REGIME_PROHIBITS_RISK",)
        elif membership is None:
            reasons = ("THEME_MEMBERSHIP_MISSING",)
        elif observation is None:
            reasons = ("SYMBOL_RESEARCH_OBSERVATION_MISSING",)
        elif not observation.liquidity_eligible:
            state = CandidateSelectionStatus.REJECTED
            reasons = ("INSUFFICIENT_LIQUIDITY",)
        elif not observation.history_complete:
            state = CandidateSelectionStatus.REJECTED
            reasons = ("INSUFFICIENT_HISTORY",)
        elif not observation.status_known:
            state = CandidateSelectionStatus.REJECTED
            reasons = ("TRADING_STATUS_UNKNOWN",)
        elif theme is None or theme.rotation_state not in _QUALIFIED_ROTATION:
            state = CandidateSelectionStatus.REJECTED
            reasons = ("THEME_ROTATION_NOT_QUALIFIED",)
        elif capital is None or capital.capital_evolution_state not in _QUALIFIED_CAPITAL:
            state = CandidateSelectionStatus.REJECTED
            reasons = ("CAPITAL_EVOLUTION_NOT_QUALIFIED",)
        elif price is None or volume is None or theme.rotation_score is None or capital.capital_evolution_score is None:
            reasons = ("STATIC_FEATURES_INCOMPLETE",)
        else:
            market_score = _market_score(market_regime)
            if market_score is None:
                reasons = ("MARKET_REGIME_SCORE_INCOMPLETE",)
            else:
                score = (
                    _unit(market_score) * configuration.market_regime_weight
                    + _unit(theme.rotation_score) * configuration.theme_rotation_weight
                    + _unit(capital.capital_evolution_score) * configuration.capital_evolution_weight
                    + _unit(_clip(price / configuration.price_action_scale)) * configuration.price_action_weight
                    + _unit(_clip((volume - 1.0) / configuration.volume_ratio_scale)) * configuration.volume_structure_weight
                )
                state = CandidateSelectionStatus.WATCHLIST
                reasons = (
                    "CONTROLLED_CANDIDATE_GATES_PASSED",
                    "NO_B0_B1_PREDICTION_FACTOR",
                )
        records.append(
            CandidateRecord(
                symbol=symbol,
                primary_theme_id=membership.primary_theme_id if membership else None,
                supporting_theme_ids=membership.supporting_theme_ids if membership else (),
                market_regime_status=market_regime.market_state,
                theme_rotation_state=(theme.rotation_state if theme else RotationState.DATA_INSUFFICIENT),
                capital_evolution_state=(capital.capital_evolution_state if capital else CapitalEvolutionState.DATA_INSUFFICIENT),
                market_regime_score=_market_score(market_regime),
                theme_score=theme.rotation_score if theme else None,
                capital_evolution_score=(capital.capital_evolution_score if capital else None),
                candidate_discovery_score=score,
                rank=None,
                selection_status=state,
                reason_codes=reasons,
                source_feature_ids=feature_ids,
                input_artifact_ids=input_ids,
            )
        )
    viable_by_symbol = {
        item.symbol: item
        for item in records
        if item.selection_status is CandidateSelectionStatus.WATCHLIST
        and item.candidate_discovery_score is not None
    }
    viable_scores = {
        symbol: item.candidate_discovery_score
        for symbol, item in viable_by_symbol.items()
        if item.candidate_discovery_score is not None
    }
    ranks = competition_ranks(viable_scores, higher_is_better=True)
    viable = sorted(
        viable_by_symbol.values(),
        key=lambda item: (ranks[item.symbol], item.symbol),
    )
    enough = len(viable) >= configuration.minimum_candidate_population
    selected_count = sum(
        1 for item in viable if ranks[item.symbol] <= configuration.top_n
    )
    boundary_tie_expanded = selected_count > min(configuration.top_n, len(viable))
    ranked = {
        item.symbol: replace(
            item,
            rank=ranks[item.symbol],
            selection_status=(
                CandidateSelectionStatus.SELECTED
                if enough and ranks[item.symbol] <= configuration.top_n
                else CandidateSelectionStatus.WATCHLIST
            ),
            reason_codes=tuple(
                dict.fromkeys(
                    (
                        *item.reason_codes,
                        "CANDIDATE_SELECTED"
                        if enough and ranks[item.symbol] <= configuration.top_n
                        else "CANDIDATE_WATCHLIST"
                        if enough
                        else "CANDIDATE_POPULATION_INSUFFICIENT",
                    )
                )
            ),
        )
        for item in viable
    }
    finalized = tuple(ranked.get(item.symbol, item) for item in sorted(records, key=lambda item: item.symbol))
    reasons = tuple(
        sorted(
            {
                "CANDIDATE_SET_IS_NOT_RECOMMENDATION",
                "CONTROLLED_CANDIDATE_DISCOVERY_WITHOUT_B0_B1",
                *(("CANDIDATE_POPULATION_INSUFFICIENT",) if not enough else ()),
                *(("CANDIDATE_BOUNDARY_TIE_EXPANDED",) if boundary_tie_expanded and enough else ()),
            }
        )
    )
    payload = {
        "records": [item.to_canonical_dict() for item in finalized],
        "minimum_candidate_population": configuration.minimum_candidate_population,
        "reason_codes": list(reasons),
    }
    lineage: dict[ArtifactId, str] = {
        inputs.input_bundle_id: inputs.content_hash,
        feature_bundle_reference[0]: feature_bundle_reference[1],
        market_regime.envelope.artifact_id: market_regime.envelope.content_hash,
        theme_rotation.envelope.artifact_id: theme_rotation.envelope.content_hash,
        capital_evolution.envelope.artifact_id: capital_evolution.envelope.content_hash,
    }
    if dynamic_pool_reference is not None:
        pool_id, pool_hash = dynamic_pool_reference
        lineage[pool_id] = pool_hash
    by_id = {
        item.artifact_id: item.content_hash for item in resolved_features.values()
    }
    for record in finalized:
        for artifact_id in record.input_artifact_ids:
            lineage[artifact_id] = by_id[artifact_id]
    ordered = tuple(sorted(lineage.items(), key=lambda item: str(item[0])))
    envelope = ArtifactEnvelope.create(
        artifact_type="CONTROLLED_CANDIDATE_SET",
        artifact_payload=payload,
        decision_date=decision_time.value.date(),
        decision_time=decision_time,
        created_at=inputs.created_at,
        code_revision=code_revision,
        configuration_id=configuration.configuration_id,
        configuration_hash=configuration.configuration_hash,
        source_manifest_id=inputs.source_manifest.source_manifest_id,
        source_manifest_hash=inputs.source_manifest.content_hash,
        input_artifact_ids=tuple(item[0] for item in ordered),
        input_content_hashes=tuple(item[1] for item in ordered),
        model_id=configuration.model_id,
        model_version=configuration.model_version,
        data_eligibility=DataEligibility.EXPLORATORY,
        evidence_authority=EvidenceAuthority.IMMUTABLE_CONTENT_ADDRESSED_ARTIFACT,
        status="RESEARCH_READY"
        if any(item.selection_status is CandidateSelectionStatus.SELECTED for item in finalized)
        else "RESEARCH_BLOCKED",
        reason_codes=reasons,
        limitations=tuple(
            sorted(
                {
                    *configuration.assumptions,
                    "B0_B1_PREDICTION_RUNS_NOT_USED",
                    "FORMAL_OOS_ALPHA_NOT_ESTABLISHED",
                    "TRADING_AUTHORITY_NOT_GRANTED",
                }
            )
        ),
    )
    return CandidateSet(
        envelope=envelope,
        records=finalized,
        minimum_candidate_population=configuration.minimum_candidate_population,
        reason_codes=reasons,
    )


def publish_controlled_research_artifact(*, root: Path, artifact: ControlledResearchArtifact) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    final = root / str(artifact.artifact_id)
    if final.exists():
        if load_verified_controlled_research_artifact(final).artifact != artifact:
            raise FileExistsError("conflicting Controlled Research Artifact exists")
        return final
    stage = Path(tempfile.mkdtemp(prefix=f".{final.name}.", dir=root))
    installed = False
    try:
        _write_json(stage / "artifact.json", artifact.to_canonical_dict())
        _write_json(
            stage / "manifest.json",
            {
                "schema_version": CONTROLLED_RESEARCH_PACKAGE_SCHEMA,
                "artifact_id": str(artifact.artifact_id),
                "content_hash": artifact.content_hash,
                "required_files": sorted(CONTROLLED_RESEARCH_PACKAGE_FILES),
            },
        )
        _write_json(
            stage / "SHA256SUMS.json",
            {name: _file_hash(stage / name) for name in ("artifact.json", "manifest.json")},
        )
        _load(stage, enforce_directory_identity=False)
        os.replace(stage, final)
        installed = True
        _fsync_directory(root)
        return final
    finally:
        if not installed and stage.exists():
            shutil.rmtree(stage)


def load_verified_controlled_research_artifact(
    path: Path,
) -> VerifiedControlledResearchArtifact:
    return _load(path, enforce_directory_identity=True)


def _load(path: Path, *, enforce_directory_identity: bool) -> VerifiedControlledResearchArtifact:
    root = path.resolve()
    if not root.is_dir() or {item.name for item in root.iterdir()} != set(CONTROLLED_RESEARCH_PACKAGE_FILES):
        raise ValueError("Controlled Research exact file set mismatch")
    checksums = _dict(_read_json(root / "SHA256SUMS.json"), "checksums")
    if set(checksums) != {"artifact.json", "manifest.json"}:
        raise ValueError("Controlled Research checksum coverage mismatch")
    if any(_file_hash(root / name) != digest for name, digest in checksums.items()):
        raise ValueError("Controlled Research checksum mismatch")
    artifact = ControlledResearchArtifact.from_canonical_dict(_dict(_read_json(root / "artifact.json"), "artifact"))
    manifest = _dict(_read_json(root / "manifest.json"), "manifest")
    if manifest != {
        "schema_version": CONTROLLED_RESEARCH_PACKAGE_SCHEMA,
        "artifact_id": str(artifact.artifact_id),
        "content_hash": artifact.content_hash,
        "required_files": sorted(CONTROLLED_RESEARCH_PACKAGE_FILES),
    } or (enforce_directory_identity and root.name != str(artifact.artifact_id)):
        raise ValueError("Controlled Research package identity mismatch")
    return VerifiedControlledResearchArtifact(
        root=root,
        artifact=artifact,
        checksums_hash=_file_hash(root / "SHA256SUMS.json"),
    )


def _validate_static_feature_authority(
    inputs: ControlledOperationalResearchInput,
    bundle: VerifiedFeatureBundleV2,
) -> None:
    static = inputs.static_feature_bundle
    if (
        bundle.artifact.bundle_id != static.feature_bundle_id
        or bundle.artifact.content_hash != static.feature_bundle_hash
        or bundle.artifact.symbols != inputs.operational_universe.symbols
    ):
        raise ValueError("Controlled Research Static Feature authority mismatch")
    allowed = {item.artifact_id for item in static.feature_artifact_references}
    if {item.artifact.artifact_id for item in bundle.artifacts} != allowed:
        raise ValueError("Controlled Research Static Feature reference scope mismatch")


def _decimal_feature(
    bundle: VerifiedFeatureBundleV2,
    symbol: str,
    feature_id: str,
    output_id: str,
):
    artifacts = tuple(
        item.artifact for item in bundle.artifacts if item.artifact.symbol == symbol and item.artifact.feature_id == feature_id
    )
    if len(artifacts) != 1:
        return None, None
    artifact = artifacts[0]
    values = tuple(item for item in artifact.values if item.output_id == output_id)
    if len(values) != 1 or values[0].state is not FeatureValueState.AVAILABLE:
        return artifact, None
    value = values[0].value
    return artifact, float(value) if isinstance(value, Decimal) else None


def _market_score(item: MarketRegimeSnapshot) -> float | None:
    values = tuple(
        value
        for value in (
            item.direction_score,
            item.breadth_score,
            item.liquidity_score,
            item.volatility_score,
            item.limit_structure_score,
        )
        if value is not None
    )
    return sum(values) / len(values) if len(values) == 5 else None


def _clip(value: float) -> float:
    return max(-1.0, min(1.0, value))


def _unit(value: float) -> float:
    return (_clip(value) + 1.0) / 2.0


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.write_text(canonical_json(payload) + "\n", encoding="utf-8")
    with path.open("rb") as handle:
        os.fsync(handle.fileno())


def _read_json(path: Path) -> object:
    raw = path.read_bytes()
    payload = json.loads(raw)
    if raw != (canonical_json(payload) + "\n").encode():
        raise ValueError(f"Controlled Research JSON is not canonical: {path.name}")
    return payload


def _file_hash(path: Path) -> str:
    return f"sha256:{sha256(path.read_bytes()).hexdigest()}"


def _object(value: object, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object")
    return value


def _dict(value: object, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")
    return value


def _strings(value: object, label: str) -> tuple[str, ...]:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ValueError(f"{label} must be a string array")
    return tuple(value)


def _fsync_directory(root: Path) -> None:
    descriptor = os.open(root, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


__all__ = [
    "ControlledPlatformResearchRunner",
    "ControlledResearchArtifact",
    "ResolvedCandidateFeature",
    "VerifiedControlledResearchArtifact",
    "discover_controlled_candidates",
    "discover_controlled_candidates_from_resolved_features",
    "load_verified_controlled_research_artifact",
    "publish_controlled_research_artifact",
]
