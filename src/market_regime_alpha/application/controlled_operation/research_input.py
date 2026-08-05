"""Operational research input bound to Universe and Static Feature authority."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Mapping

from market_regime_alpha.application.operational_research.contracts import (
    CapitalObservationEvidence,
    SupplementalResearchEvidenceBundle,
    ThemeObservationEvidence,
)
from market_regime_alpha.application.operational_research.supplemental_artifact import (
    VerifiedSupplementalResearchEvidence,
)
from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.data.contracts import DataEligibility
from market_regime_alpha.data.source_manifest import SourceManifest
from market_regime_alpha.evidence.canonical import canonical_hash, require_sha256
from market_regime_alpha.features.operational_overlay import StaticUniverseFeatureBundle
from market_regime_alpha.research.platform_v2.inputs import (
    ETFObservation,
    MarketObservation,
    ResearchDailyBar,
    ResearchEvidenceKind,
    SymbolResearchObservation,
    ThemeMembership,
    ThemeResearchObservation,
)
from market_regime_alpha.universe.operational import OperationalUniverseArtifact


CONTROLLED_RESEARCH_INPUT_SCHEMA = "controlled-operational-research-input-v1"


@dataclass(frozen=True, slots=True)
class ControlledOperationalResearchInput:
    schema_version: str
    input_bundle_id: ArtifactId
    content_hash: str
    operational_universe: OperationalUniverseArtifact
    static_feature_bundle: StaticUniverseFeatureBundle
    supplemental_evidence: SupplementalResearchEvidenceBundle
    input_artifact_ids: tuple[ArtifactId, ...]
    input_content_hashes: tuple[str, ...]
    limitations: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.schema_version != CONTROLLED_RESEARCH_INPUT_SCHEMA:
            raise ValueError("unsupported Controlled Research input schema")
        require_sha256("content_hash", self.content_hash)
        self._validate_bindings()
        if len(self.input_artifact_ids) != len(self.input_content_hashes):
            raise ValueError("Controlled Research input lineage must align")
        if self.input_artifact_ids != tuple(sorted(set(self.input_artifact_ids), key=str)):
            raise ValueError("Controlled Research input identities must be unique and sorted")
        for digest in self.input_content_hashes:
            require_sha256("input content hash", digest)
        if not self.limitations or self.limitations != tuple(sorted(set(self.limitations))):
            raise ValueError("Controlled Research limitations must be non-empty and sorted")
        for required in (
            "B0_B1_PREDICTION_RUNS_NOT_USED",
            "FORMAL_PIT_NOT_ESTABLISHED",
            "TRADING_AUTHORITY_NOT_GRANTED",
        ):
            if required not in self.limitations:
                raise ValueError("Controlled Research authority ceiling is incomplete")
        self.verify_identity()

    @classmethod
    def create(
        cls,
        *,
        operational_universe: OperationalUniverseArtifact,
        static_feature_bundle: StaticUniverseFeatureBundle,
        supplemental_evidence: VerifiedSupplementalResearchEvidence,
    ) -> ControlledOperationalResearchInput:
        bundle = supplemental_evidence.bundle
        operational_universe.verify_identity()
        static_feature_bundle.verify_identity()
        if bundle.missing_evidence:
            raise ValueError("Controlled Research supplemental evidence is incomplete")
        lineage: dict[ArtifactId, str] = {
            ArtifactId(str(operational_universe.universe_id)): operational_universe.content_hash,
            static_feature_bundle.artifact_id: static_feature_bundle.content_hash,
            bundle.bundle_id: bundle.content_hash,
            bundle.source_manifest.source_manifest_id: bundle.source_manifest.content_hash,
        }
        for source in bundle.source_manifest.source_artifacts:
            existing = lineage.get(source.artifact_id)
            if existing is not None and existing != source.content_hash:
                raise ValueError("Controlled Research source identity hash conflict")
            lineage[source.artifact_id] = source.content_hash
        ordered = tuple(sorted(lineage.items(), key=lambda item: str(item[0])))
        limitations = tuple(
            sorted(
                {
                    *operational_universe.limitations,
                    *static_feature_bundle.limitations,
                    *bundle.reason_codes,
                    "B0_B1_PREDICTION_RUNS_NOT_USED",
                    "CONTROLLED_CANDIDATE_DISCOVERY_V1",
                    "FORMAL_OOS_ALPHA_NOT_ESTABLISHED",
                    "FORMAL_PIT_NOT_ESTABLISHED",
                    "TRADING_AUTHORITY_NOT_GRANTED",
                }
            )
        )
        values = {
            "operational_universe": operational_universe,
            "static_feature_bundle": static_feature_bundle,
            "supplemental_evidence": bundle,
            "input_artifact_ids": tuple(item[0] for item in ordered),
            "input_content_hashes": tuple(item[1] for item in ordered),
            "limitations": limitations,
        }
        digest = canonical_hash(_payload(**values))
        return cls(
            schema_version=CONTROLLED_RESEARCH_INPUT_SCHEMA,
            input_bundle_id=ArtifactId(f"controlled-research-input-{digest.split(':', 1)[1][:24]}"),
            content_hash=digest,
            **values,
        )

    @property
    def evidence_kind(self) -> ResearchEvidenceKind:
        return ResearchEvidenceKind.OPERATIONAL_EXPLORATORY_ARCHIVE

    @property
    def source_manifest(self) -> SourceManifest:
        return self.supplemental_evidence.source_manifest

    @property
    def market_observation(self) -> MarketObservation:
        return self.supplemental_evidence.market_observation

    @property
    def theme_observations(self) -> tuple[ThemeResearchObservation, ...]:
        capital = {
            item.theme_id: item for item in self.supplemental_evidence.capital_observations
        }
        return tuple(
            _combine_theme_and_capital(item, capital[item.theme_id])
            for item in self.supplemental_evidence.theme_observations
        )

    @property
    def symbol_observations(self) -> tuple[SymbolResearchObservation, ...]:
        return self.supplemental_evidence.symbol_observations

    @property
    def theme_memberships(self) -> tuple[ThemeMembership, ...]:
        return tuple(
            ThemeMembership(
                symbol=item.symbol,
                primary_theme_id=item.primary_theme_id,
                supporting_theme_ids=item.supporting_theme_ids,
            )
            for item in self.supplemental_evidence.theme_memberships
        )

    @property
    def etf_observations(self) -> tuple[ETFObservation, ...]:
        return self.supplemental_evidence.etf_observations

    @property
    def stock_daily_bars(self) -> tuple[ResearchDailyBar, ...]:
        return self.supplemental_evidence.stock_daily_bars

    @property
    def created_at(self) -> datetime:
        return self.supplemental_evidence.created_at

    @property
    def data_eligibility(self) -> DataEligibility:
        return DataEligibility.EXPLORATORY

    def _validate_bindings(self) -> None:
        universe = self.operational_universe
        static = self.static_feature_bundle
        supplemental = self.supplemental_evidence
        if (
            static.universe_id != universe.universe_id
            or static.universe_hash != universe.content_hash
            or static.symbols != universe.symbols
        ):
            raise ValueError("Controlled Research Static Bundle and Universe mismatch")
        decision = supplemental.decision_time.value
        if (
            universe.decision_date != decision.date()
            or static.decision_date != decision.date()
            or universe.available_at > decision
            or static.static_decision_time > decision
        ):
            raise ValueError("Controlled Research DecisionTime binding mismatch")
        symbols = set(universe.symbols)
        if (
            {item.symbol for item in supplemental.symbol_observations} != symbols
            or {item.symbol for item in supplemental.theme_memberships} != symbols
        ):
            raise ValueError("Controlled Research evidence does not cover Operational Universe")
        themes = {item.theme_id for item in supplemental.theme_observations}
        capital = {item.theme_id for item in supplemental.capital_observations}
        if not themes or themes != capital:
            raise ValueError("Controlled Research Theme/Capital scope mismatch")
        if supplemental.data_eligibility is not DataEligibility.EXPLORATORY:
            raise ValueError("Controlled Research cannot increase DataEligibility")

    def semantic_payload(self) -> dict[str, Any]:
        return _payload(**_values(self))

    def verify_identity(self) -> None:
        digest = canonical_hash(self.semantic_payload())
        if digest != self.content_hash:
            raise ValueError("Controlled Research input hash mismatch")
        expected = f"controlled-research-input-{digest.split(':', 1)[1][:24]}"
        if str(self.input_bundle_id) != expected:
            raise ValueError("Controlled Research input identity mismatch")

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "input_bundle_id": str(self.input_bundle_id),
            "content_hash": self.content_hash,
            **self.semantic_payload(),
        }

    @classmethod
    def from_canonical_dict(
        cls, payload: Mapping[str, Any]
    ) -> ControlledOperationalResearchInput:
        expected = {
            "schema_version", "input_bundle_id", "content_hash",
            "operational_universe", "static_feature_bundle", "supplemental_evidence",
            "input_artifact_ids", "input_content_hashes", "limitations",
        }
        if set(payload) != expected:
            raise ValueError("Controlled Research input fields mismatch")
        return cls(
            schema_version=str(payload["schema_version"]),
            input_bundle_id=ArtifactId(str(payload["input_bundle_id"])),
            content_hash=str(payload["content_hash"]),
            operational_universe=OperationalUniverseArtifact.from_canonical_dict(
                _object(payload["operational_universe"], "operational universe")
            ),
            static_feature_bundle=StaticUniverseFeatureBundle.from_canonical_dict(
                _object(payload["static_feature_bundle"], "static Feature Bundle")
            ),
            supplemental_evidence=SupplementalResearchEvidenceBundle.from_canonical_dict(
                _object(payload["supplemental_evidence"], "supplemental evidence")
            ),
            input_artifact_ids=tuple(
                ArtifactId(item) for item in _strings(payload["input_artifact_ids"], "input ids")
            ),
            input_content_hashes=_strings(payload["input_content_hashes"], "input hashes"),
            limitations=_strings(payload["limitations"], "limitations"),
        )


def _combine_theme_and_capital(
    theme: ThemeObservationEvidence,
    capital: CapitalObservationEvidence,
) -> ThemeResearchObservation:
    if theme.theme_id != capital.theme_id:
        raise ValueError("Theme and Capital observation identity mismatch")
    return ThemeResearchObservation(
        theme_id=theme.theme_id,
        theme_name=theme.theme_name,
        benchmark_id=theme.benchmark_id,
        proxy_etf_ids=theme.proxy_etf_ids,
        available_at=(
            theme.available_at
            if theme.available_at.value >= capital.available_at.value
            else capital.available_at
        ),
        source_artifact_id=capital.source_artifact_id,
        relative_strength_1d=theme.relative_strength_1d,
        relative_strength_3d=theme.relative_strength_3d,
        relative_strength_5d=theme.relative_strength_5d,
        relative_strength_10d=theme.relative_strength_10d,
        amount_expansion=theme.amount_expansion,
        etf_amount_expansion=capital.etf_amount_expansion,
        breadth=theme.breadth,
        new_high_breadth=theme.new_high_breadth,
        leader_strength=theme.leader_strength,
        participation_change=theme.participation_change,
        rank_persistence=theme.rank_persistence,
        amount_persistence=capital.amount_persistence,
        capital_concentration=capital.capital_concentration,
        diffusion_score=capital.diffusion_score,
        confidence=theme.confidence,
        reason_codes=tuple(dict.fromkeys((*theme.reason_codes, *capital.reason_codes))),
    )


def _values(item: ControlledOperationalResearchInput) -> dict[str, Any]:
    return {
        "operational_universe": item.operational_universe,
        "static_feature_bundle": item.static_feature_bundle,
        "supplemental_evidence": item.supplemental_evidence,
        "input_artifact_ids": item.input_artifact_ids,
        "input_content_hashes": item.input_content_hashes,
        "limitations": item.limitations,
    }


def _payload(**values: Any) -> dict[str, Any]:
    return {
        "schema_version": CONTROLLED_RESEARCH_INPUT_SCHEMA,
        "operational_universe": values["operational_universe"].to_canonical_dict(),
        "static_feature_bundle": values["static_feature_bundle"].to_canonical_dict(),
        "supplemental_evidence": values["supplemental_evidence"].to_canonical_dict(),
        "input_artifact_ids": [str(item) for item in values["input_artifact_ids"]],
        "input_content_hashes": list(values["input_content_hashes"]),
        "limitations": list(values["limitations"]),
    }


def _strings(value: object, label: str) -> tuple[str, ...]:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ValueError(f"{label} must be a string array")
    return tuple(value)


def _object(value: object, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object")
    return value


__all__ = ["ControlledOperationalResearchInput"]
