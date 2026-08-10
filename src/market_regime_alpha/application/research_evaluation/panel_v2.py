"""Frozen full-universe Research Panel V2 for future ablation work."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Mapping

from market_regime_alpha.application.canonical_lifecycle._immutable_io import (
    publish_immutable_text,
)
from market_regime_alpha.application.continuous_research.journal import (
    RuntimeArtifactReference,
)
from market_regime_alpha.application.research_evaluation.targeted_outcome import (
    TargetedShadowOutcome,
)
from market_regime_alpha.application.research_evaluation.targets import (
    OutcomeTargetProtocol,
)
from market_regime_alpha.application.shadow_research.contracts import ShadowDecision
from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.evidence.canonical import (
    canonical_datetime,
    canonical_hash,
    canonical_json,
    require_sha256,
    require_text,
)
from market_regime_alpha.research.candidate_discovery.contracts import CandidateSet
from market_regime_alpha.research.state_system.pool import DynamicStockPoolVersion


@dataclass(frozen=True, slots=True)
class ResearchFactorValue:
    factor_id: str
    raw_exposure: Decimal | None
    normalized_exposure: Decimal | None
    contribution: Decimal | None

    def __post_init__(self) -> None:
        require_text("factor_id", self.factor_id)

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "factor_id": self.factor_id,
            "raw_exposure": _decimal(self.raw_exposure),
            "normalized_exposure": _decimal(self.normalized_exposure),
            "contribution": _decimal(self.contribution),
        }

    @classmethod
    def from_canonical_dict(cls, value: Mapping[str, Any]) -> ResearchFactorValue:
        return cls(
            factor_id=str(value["factor_id"]),
            raw_exposure=_optional_decimal(value["raw_exposure"]),
            normalized_exposure=_optional_decimal(value["normalized_exposure"]),
            contribution=_optional_decimal(value["contribution"]),
        )


@dataclass(frozen=True, slots=True)
class ResearchPanelRow:
    row_id: ArtifactId
    row_hash: str
    symbol: str
    universe_eligible: bool
    pool_included: bool | None
    pool_gate_result: str | None
    pool_exclusion_reasons: tuple[str, ...]
    candidate_status: str | None
    candidate_rank: int | None
    candidate_score: Decimal | None
    candidate_reason_codes: tuple[str, ...]
    factor_values: tuple[ResearchFactorValue, ...]
    signal_features: tuple[tuple[str, Decimal | None], ...]
    forecast_outputs: tuple[tuple[str, Decimal | None], ...]
    target_labels: tuple[RuntimeArtifactReference, ...]
    reason_codes: tuple[str, ...]

    def __post_init__(self) -> None:
        require_text("symbol", self.symbol)
        require_sha256("row_hash", self.row_hash)
        if not isinstance(self.universe_eligible, bool):
            raise TypeError("universe_eligible must be bool")
        if self.factor_values != tuple(sorted(self.factor_values, key=lambda item: item.factor_id)):
            raise ValueError("Research factors must be unique and sorted")
        if len({item.factor_id for item in self.factor_values}) != len(self.factor_values):
            raise ValueError("Research factors must be unique")
        for named_values in (self.signal_features, self.forecast_outputs):
            if named_values != tuple(sorted(named_values)):
                raise ValueError("Research named values must be unique and sorted")
        if self.target_labels != _references(self.target_labels):
            raise ValueError("Target labels must be unique and sorted")
        for reason_values in (
            self.pool_exclusion_reasons,
            self.candidate_reason_codes,
            self.reason_codes,
        ):
            if reason_values != tuple(sorted(set(reason_values))):
                raise ValueError("Research Panel reasons must be unique and sorted")
        if canonical_hash(self.identity_payload()) != self.row_hash:
            raise ValueError("Research Panel row hash mismatch")
        if str(self.row_id) != f"research-panel-row:{self.row_hash[7:]}":
            raise ValueError("Research Panel row id mismatch")

    @classmethod
    def create(cls, **values: Any) -> ResearchPanelRow:
        normalized = dict(values)
        normalized["factor_values"] = tuple(sorted(values["factor_values"], key=lambda item: item.factor_id))
        normalized["signal_features"] = tuple(sorted(set(values["signal_features"])))
        normalized["forecast_outputs"] = tuple(sorted(set(values["forecast_outputs"])))
        normalized["target_labels"] = _references(values["target_labels"])
        for name in (
            "pool_exclusion_reasons",
            "candidate_reason_codes",
            "reason_codes",
        ):
            normalized[name] = tuple(sorted(set(values[name])))
        digest = canonical_hash(_row_payload(**normalized))
        return cls(
            row_id=ArtifactId(f"research-panel-row:{digest[7:]}"),
            row_hash=digest,
            **normalized,
        )

    def identity_payload(self) -> dict[str, Any]:
        return _row_payload(**{name: getattr(self, name) for name in _row_names()})

    def to_canonical_dict(self) -> dict[str, Any]:
        return {"row_id": str(self.row_id), "row_hash": self.row_hash, **self.identity_payload()}

    @classmethod
    def from_canonical_dict(cls, value: Mapping[str, Any]) -> ResearchPanelRow:
        return cls(
            row_id=ArtifactId(str(value["row_id"])),
            row_hash=str(value["row_hash"]),
            symbol=str(value["symbol"]),
            universe_eligible=_required_bool(value["universe_eligible"]),
            pool_included=_optional_bool(value["pool_included"]),
            pool_gate_result=_optional_text(value["pool_gate_result"]),
            pool_exclusion_reasons=_strings(value["pool_exclusion_reasons"]),
            candidate_status=_optional_text(value["candidate_status"]),
            candidate_rank=None if value["candidate_rank"] is None else int(value["candidate_rank"]),
            candidate_score=_optional_decimal(value["candidate_score"]),
            candidate_reason_codes=_strings(value["candidate_reason_codes"]),
            factor_values=tuple(ResearchFactorValue.from_canonical_dict(item) for item in _objects(value["factor_values"])),
            signal_features=_named_values(value["signal_features"]),
            forecast_outputs=_named_values(value["forecast_outputs"]),
            target_labels=tuple(_reference(item) for item in _objects(value["target_labels"])),
            reason_codes=_strings(value["reason_codes"]),
        )


@dataclass(frozen=True, slots=True)
class ResearchPanelSliceV2:
    slice_id: ArtifactId
    slice_hash: str
    trading_date: date
    run_id: ArtifactId
    tick_id: ArtifactId
    shadow_decision: RuntimeArtifactReference
    summary: RuntimeArtifactReference
    source_manifest: RuntimeArtifactReference
    dataset: RuntimeArtifactReference
    feature_bundle: RuntimeArtifactReference
    market_state: RuntimeArtifactReference
    etf_state: RuntimeArtifactReference
    theme_state: RuntimeArtifactReference
    capital_state: RuntimeArtifactReference
    dynamic_pool: RuntimeArtifactReference | None
    candidate_set: RuntimeArtifactReference | None
    signal: RuntimeArtifactReference | None
    forecast: RuntimeArtifactReference | None
    model_references: tuple[RuntimeArtifactReference, ...]
    configuration_references: tuple[RuntimeArtifactReference, ...]
    state_policy_references: tuple[RuntimeArtifactReference, ...]
    target_protocol: RuntimeArtifactReference
    targeted_outcome: RuntimeArtifactReference
    rows: tuple[ResearchPanelRow, ...]
    reason_codes: tuple[str, ...]

    def __post_init__(self) -> None:
        require_sha256("slice_hash", self.slice_hash)
        if self.rows != tuple(sorted(self.rows, key=lambda item: item.symbol)):
            raise ValueError("Research Panel rows must be symbol-sorted")
        if len({item.symbol for item in self.rows}) != len(self.rows):
            raise ValueError("Research Panel rows must be symbol-unique")
        for refs in (
            self.model_references,
            self.configuration_references,
            self.state_policy_references,
        ):
            if refs != _references(refs):
                raise ValueError("Research Panel lineage must be unique and sorted")
        if self.reason_codes != tuple(sorted(set(self.reason_codes))):
            raise ValueError("Research Panel slice reasons must be unique and sorted")
        if canonical_hash(self.identity_payload()) != self.slice_hash:
            raise ValueError("Research Panel slice hash mismatch")
        if str(self.slice_id) != f"research-panel-slice:{self.slice_hash[7:]}":
            raise ValueError("Research Panel slice id mismatch")

    @classmethod
    def create(cls, **values: Any) -> ResearchPanelSliceV2:
        normalized = dict(values)
        normalized["rows"] = tuple(sorted(values["rows"], key=lambda item: item.symbol))
        for name in (
            "model_references",
            "configuration_references",
            "state_policy_references",
        ):
            normalized[name] = _references(values[name])
        normalized["reason_codes"] = tuple(sorted(set(values["reason_codes"])))
        digest = canonical_hash(_slice_payload(**normalized))
        return cls(
            slice_id=ArtifactId(f"research-panel-slice:{digest[7:]}"),
            slice_hash=digest,
            **normalized,
        )

    def identity_payload(self) -> dict[str, Any]:
        return _slice_payload(**{name: getattr(self, name) for name in _slice_names()})

    def to_canonical_dict(self) -> dict[str, Any]:
        return {"slice_id": str(self.slice_id), "slice_hash": self.slice_hash, **self.identity_payload()}

    @classmethod
    def from_canonical_dict(cls, value: Mapping[str, Any]) -> ResearchPanelSliceV2:
        return cls(
            slice_id=ArtifactId(str(value["slice_id"])),
            slice_hash=str(value["slice_hash"]),
            trading_date=date.fromisoformat(str(value["trading_date"])),
            run_id=ArtifactId(str(value["run_id"])),
            tick_id=ArtifactId(str(value["tick_id"])),
            shadow_decision=_reference(value["shadow_decision"]),
            summary=_reference(value["summary"]),
            source_manifest=_reference(value["source_manifest"]),
            dataset=_reference(value["dataset"]),
            feature_bundle=_reference(value["feature_bundle"]),
            market_state=_reference(value["market_state"]),
            etf_state=_reference(value["etf_state"]),
            theme_state=_reference(value["theme_state"]),
            capital_state=_reference(value["capital_state"]),
            dynamic_pool=_optional_reference(value["dynamic_pool"]),
            candidate_set=_optional_reference(value["candidate_set"]),
            signal=_optional_reference(value["signal"]),
            forecast=_optional_reference(value["forecast"]),
            model_references=tuple(_reference(item) for item in _objects(value["model_references"])),
            configuration_references=tuple(_reference(item) for item in _objects(value["configuration_references"])),
            state_policy_references=tuple(_reference(item) for item in _objects(value["state_policy_references"])),
            target_protocol=_reference(value["target_protocol"]),
            targeted_outcome=_reference(value["targeted_outcome"]),
            rows=tuple(ResearchPanelRow.from_canonical_dict(item) for item in _objects(value["rows"])),
            reason_codes=_strings(value["reason_codes"]),
        )


@dataclass(frozen=True, slots=True)
class FrozenResearchPanelV2:
    panel_id: ArtifactId
    panel_hash: str
    target_protocol_id: ArtifactId
    target_protocol_hash: str
    slices: tuple[ResearchPanelSliceV2, ...]
    created_at: datetime
    limitations: tuple[str, ...]
    schema_version: str = "frozen-research-panel/v2"

    def __post_init__(self) -> None:
        if self.schema_version != "frozen-research-panel/v2":
            raise ValueError("unsupported Research Panel schema")
        require_sha256("panel_hash", self.panel_hash)
        require_sha256("target_protocol_hash", self.target_protocol_hash)
        keys = tuple((item.trading_date, str(item.run_id)) for item in self.slices)
        if not keys or keys != tuple(sorted(set(keys))):
            raise ValueError("Research Panel slices must be unique and sorted")
        required = {
            "EXPLORATORY_ONLY",
            "NOT_FORMAL_OOS",
            "NOT_MODEL_QUALIFICATION",
            "OUTCOME_CANNOT_REWRITE_DECISION",
        }
        if not required.issubset(self.limitations):
            raise ValueError("Research Panel authority ceiling is incomplete")
        if canonical_hash(self.identity_payload()) != self.panel_hash:
            raise ValueError("Research Panel hash mismatch")
        if str(self.panel_id) != f"research-panel-v2:{self.panel_hash[7:]}":
            raise ValueError("Research Panel id mismatch")

    @classmethod
    def create(
        cls,
        *,
        target_protocol: OutcomeTargetProtocol,
        slices: tuple[ResearchPanelSliceV2, ...],
        created_at: datetime,
    ) -> FrozenResearchPanelV2:
        ordered = tuple(sorted(slices, key=lambda item: (item.trading_date, str(item.run_id))))
        limitations = (
            "EXPLORATORY_ONLY",
            "NOT_FORMAL_OOS",
            "NOT_MODEL_QUALIFICATION",
            "OUTCOME_CANNOT_REWRITE_DECISION",
        )
        values = {
            "target_protocol_id": target_protocol.protocol_id,
            "target_protocol_hash": target_protocol.protocol_hash,
            "slices": ordered,
            "created_at": created_at,
            "limitations": limitations,
        }
        digest = canonical_hash(_panel_payload(**values))
        return cls(
            panel_id=ArtifactId(f"research-panel-v2:{digest[7:]}"),
            panel_hash=digest,
            target_protocol_id=target_protocol.protocol_id,
            target_protocol_hash=target_protocol.protocol_hash,
            slices=ordered,
            created_at=created_at,
            limitations=limitations,
        )

    @property
    def row_count(self) -> int:
        return sum(len(item.rows) for item in self.slices)

    def identity_payload(self) -> dict[str, Any]:
        return _panel_payload(
            target_protocol_id=self.target_protocol_id,
            target_protocol_hash=self.target_protocol_hash,
            slices=self.slices,
            created_at=self.created_at,
            limitations=self.limitations,
        )

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "panel_id": str(self.panel_id),
            "panel_hash": self.panel_hash,
            **self.identity_payload(),
            "row_count": self.row_count,
        }

    @classmethod
    def from_canonical_dict(cls, value: Mapping[str, Any]) -> FrozenResearchPanelV2:
        panel = cls(
            panel_id=ArtifactId(str(value["panel_id"])),
            panel_hash=str(value["panel_hash"]),
            target_protocol_id=ArtifactId(str(value["target_protocol_id"])),
            target_protocol_hash=str(value["target_protocol_hash"]),
            slices=tuple(ResearchPanelSliceV2.from_canonical_dict(item) for item in _objects(value["slices"])),
            created_at=_instant(value["created_at"]),
            limitations=_strings(value["limitations"]),
            schema_version=str(value["schema_version"]),
        )
        if value.get("row_count") != panel.row_count:
            raise ValueError("Research Panel row count mismatch")
        return panel


def build_research_panel_slice_v2(
    *,
    decision: ShadowDecision,
    dynamic_pool: DynamicStockPoolVersion,
    candidate_set: CandidateSet,
    targeted_outcome: TargetedShadowOutcome,
    target_protocol: OutcomeTargetProtocol,
    state_policy_references: tuple[RuntimeArtifactReference, ...],
    factor_details: Mapping[str, tuple[ResearchFactorValue, ...]] | None = None,
    signal_features: Mapping[str, tuple[tuple[str, Decimal | None], ...]] | None = None,
    forecast_outputs: Mapping[str, tuple[tuple[str, Decimal | None], ...]] | None = None,
) -> ResearchPanelSliceV2:
    if decision.dynamic_pool is None or (
        decision.dynamic_pool.artifact_id != dynamic_pool.pool_id or decision.dynamic_pool.content_hash != dynamic_pool.pool_hash
    ):
        raise ValueError("Research Panel Dynamic Pool lineage mismatch")
    if decision.candidate_set is None or (
        decision.candidate_set.artifact_id != candidate_set.envelope.artifact_id
        or decision.candidate_set.content_hash != candidate_set.envelope.content_hash
    ):
        raise ValueError("Research Panel Candidate lineage mismatch")
    if (
        targeted_outcome.shadow_decision.artifact_id != decision.decision_id
        or targeted_outcome.target_protocol_id != target_protocol.protocol_id
        or targeted_outcome.target_protocol_hash != target_protocol.protocol_hash
    ):
        raise ValueError("Research Panel Target/Decision lineage mismatch")
    normalized_state_policy_references = _references(state_policy_references)
    if normalized_state_policy_references != decision.state_policy_references:
        raise ValueError("Research Panel State Policy lineage mismatch")
    pools = {item.symbol: item for item in dynamic_pool.members}
    candidates = {item.symbol: item for item in candidate_set.records}
    labels: dict[str, list[RuntimeArtifactReference]] = {}
    for item in targeted_outcome.labels:
        labels.setdefault(item.symbol, []).append(RuntimeArtifactReference("TARGET_OUTCOME_LABEL", item.label_id, item.label_hash))
    symbols = tuple(sorted(set(pools) | set(candidates)))
    if not symbols:
        raise ValueError("Research Panel requires an evaluated universe")
    rows = []
    for symbol in symbols:
        pool = pools.get(symbol)
        candidate = candidates.get(symbol)
        defaults = () if candidate is None else _candidate_factors(candidate)
        row_reasons = {"FULL_EVALUATED_UNIVERSE_ROW"}
        if pool is None:
            row_reasons.add("POOL_RECORD_MISSING")
        if candidate is None:
            row_reasons.add("CANDIDATE_RECORD_MISSING")
        rows.append(
            ResearchPanelRow.create(
                symbol=symbol,
                universe_eligible=False if pool is None else pool.eligibility,
                pool_included=None if pool is None else pool.included,
                pool_gate_result=None if pool is None else pool.gate_result,
                pool_exclusion_reasons=() if pool is None else pool.exclusion_reasons,
                candidate_status=None if candidate is None else candidate.selection_status.value,
                candidate_rank=None if candidate is None else candidate.rank,
                candidate_score=(
                    None
                    if candidate is None or candidate.candidate_discovery_score is None
                    else Decimal(str(candidate.candidate_discovery_score))
                ),
                candidate_reason_codes=() if candidate is None else candidate.reason_codes,
                factor_values=(factor_details or {}).get(symbol, defaults),
                signal_features=(signal_features or {}).get(symbol, ()),
                forecast_outputs=(forecast_outputs or {}).get(symbol, ()),
                target_labels=tuple(labels.get(symbol, ())),
                reason_codes=tuple(sorted(row_reasons)),
            )
        )
    return ResearchPanelSliceV2.create(
        trading_date=decision.trading_date,
        run_id=decision.run_id,
        tick_id=decision.tick_id,
        shadow_decision=RuntimeArtifactReference("SHADOW_DECISION", decision.decision_id, decision.decision_hash),
        summary=decision.summary,
        source_manifest=decision.source_manifest,
        dataset=decision.dataset,
        feature_bundle=decision.feature_bundle,
        market_state=decision.market_state,
        etf_state=decision.etf_state,
        theme_state=decision.theme_state,
        capital_state=decision.capital_state,
        dynamic_pool=decision.dynamic_pool,
        candidate_set=decision.candidate_set,
        signal=decision.signal,
        forecast=decision.forecast,
        model_references=decision.model_selection_receipts,
        configuration_references=decision.configuration_references,
        state_policy_references=normalized_state_policy_references,
        target_protocol=RuntimeArtifactReference("OUTCOME_TARGET_PROTOCOL", target_protocol.protocol_id, target_protocol.protocol_hash),
        targeted_outcome=RuntimeArtifactReference(
            "TARGETED_SHADOW_OUTCOME", targeted_outcome.settlement_id, targeted_outcome.settlement_hash
        ),
        rows=tuple(rows),
        reason_codes=("FROZEN_FULL_RESEARCH_PANEL", "TARGET_PROTOCOL_BOUND"),
    )


def publish_research_panel_v2(*, root: Path, panel: FrozenResearchPanelV2) -> Path:
    path = root / f"{panel.panel_id}.json"
    publish_immutable_text(
        path=path,
        payload=canonical_json(panel.to_canonical_dict()) + "\n",
        collision_message="Research Panel V2 identity conflict",
    )
    if load_research_panel_v2(path) != panel:
        raise ValueError("published Research Panel V2 semantic mismatch")
    return path


def load_research_panel_v2(path: Path) -> FrozenResearchPanelV2:
    import json

    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("Research Panel V2 payload must be an object")
    return FrozenResearchPanelV2.from_canonical_dict(value)


def _candidate_factors(candidate: Any) -> tuple[ResearchFactorValue, ...]:
    values = (
        ("capital_evolution", candidate.capital_evolution_score),
        ("candidate_discovery", candidate.candidate_discovery_score),
        ("market_regime", candidate.market_regime_score),
        ("theme_rotation", candidate.theme_score),
    )
    return tuple(
        ResearchFactorValue(
            factor_id=name,
            raw_exposure=None if value is None else Decimal(str(value)),
            normalized_exposure=None,
            contribution=None,
        )
        for name, value in values
    )


def _row_names() -> tuple[str, ...]:
    return (
        "symbol",
        "universe_eligible",
        "pool_included",
        "pool_gate_result",
        "pool_exclusion_reasons",
        "candidate_status",
        "candidate_rank",
        "candidate_score",
        "candidate_reason_codes",
        "factor_values",
        "signal_features",
        "forecast_outputs",
        "target_labels",
        "reason_codes",
    )


def _row_payload(**v: Any) -> dict[str, Any]:
    return {
        "schema": "research_panel_row/v2",
        "symbol": v["symbol"],
        "universe_eligible": v["universe_eligible"],
        "pool_included": v["pool_included"],
        "pool_gate_result": v["pool_gate_result"],
        "pool_exclusion_reasons": list(v["pool_exclusion_reasons"]),
        "candidate_status": v["candidate_status"],
        "candidate_rank": v["candidate_rank"],
        "candidate_score": _decimal(v["candidate_score"]),
        "candidate_reason_codes": list(v["candidate_reason_codes"]),
        "factor_values": [item.to_canonical_dict() for item in v["factor_values"]],
        "signal_features": _named_payload(v["signal_features"]),
        "forecast_outputs": _named_payload(v["forecast_outputs"]),
        "target_labels": [item.to_canonical_dict() for item in v["target_labels"]],
        "reason_codes": list(v["reason_codes"]),
    }


def _slice_names() -> tuple[str, ...]:
    return (
        "trading_date",
        "run_id",
        "tick_id",
        "shadow_decision",
        "summary",
        "source_manifest",
        "dataset",
        "feature_bundle",
        "market_state",
        "etf_state",
        "theme_state",
        "capital_state",
        "dynamic_pool",
        "candidate_set",
        "signal",
        "forecast",
        "model_references",
        "configuration_references",
        "state_policy_references",
        "target_protocol",
        "targeted_outcome",
        "rows",
        "reason_codes",
    )


def _slice_payload(**v: Any) -> dict[str, Any]:
    return {
        "schema": "research_panel_slice/v2",
        "trading_date": v["trading_date"].isoformat(),
        "run_id": str(v["run_id"]),
        "tick_id": str(v["tick_id"]),
        **{
            name: _optional_reference_dict(v[name])
            for name in (
                "shadow_decision",
                "summary",
                "source_manifest",
                "dataset",
                "feature_bundle",
                "market_state",
                "etf_state",
                "theme_state",
                "capital_state",
                "dynamic_pool",
                "candidate_set",
                "signal",
                "forecast",
                "target_protocol",
                "targeted_outcome",
            )
        },
        "model_references": [item.to_canonical_dict() for item in v["model_references"]],
        "configuration_references": [item.to_canonical_dict() for item in v["configuration_references"]],
        "state_policy_references": [item.to_canonical_dict() for item in v["state_policy_references"]],
        "rows": [item.to_canonical_dict() for item in v["rows"]],
        "reason_codes": list(v["reason_codes"]),
    }


def _panel_payload(**v: Any) -> dict[str, Any]:
    return {
        "schema_version": "frozen-research-panel/v2",
        "target_protocol_id": str(v["target_protocol_id"]),
        "target_protocol_hash": v["target_protocol_hash"],
        "slices": [item.to_canonical_dict() for item in v["slices"]],
        "created_at": canonical_datetime(v["created_at"]),
        "limitations": list(v["limitations"]),
    }


def _references(values: tuple[RuntimeArtifactReference, ...]) -> tuple[RuntimeArtifactReference, ...]:
    return tuple(sorted(set(values), key=lambda item: (item.reference_kind, str(item.artifact_id), item.content_hash)))


def _reference(value: object) -> RuntimeArtifactReference:
    if not isinstance(value, Mapping):
        raise ValueError("reference must be an object")
    return RuntimeArtifactReference(str(value["reference_kind"]), ArtifactId(str(value["artifact_id"])), str(value["content_hash"]))


def _optional_reference(value: object) -> RuntimeArtifactReference | None:
    return None if value is None else _reference(value)


def _optional_reference_dict(value: RuntimeArtifactReference | None) -> dict[str, Any] | None:
    return None if value is None else value.to_canonical_dict()


def _objects(value: object) -> tuple[Mapping[str, Any], ...]:
    if not isinstance(value, list) or any(not isinstance(item, Mapping) for item in value):
        raise ValueError("expected object array")
    return tuple(value)


def _strings(value: object) -> tuple[str, ...]:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ValueError("expected string array")
    return tuple(value)


def _named_payload(values: tuple[tuple[str, Decimal | None], ...]) -> list[dict[str, Any]]:
    return [{"name": name, "value": _decimal(value)} for name, value in values]


def _named_values(value: object) -> tuple[tuple[str, Decimal | None], ...]:
    return tuple((str(item["name"]), _optional_decimal(item["value"])) for item in _objects(value))


def _decimal(value: Decimal | None) -> str | None:
    return None if value is None else str(value)


def _optional_decimal(value: object) -> Decimal | None:
    return None if value is None else Decimal(str(value))


def _optional_bool(value: object) -> bool | None:
    if value is None:
        return None
    if not isinstance(value, bool):
        raise ValueError("expected optional boolean")
    return value


def _required_bool(value: object) -> bool:
    if not isinstance(value, bool):
        raise ValueError("expected boolean")
    return value


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("expected optional text")
    return value


def _instant(value: object) -> datetime:
    if not isinstance(value, str):
        raise ValueError("expected timestamp")
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


__all__ = [
    "FrozenResearchPanelV2",
    "ResearchFactorValue",
    "ResearchPanelRow",
    "ResearchPanelSliceV2",
    "build_research_panel_slice_v2",
    "load_research_panel_v2",
    "publish_research_panel_v2",
]
