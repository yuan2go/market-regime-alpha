"""Canonical multi-strategy identities and runtime business objects."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any, Mapping

from market_regime_alpha.application.continuous_research.journal import (
    RuntimeArtifactReference,
)
from market_regime_alpha.core.identity import ArtifactId, StrategyId
from market_regime_alpha.evidence.canonical import (
    canonical_datetime,
    canonical_hash,
    require_sha256,
    require_text,
)
from market_regime_alpha.market_data import CanonicalMarketBar, Timeframe
from market_regime_alpha.market_data.adjustment import PriceAdjustmentPolicy
from market_regime_alpha.market_data.dataset import (
    MarketDataDatasetArtifact,
    MarketDataPartition,
)
from market_regime_alpha.platform.runtime_governance import RuntimeAuthorityMode
from market_regime_alpha.research.candidate_discovery.contracts import CandidateSet


class StrategyFamily(str, Enum):
    OVERNIGHT = "OVERNIGHT"
    SWING_STATE = "SWING_STATE"
    CONDITIONAL_PREDICTION = "CONDITIONAL_PREDICTION"


class StrategyForecastRequirement(str, Enum):
    FORECAST_REQUIRED = "FORECAST_REQUIRED"
    FORECAST_NOT_REQUIRED = "FORECAST_NOT_REQUIRED"


class CanonicalStrategyAction(str, Enum):
    NO_ACTION = "NO_ACTION"
    ENTER = "ENTER"
    HOLD = "HOLD"
    ADD = "ADD"
    REDUCE = "REDUCE"
    ROTATE = "ROTATE"
    EXIT = "EXIT"


class PriceFreshnessStatus(str, Enum):
    FRESH = "FRESH"
    STALE = "STALE"
    NOT_ESTIMABLE = "NOT_ESTIMABLE"


class PortfolioWeightingMethod(str, Enum):
    EQUAL = "EQUAL"
    SCORE = "SCORE"


class StrategyRunOrigin(str, Enum):
    CONTINUOUS = "CONTINUOUS"
    HISTORICAL = "HISTORICAL"
    REPLAY = "REPLAY"


class StrategyRunStatus(str, Enum):
    COMPLETED = "COMPLETED"
    DATA_INSUFFICIENT = "DATA_INSUFFICIENT"


class StrategyEligibilityStatus(str, Enum):
    ELIGIBLE = "ELIGIBLE"
    INELIGIBLE = "INELIGIBLE"
    NOT_ESTIMABLE = "NOT_ESTIMABLE"


@dataclass(frozen=True, slots=True)
class StrategyContract:
    contract_id: ArtifactId
    contract_hash: str
    strategy_id: StrategyId
    family: StrategyFamily
    semantic_version: str
    objective: str
    universe_reference: RuntimeArtifactReference
    target_references: tuple[RuntimeArtifactReference, ...]
    decision_times: tuple[str, ...]
    horizon_sessions: tuple[int, ...]
    candidate_policy_version: str
    action_policy_version: str
    portfolio_weighting: PortfolioWeightingMethod
    top_k: int
    strategy_budget: Decimal
    cost_model_reference: RuntimeArtifactReference
    evaluation_protocol_reference: RuntimeArtifactReference
    code_reference: RuntimeArtifactReference
    configuration_reference: RuntimeArtifactReference
    parameters: tuple[tuple[str, str], ...]
    limitations: tuple[str, ...]
    forecast_requirement: StrategyForecastRequirement = (
        StrategyForecastRequirement.FORECAST_NOT_REQUIRED
    )
    schema_version: str = "strategy-contract/v2"

    def __post_init__(self) -> None:
        if self.schema_version not in {"strategy-contract/v1", "strategy-contract/v2"}:
            raise ValueError("unsupported Strategy Contract schema")
        if (
            self.schema_version == "strategy-contract/v1"
            and self.forecast_requirement
            is not StrategyForecastRequirement.FORECAST_NOT_REQUIRED
        ):
            raise ValueError("legacy Strategy Contract cannot require Forecast")
        if (
            self.family is StrategyFamily.CONDITIONAL_PREDICTION
            and self.forecast_requirement
            is not StrategyForecastRequirement.FORECAST_REQUIRED
        ):
            raise ValueError("Conditional Prediction Strategy requires Forecast")
        if (
            self.family is not StrategyFamily.CONDITIONAL_PREDICTION
            and self.forecast_requirement
            is not StrategyForecastRequirement.FORECAST_NOT_REQUIRED
        ):
            raise ValueError(
                "non-conditional Strategy must declare FORECAST_NOT_REQUIRED"
            )
        require_sha256("contract_hash", self.contract_hash)
        for label, value in (
            ("semantic_version", self.semantic_version),
            ("objective", self.objective),
            ("candidate_policy_version", self.candidate_policy_version),
            ("action_policy_version", self.action_policy_version),
        ):
            require_text(label, value)
        _require_references("target", self.target_references)
        if not self.decision_times or self.decision_times != tuple(sorted(set(self.decision_times))):
            raise ValueError("Strategy decision times must be non-empty, unique, and sorted")
        if (
            not self.horizon_sessions
            or self.horizon_sessions != tuple(sorted(set(self.horizon_sessions)))
            or any(value <= 0 for value in self.horizon_sessions)
        ):
            raise ValueError("Strategy horizons must be positive, unique, and sorted")
        if self.top_k <= 0:
            raise ValueError("Strategy Top-K must be positive")
        if not Decimal("0") < self.strategy_budget <= Decimal("1"):
            raise ValueError("Strategy budget must be within (0, 1]")
        _require_pairs("Strategy parameter", self.parameters)
        _require_text_set("Strategy limitation", self.limitations)
        digest = canonical_hash(self.identity_payload())
        if digest != self.contract_hash:
            raise ValueError("Strategy Contract hash mismatch")
        if str(self.contract_id) != f"strategy-contract:{digest[7:]}":
            raise ValueError("Strategy Contract identifier mismatch")

    @classmethod
    def create(cls, **values: Any) -> StrategyContract:
        normalized = dict(values)
        normalized["target_references"] = _references(tuple(values["target_references"]))
        normalized["decision_times"] = tuple(sorted(set(values["decision_times"])))
        normalized["horizon_sessions"] = tuple(sorted(set(values["horizon_sessions"])))
        normalized["parameters"] = tuple(sorted(set(values["parameters"])))
        normalized["limitations"] = tuple(sorted(set(values["limitations"])))
        forecast_requirement_was_explicit = "forecast_requirement" in normalized
        normalized.setdefault(
            "forecast_requirement",
            StrategyForecastRequirement.FORECAST_NOT_REQUIRED,
        )
        # Preserve the content-addressed identities of already registered incumbent
        # contracts.  V2 is selected only by an explicit Forecast declaration.
        normalized.setdefault(
            "schema_version",
            "strategy-contract/v2"
            if forecast_requirement_was_explicit
            else "strategy-contract/v1",
        )
        payload = _contract_payload(**normalized)
        digest = canonical_hash(payload)
        return cls(
            contract_id=ArtifactId(f"strategy-contract:{digest[7:]}"),
            contract_hash=digest,
            **normalized,
        )

    def identity_payload(self) -> dict[str, Any]:
        return _contract_payload(**{name: getattr(self, name) for name in _contract_fields()})

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "contract_id": str(self.contract_id),
            "contract_hash": self.contract_hash,
            **self.identity_payload(),
        }

    @classmethod
    def from_canonical_dict(cls, payload: Mapping[str, Any]) -> StrategyContract:
        return cls(
            contract_id=ArtifactId(str(payload["contract_id"])),
            contract_hash=str(payload["contract_hash"]),
            strategy_id=StrategyId(str(payload["strategy_id"])),
            family=StrategyFamily(str(payload["family"])),
            semantic_version=str(payload["semantic_version"]),
            objective=str(payload["objective"]),
            universe_reference=_reference(payload["universe_reference"]),
            target_references=_references_from(payload["target_references"]),
            decision_times=_strings(payload["decision_times"]),
            horizon_sessions=_integers(payload["horizon_sessions"]),
            candidate_policy_version=str(payload["candidate_policy_version"]),
            action_policy_version=str(payload["action_policy_version"]),
            portfolio_weighting=PortfolioWeightingMethod(str(payload["portfolio_weighting"])),
            top_k=int(payload["top_k"]),
            strategy_budget=Decimal(str(payload["strategy_budget"])),
            cost_model_reference=_reference(payload["cost_model_reference"]),
            evaluation_protocol_reference=_reference(payload["evaluation_protocol_reference"]),
            code_reference=_reference(payload["code_reference"]),
            configuration_reference=_reference(payload["configuration_reference"]),
            parameters=_pairs(payload["parameters"]),
            limitations=_strings(payload["limitations"]),
            forecast_requirement=StrategyForecastRequirement(
                str(
                    payload.get(
                        "forecast_requirement",
                        StrategyForecastRequirement.FORECAST_NOT_REQUIRED.value,
                    )
                )
            ),
            schema_version=str(payload["schema_version"]),
        )


@dataclass(frozen=True, slots=True)
class StrategyVersion:
    version_id: ArtifactId
    version_hash: str
    contract_reference: RuntimeArtifactReference
    family: StrategyFamily
    semantic_version: str
    lifecycle_status: str
    research_status: str
    limitations: tuple[str, ...]
    schema_version: str = "strategy-version/v1"

    def __post_init__(self) -> None:
        if self.schema_version != "strategy-version/v1":
            raise ValueError("unsupported Strategy Version schema")
        require_sha256("version_hash", self.version_hash)
        if self.lifecycle_status not in {"ACTIVE", "SUSPENDED", "RETIRED"}:
            raise ValueError("unsupported Strategy lifecycle status")
        if self.research_status not in {"EXPLORATORY", "QUALIFICATION_BLOCKED"}:
            raise ValueError("unsupported Strategy research status")
        _require_text_set("Strategy Version limitation", self.limitations)
        digest = canonical_hash(self.identity_payload())
        if digest != self.version_hash:
            raise ValueError("Strategy Version hash mismatch")
        if str(self.version_id) != f"strategy-version:{digest[7:]}":
            raise ValueError("Strategy Version identifier mismatch")

    @classmethod
    def activate(cls, contract: StrategyContract) -> StrategyVersion:
        contract_reference = RuntimeArtifactReference("STRATEGY_CONTRACT", contract.contract_id, contract.contract_hash)
        digest = canonical_hash(
            _strategy_version_payload(
                contract_reference=contract_reference,
                family=contract.family,
                semantic_version=contract.semantic_version,
                lifecycle_status="ACTIVE",
                research_status="EXPLORATORY",
                limitations=contract.limitations,
                schema_version="strategy-version/v1",
            )
        )
        return cls(
            version_id=ArtifactId(f"strategy-version:{digest[7:]}"),
            version_hash=digest,
            contract_reference=contract_reference,
            family=contract.family,
            semantic_version=contract.semantic_version,
            lifecycle_status="ACTIVE",
            research_status="EXPLORATORY",
            limitations=contract.limitations,
            schema_version="strategy-version/v1",
        )

    @property
    def production_authorized(self) -> bool:
        return False

    def identity_payload(self) -> dict[str, Any]:
        return _strategy_version_payload(
            contract_reference=self.contract_reference,
            family=self.family,
            semantic_version=self.semantic_version,
            lifecycle_status=self.lifecycle_status,
            research_status=self.research_status,
            limitations=self.limitations,
            schema_version=self.schema_version,
        )

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "version_id": str(self.version_id),
            "version_hash": self.version_hash,
            **self.identity_payload(),
        }

    @classmethod
    def from_canonical_dict(cls, payload: Mapping[str, Any]) -> StrategyVersion:
        return cls(
            version_id=ArtifactId(str(payload["version_id"])),
            version_hash=str(payload["version_hash"]),
            contract_reference=_reference(payload["contract_reference"]),
            family=StrategyFamily(str(payload["family"])),
            semantic_version=str(payload["semantic_version"]),
            lifecycle_status=str(payload["lifecycle_status"]),
            research_status=str(payload["research_status"]),
            limitations=_strings(payload["limitations"]),
            schema_version=str(payload["schema_version"]),
        )


@dataclass(frozen=True, slots=True)
class StrategyRegistry:
    """Validated active Strategy catalog; it owns no scheduling or qualification."""

    contracts: tuple[StrategyContract, ...]
    versions: tuple[StrategyVersion, ...]

    def __post_init__(self) -> None:
        contract_ids = tuple(str(item.contract_id) for item in self.contracts)
        if contract_ids != tuple(sorted(set(contract_ids))) or not contract_ids:
            raise ValueError("Strategy Registry contracts must be non-empty and unique")
        version_ids = tuple(str(item.version_id) for item in self.versions)
        if version_ids != tuple(sorted(set(version_ids))) or not version_ids:
            raise ValueError("Strategy Registry versions must be non-empty and unique")
        contracts_by_id = {str(item.contract_id): item for item in self.contracts}
        active_strategy_ids: list[str] = []
        for version in self.versions:
            contract = contracts_by_id.get(str(version.contract_reference.artifact_id))
            if contract is None or (contract.contract_hash != version.contract_reference.content_hash):
                raise ValueError("Strategy Version references an unknown Strategy Contract")
            if contract.family is not version.family:
                raise ValueError("Strategy Version family differs from its contract")
            if version.lifecycle_status == "ACTIVE":
                active_strategy_ids.append(str(contract.strategy_id))
        if len(active_strategy_ids) != len(set(active_strategy_ids)):
            raise ValueError("Strategy Registry allows one active version per Strategy")

    @classmethod
    def create(
        cls,
        *,
        contracts: tuple[StrategyContract, ...],
        versions: tuple[StrategyVersion, ...],
    ) -> StrategyRegistry:
        return cls(
            contracts=tuple(sorted(contracts, key=lambda item: str(item.contract_id))),
            versions=tuple(sorted(versions, key=lambda item: str(item.version_id))),
        )

    @property
    def active_versions(self) -> tuple[StrategyVersion, ...]:
        return tuple(item for item in self.versions if item.lifecycle_status == "ACTIVE")

    @property
    def active_version_ids(self) -> tuple[ArtifactId, ...]:
        return tuple(item.version_id for item in self.active_versions)

    def contract_for(self, version: StrategyVersion) -> StrategyContract:
        for contract in self.contracts:
            if (
                contract.contract_id == version.contract_reference.artifact_id
                and contract.contract_hash == version.contract_reference.content_hash
            ):
                return contract
        raise KeyError(str(version.version_id))

    def family_for(self, run: StrategyRun) -> StrategyFamily:
        for version in self.versions:
            if (
                version.version_id == run.strategy_version_reference.artifact_id
                and version.version_hash == run.strategy_version_reference.content_hash
            ):
                return version.family
        raise KeyError(str(run.strategy_version_reference.artifact_id))


@dataclass(frozen=True, slots=True)
class StrategyPositionState:
    strategy_version_id: ArtifactId
    symbol: str
    quantity: Decimal
    average_cost: Decimal
    current_price: Decimal | None
    peak_price: Decimal
    sessions_held: int
    add_count: int = 0
    reduce_count: int = 0
    account_id: str | None = None
    strategy_version_hash: str | None = None
    state_reference: RuntimeArtifactReference | None = None
    source_allocation_references: tuple[RuntimeArtifactReference, ...] = ()
    source_fill_references: tuple[RuntimeArtifactReference, ...] = ()
    price_observation_references: tuple[RuntimeArtifactReference, ...] = ()
    available_quantity: Decimal | None = None
    entry_time: datetime | None = None
    price_observed_at: datetime | None = None
    price_freshness: PriceFreshnessStatus | None = None
    trading_calendar_reference: RuntimeArtifactReference | None = None

    def __post_init__(self) -> None:
        require_text("symbol", self.symbol)
        if self.quantity <= 0 or self.average_cost <= 0 or self.peak_price <= 0:
            raise ValueError("Strategy position quantities and prices must be positive")
        if self.current_price is not None and self.current_price <= 0:
            raise ValueError("Strategy current price must be positive")
        if min(self.sessions_held, self.add_count, self.reduce_count) < 0:
            raise ValueError("Strategy position counters cannot be negative")
        execution_state = (
            self.available_quantity,
            self.entry_time,
            self.price_freshness,
            self.trading_calendar_reference,
        )
        if any(value is not None for value in execution_state):
            if any(value is None for value in execution_state):
                raise ValueError(
                    "owner-resolved Strategy execution state must be complete"
                )
            assert self.available_quantity is not None
            assert self.entry_time is not None
            assert self.price_freshness is not None
            if not Decimal("0") <= self.available_quantity <= self.quantity:
                raise ValueError("Strategy available quantity is invalid")
            canonical_datetime(self.entry_time)
            if self.price_freshness is PriceFreshnessStatus.NOT_ESTIMABLE:
                if self.current_price is not None or self.price_observed_at is not None:
                    raise ValueError(
                        "NOT_ESTIMABLE Strategy price cannot carry a current mark"
                    )
            elif self.current_price is None or self.price_observed_at is None:
                raise ValueError("fresh/stale Strategy price requires an observed mark")
            if self.price_observed_at is not None:
                canonical_datetime(self.price_observed_at)
        lineage = (
            self.source_allocation_references,
            self.source_fill_references,
            self.price_observation_references,
        )
        for label, references in zip(
            ("allocation", "Fill", "price observation"),
            lineage,
            strict=True,
        ):
            keys = tuple(
                (item.reference_kind, str(item.artifact_id), item.content_hash)
                for item in references
            )
            if keys != tuple(sorted(set(keys))):
                raise ValueError(f"Strategy position {label} lineage must be sorted and unique")
        has_owner_lineage = any(
            value is not None
            for value in (
                self.account_id,
                self.strategy_version_hash,
                self.state_reference,
            )
        ) or any(lineage)
        if has_owner_lineage:
            if not self.account_id:
                raise ValueError("owner-resolved Strategy position requires account")
            require_sha256("strategy_version_hash", self.strategy_version_hash or "")
            if not self.source_allocation_references or not self.source_fill_references:
                raise ValueError("owner-resolved Strategy position requires Fill lineage")
            if self.state_reference is None:
                raise ValueError("owner-resolved Strategy position requires state reference")
            digest = canonical_hash(self.identity_payload())
            if (
                self.state_reference.reference_kind != "STRATEGY_SHADOW_POSITION_STATE"
                or self.state_reference.content_hash != digest
                or str(self.state_reference.artifact_id)
                != f"strategy-shadow-position-state:{digest[7:]}"
            ):
                raise ValueError("owner-resolved Strategy position identity mismatch")

    @classmethod
    def owner_resolved(cls, **values: Any) -> StrategyPositionState:
        values.pop("state_reference", None)
        values.setdefault("add_count", 0)
        values.setdefault("reduce_count", 0)
        values.setdefault("source_allocation_references", ())
        values.setdefault("source_fill_references", ())
        values.setdefault("price_observation_references", ())
        digest = canonical_hash(_strategy_position_payload(**values))
        return cls(
            **values,
            state_reference=RuntimeArtifactReference(
                "STRATEGY_SHADOW_POSITION_STATE",
                ArtifactId(f"strategy-shadow-position-state:{digest[7:]}"),
                digest,
            ),
        )

    def identity_payload(self) -> dict[str, Any]:
        return _strategy_position_payload(
            strategy_version_id=self.strategy_version_id,
            symbol=self.symbol,
            quantity=self.quantity,
            average_cost=self.average_cost,
            current_price=self.current_price,
            peak_price=self.peak_price,
            sessions_held=self.sessions_held,
            add_count=self.add_count,
            reduce_count=self.reduce_count,
            account_id=self.account_id,
            strategy_version_hash=self.strategy_version_hash,
            source_allocation_references=self.source_allocation_references,
            source_fill_references=self.source_fill_references,
            price_observation_references=self.price_observation_references,
            available_quantity=self.available_quantity,
            entry_time=self.entry_time,
            price_observed_at=self.price_observed_at,
            price_freshness=self.price_freshness,
            trading_calendar_reference=self.trading_calendar_reference,
        )

    def to_canonical_dict(self) -> dict[str, Any]:
        payload = self.identity_payload()
        if self.state_reference is not None:
            payload["state_reference"] = self.state_reference.to_canonical_dict()
        return payload

    @classmethod
    def from_canonical_dict(cls, payload: Mapping[str, Any]) -> StrategyPositionState:
        current_price = payload["current_price"]
        state_reference = payload.get("state_reference")
        return cls(
            strategy_version_id=ArtifactId(str(payload["strategy_version_id"])),
            symbol=str(payload["symbol"]),
            quantity=Decimal(str(payload["quantity"])),
            average_cost=Decimal(str(payload["average_cost"])),
            current_price=(None if current_price is None else Decimal(str(current_price))),
            peak_price=Decimal(str(payload["peak_price"])),
            sessions_held=int(payload["sessions_held"]),
            add_count=int(payload["add_count"]),
            reduce_count=int(payload["reduce_count"]),
            account_id=(None if payload.get("account_id") is None else str(payload["account_id"])),
            strategy_version_hash=(
                None
                if payload.get("strategy_version_hash") is None
                else str(payload["strategy_version_hash"])
            ),
            state_reference=(None if state_reference is None else _reference(state_reference)),
            source_allocation_references=tuple(
                _reference(item)
                for item in _sequence(payload.get("source_allocation_references", []))
            ),
            source_fill_references=tuple(
                _reference(item)
                for item in _sequence(payload.get("source_fill_references", []))
            ),
            price_observation_references=tuple(
                _reference(item)
                for item in _sequence(payload.get("price_observation_references", []))
            ),
            available_quantity=(
                None
                if payload.get("available_quantity") is None
                else Decimal(str(payload["available_quantity"]))
            ),
            entry_time=(
                None
                if payload.get("entry_time") is None
                else datetime.fromisoformat(str(payload["entry_time"]))
            ),
            price_observed_at=(
                None
                if payload.get("price_observed_at") is None
                else datetime.fromisoformat(str(payload["price_observed_at"]))
            ),
            price_freshness=(
                None
                if payload.get("price_freshness") is None
                else PriceFreshnessStatus(str(payload["price_freshness"]))
            ),
            trading_calendar_reference=(
                None
                if payload.get("trading_calendar_reference") is None
                else _reference(payload["trading_calendar_reference"])
            ),
        )


def _strategy_position_payload(**values: Any) -> dict[str, Any]:
    current_price = values["current_price"]
    payload = {
        "strategy_version_id": str(values["strategy_version_id"]),
        "symbol": values["symbol"],
        "quantity": str(values["quantity"]),
        "average_cost": str(values["average_cost"]),
        "current_price": None if current_price is None else str(current_price),
        "peak_price": str(values["peak_price"]),
        "sessions_held": values["sessions_held"],
        "add_count": values["add_count"],
        "reduce_count": values["reduce_count"],
    }
    if values.get("account_id") is not None:
        payload.update(
            {
                "account_id": values["account_id"],
                "strategy_version_hash": values["strategy_version_hash"],
                "source_allocation_references": [
                    item.to_canonical_dict()
                    for item in values["source_allocation_references"]
                ],
                "source_fill_references": [
                    item.to_canonical_dict()
                    for item in values["source_fill_references"]
                ],
                "price_observation_references": [
                    item.to_canonical_dict()
                    for item in values["price_observation_references"]
                ],
            }
        )
    if values.get("available_quantity") is not None:
        price_freshness = values["price_freshness"]
        payload.update(
            {
                "available_quantity": str(values["available_quantity"]),
                "entry_time": canonical_datetime(values["entry_time"]),
                "price_observed_at": (
                    None
                    if values["price_observed_at"] is None
                    else canonical_datetime(values["price_observed_at"])
                ),
                "price_freshness": price_freshness.value,
                "trading_calendar_reference": values[
                    "trading_calendar_reference"
                ].to_canonical_dict(),
            }
        )
    return payload


def _strategy_opportunity_payload(**values: Any) -> dict[str, Any]:
    expected_return = values["expected_return"]
    prediction_uncertainty = values["prediction_uncertainty"]
    return {
        "schema_version": "strategy-opportunity/v1",
        "symbol": values["symbol"],
        "strategy_version_reference": values[
            "strategy_version_reference"
        ].to_canonical_dict(),
        "candidate_reference": values["candidate_reference"].to_canonical_dict(),
        "decision_time": canonical_datetime(values["decision_time"]),
        "signal_reference": values["signal_reference"].to_canonical_dict(),
        "forecast_reference": values["forecast_reference"].to_canonical_dict(),
        "context_reference": values["context_reference"].to_canonical_dict(),
        "risk_state_reference": values["risk_state_reference"].to_canonical_dict(),
        "model_reference": values["model_reference"].to_canonical_dict(),
        "signal_active": values["signal_active"],
        "risk_allows_action": values["risk_allows_action"],
        "risk_reason_codes": list(values["risk_reason_codes"]),
        "expected_return": (
            None if expected_return is None else str(expected_return)
        ),
        "prediction_uncertainty": (
            None if prediction_uncertainty is None else str(prediction_uncertainty)
        ),
        "calibration_status": values["calibration_status"],
        "available_at": canonical_datetime(values["available_at"]),
    }


@dataclass(frozen=True, slots=True)
class StrategyDecisionPrice:
    """Frozen decision-time projection with its reloadable Dataset owner."""

    price_owner_reference: RuntimeArtifactReference
    source_dataset_reference: RuntimeArtifactReference
    source_dataset_owner: MarketDataDatasetArtifact
    price_owner: CanonicalMarketBar
    symbol: str
    price: Decimal
    observed_at: datetime
    available_at: datetime
    freshness_expires_at: datetime
    schema_version: str = "strategy-decision-price/v2"

    def __post_init__(self) -> None:
        if self.schema_version != "strategy-decision-price/v2":
            raise ValueError("unsupported Strategy Decision Price schema")
        if self.price_owner_reference.reference_kind != "CANONICAL_MARKET_BAR":
            raise ValueError("Strategy price owner must be a Canonical Market Bar")
        if self.source_dataset_reference.reference_kind != "MARKET_DATA_DATASET":
            raise ValueError("Strategy price source must be a Market Data Dataset")
        self.source_dataset_owner.verify_identity()
        if self.source_dataset_reference != RuntimeArtifactReference(
            "MARKET_DATA_DATASET",
            ArtifactId(str(self.source_dataset_owner.dataset_id)),
            self.source_dataset_owner.content_hash,
        ):
            raise ValueError("Strategy price Dataset owner identity mismatch")
        self.price_owner.verify_identity()
        duration = self.price_owner.timeframe.duration
        if self.price_owner.timeframe is not Timeframe.MINUTE_1 or duration is None:
            raise ValueError("Strategy decision price owner must be a one-minute bar")
        if self.price_owner_reference != RuntimeArtifactReference(
            "CANONICAL_MARKET_BAR",
            self.price_owner.bar_id,
            self.price_owner.content_hash,
        ):
            raise ValueError("Strategy decision price owner identity mismatch")
        owner_matches = tuple(
            item
            for item in self.source_dataset_owner.iter_bars()
            if item.bar_id == self.price_owner.bar_id
        )
        if owner_matches != (self.price_owner,):
            raise ValueError("Strategy price owner is not a member of its Dataset")
        require_text("symbol", self.symbol)
        if self.price <= 0:
            raise ValueError("Strategy decision price must be positive")
        if (
            self.symbol != self.price_owner.symbol
            or self.price != self.price_owner.close
            or self.observed_at != self.price_owner.event_end
            or self.available_at != self.price_owner.available_at
            or self.freshness_expires_at
            != self.price_owner.event_end + duration
        ):
            raise ValueError("Strategy decision price projection disagrees with its owner")
        for value in (
            self.observed_at,
            self.available_at,
            self.freshness_expires_at,
        ):
            canonical_datetime(value)
        if self.available_at < self.observed_at:
            raise ValueError("Strategy price cannot be available before observation")
        if self.freshness_expires_at < self.available_at:
            raise ValueError("Strategy price freshness cannot expire before availability")

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "price_owner_reference": self.price_owner_reference.to_canonical_dict(),
            "source_dataset_reference": self.source_dataset_reference.to_canonical_dict(),
            "source_dataset_owner": {
                "artifact": self.source_dataset_owner.to_canonical_dict(),
                "adjustment_policy": self.source_dataset_owner.adjustment_policy.to_canonical_dict(),
                "partitions": [
                    item.to_canonical_dict()
                    for item in self.source_dataset_owner.partitions
                ],
            },
            "price_owner": self.price_owner.to_canonical_dict(),
            "symbol": self.symbol,
            "price": str(self.price),
            "observed_at": canonical_datetime(self.observed_at),
            "available_at": canonical_datetime(self.available_at),
            "freshness_expires_at": canonical_datetime(self.freshness_expires_at),
        }

    @classmethod
    def from_canonical_dict(cls, payload: Mapping[str, Any]) -> StrategyDecisionPrice:
        owner_payload = _mapping(payload["source_dataset_owner"])
        partitions = tuple(
            MarketDataPartition.from_canonical_dict(_mapping(item))
            for item in _sequence(owner_payload["partitions"])
        )
        adjustment_policy = PriceAdjustmentPolicy.from_canonical_dict(
            _mapping(owner_payload["adjustment_policy"])
        )
        return cls(
            price_owner_reference=_reference(payload["price_owner_reference"]),
            source_dataset_reference=_reference(payload["source_dataset_reference"]),
            source_dataset_owner=MarketDataDatasetArtifact.from_canonical_dict(
                _mapping(owner_payload["artifact"]),
                partitions=partitions,
                adjustment_policy=adjustment_policy,
            ),
            price_owner=CanonicalMarketBar.from_canonical_dict(
                _mapping(payload["price_owner"])
            ),
            symbol=str(payload["symbol"]),
            price=Decimal(str(payload["price"])),
            observed_at=datetime.fromisoformat(str(payload["observed_at"])),
            available_at=datetime.fromisoformat(str(payload["available_at"])),
            freshness_expires_at=datetime.fromisoformat(str(payload["freshness_expires_at"])),
            schema_version=str(payload["schema_version"]),
        )


@dataclass(frozen=True, slots=True)
class StrategyOpportunityInput:
    """Symbol-level Signal/Forecast/Context/Risk/Model lineage consumed by Strategy."""

    symbol: str
    strategy_version_reference: RuntimeArtifactReference
    candidate_reference: RuntimeArtifactReference
    decision_time: datetime
    signal_reference: RuntimeArtifactReference
    forecast_reference: RuntimeArtifactReference
    context_reference: RuntimeArtifactReference
    risk_state_reference: RuntimeArtifactReference
    model_reference: RuntimeArtifactReference
    signal_active: bool
    risk_allows_action: bool
    risk_reason_codes: tuple[str, ...]
    expected_return: Decimal | None
    prediction_uncertainty: Decimal | None
    calibration_status: str
    available_at: datetime
    binding_hash: str

    def __post_init__(self) -> None:
        require_text("symbol", self.symbol)
        canonical_datetime(self.decision_time)
        canonical_datetime(self.available_at)
        if self.available_at > self.decision_time:
            raise ValueError("Strategy opportunity lineage is unavailable at DecisionTime")
        expected_kinds = {
            "strategy_version_reference": {"STRATEGY_VERSION"},
            "candidate_reference": {"CANDIDATE_SET"},
            "signal_reference": {
                "SIGNAL_SNAPSHOT",
                "CANONICAL_SIGNAL_SNAPSHOT",
                "HISTORICAL_SIGNAL",
            },
            "forecast_reference": {
                "PATH_FORECAST",
                "CONDITIONAL_FORECAST_RESULT",
                "HISTORICAL_FORECAST",
            },
            "context_reference": {
                "CONTEXT_CONDITIONAL_EVALUATION",
                "HISTORICAL_CONTEXT_CONDITIONAL_EVIDENCE",
                "HISTORICAL_CONTEXT",
            },
            "risk_state_reference": {
                "PRE_STRATEGY_RISK_STATE",
            },
            "model_reference": {
                "CONDITIONAL_FORECAST_MODEL",
                "MODEL_VERSION",
                "PATH_FORECAST",
                "RESEARCH_MODEL_ARTIFACT",
            },
        }
        for field_name, kinds in expected_kinds.items():
            reference = getattr(self, field_name)
            if reference.reference_kind not in kinds:
                raise ValueError(f"Strategy opportunity {field_name} kind is invalid")
        if self.calibration_status not in {
            "NOT_CALIBRATED",
            "CALIBRATED_EXPLORATORY",
            "DATA_INSUFFICIENT",
        }:
            raise ValueError("unsupported Strategy Forecast calibration status")
        if self.prediction_uncertainty is not None and self.prediction_uncertainty < 0:
            raise ValueError("Strategy prediction uncertainty cannot be negative")
        if self.risk_reason_codes != tuple(sorted(set(self.risk_reason_codes))):
            raise ValueError("Strategy Risk reason codes must be unique and sorted")
        if self.risk_allows_action == bool(self.risk_reason_codes):
            raise ValueError("Strategy Risk state and reason codes disagree")
        if self.expected_return is None and self.calibration_status != "DATA_INSUFFICIENT":
            raise ValueError("available Strategy Forecast requires expected return")
        if canonical_hash(self.identity_payload()) != self.binding_hash:
            raise ValueError("Strategy opportunity binding hash mismatch")

    @classmethod
    def create(cls, **values: Any) -> StrategyOpportunityInput:
        payload = _strategy_opportunity_payload(**values)
        return cls(**values, binding_hash=canonical_hash(payload))

    def identity_payload(self) -> dict[str, Any]:
        return _strategy_opportunity_payload(
            **{
                field_name: getattr(self, field_name)
                for field_name in (
                    "symbol",
                    "strategy_version_reference",
                    "candidate_reference",
                    "decision_time",
                    "signal_reference",
                    "forecast_reference",
                    "context_reference",
                    "risk_state_reference",
                    "model_reference",
                    "signal_active",
                    "risk_allows_action",
                    "risk_reason_codes",
                    "expected_return",
                    "prediction_uncertainty",
                    "calibration_status",
                    "available_at",
                )
            }
        )

    def to_canonical_dict(self) -> dict[str, Any]:
        return {**self.identity_payload(), "binding_hash": self.binding_hash}

    @property
    def opportunity_id(self) -> ArtifactId:
        return ArtifactId(f"strategy-opportunity:{self.binding_hash[7:]}")

    @property
    def reference(self) -> RuntimeArtifactReference:
        return RuntimeArtifactReference(
            "STRATEGY_OPPORTUNITY",
            self.opportunity_id,
            self.binding_hash,
        )

    @classmethod
    def from_canonical_dict(
        cls, payload: Mapping[str, Any]
    ) -> StrategyOpportunityInput:
        expected_return = payload["expected_return"]
        uncertainty = payload["prediction_uncertainty"]
        return cls(
            symbol=str(payload["symbol"]),
            strategy_version_reference=_reference(
                payload["strategy_version_reference"]
            ),
            candidate_reference=_reference(payload["candidate_reference"]),
            decision_time=datetime.fromisoformat(str(payload["decision_time"])),
            signal_reference=_reference(payload["signal_reference"]),
            forecast_reference=_reference(payload["forecast_reference"]),
            context_reference=_reference(payload["context_reference"]),
            risk_state_reference=_reference(payload["risk_state_reference"]),
            model_reference=_reference(payload["model_reference"]),
            signal_active=bool(payload["signal_active"]),
            risk_allows_action=bool(payload["risk_allows_action"]),
            risk_reason_codes=tuple(
                str(item) for item in _sequence(payload["risk_reason_codes"])
            ),
            expected_return=(
                None if expected_return is None else Decimal(str(expected_return))
            ),
            prediction_uncertainty=(
                None if uncertainty is None else Decimal(str(uncertainty))
            ),
            calibration_status=str(payload["calibration_status"]),
            available_at=datetime.fromisoformat(str(payload["available_at"])),
            binding_hash=str(payload["binding_hash"]),
        )


@dataclass(frozen=True, slots=True)
class StrategyRuntimeInput:
    origin: StrategyRunOrigin
    authority_mode: RuntimeAuthorityMode
    parent_run_reference: RuntimeArtifactReference
    parent_tick_reference: RuntimeArtifactReference
    candidate_set: CandidateSet
    dataset_reference: RuntimeArtifactReference
    decision_time: datetime
    positions: tuple[StrategyPositionState, ...]
    code_reference: RuntimeArtifactReference
    configuration_reference: RuntimeArtifactReference
    decision_prices: tuple[StrategyDecisionPrice, ...] | None = ()
    opportunities: tuple[StrategyOpportunityInput, ...] | None = ()

    def __post_init__(self) -> None:
        canonical_datetime(self.decision_time)
        position_keys = tuple((str(item.strategy_version_id), item.symbol) for item in self.positions)
        if position_keys != tuple(sorted(set(position_keys))):
            raise ValueError("Strategy position input must be unique and sorted")
        prices = self.decision_prices or ()
        price_symbols = tuple(item.symbol for item in prices)
        if price_symbols != tuple(sorted(set(price_symbols))):
            raise ValueError("Strategy decision prices must be unique and sorted")
        if any(
            item.observed_at > self.decision_time
            or item.available_at > self.decision_time
            or item.freshness_expires_at < self.decision_time
            or item.source_dataset_owner.decision_time != self.decision_time
            for item in prices
        ):
            raise ValueError("Strategy decision price must be available and fresh at decision time")
        opportunities = self.opportunities or ()
        opportunity_keys = tuple(
            (str(item.strategy_version_reference.artifact_id), item.symbol)
            for item in opportunities
        )
        if opportunity_keys != tuple(sorted(set(opportunity_keys))):
            raise ValueError("Strategy opportunities must be unique and sorted")
        candidate_reference = RuntimeArtifactReference(
            "CANDIDATE_SET",
            self.candidate_set.envelope.artifact_id,
            self.candidate_set.envelope.content_hash,
        )
        if any(
            item.candidate_reference != candidate_reference
            or item.decision_time != self.decision_time
            for item in opportunities
        ):
            raise ValueError(
                "Strategy opportunity must bind the Candidate owner and DecisionTime"
            )
        admitted_symbols = {
            item.symbol for item in self.candidate_set.records
        } | {item.symbol for item in self.positions}
        if any(item.symbol not in admitted_symbols for item in opportunities):
            raise ValueError(
                "Strategy opportunity must belong to a Candidate or existing Position"
            )
        self.candidate_set.envelope.verify_payload(self.candidate_set.artifact_payload())

    @property
    def input_hash(self) -> str:
        return canonical_hash(self.to_canonical_dict())

    def to_canonical_dict(self) -> dict[str, Any]:
        payload = {
            "origin": self.origin.value,
            "authority_mode": self.authority_mode.value,
            "parent_run_reference": self.parent_run_reference.to_canonical_dict(),
            "parent_tick_reference": self.parent_tick_reference.to_canonical_dict(),
            "candidate_set": self.candidate_set.to_canonical_dict(),
            "dataset_reference": self.dataset_reference.to_canonical_dict(),
            "decision_time": canonical_datetime(self.decision_time),
            "positions": [item.to_canonical_dict() for item in self.positions],
            "code_reference": self.code_reference.to_canonical_dict(),
            "configuration_reference": self.configuration_reference.to_canonical_dict(),
        }
        if self.decision_prices is not None:
            payload["decision_prices"] = [item.to_canonical_dict() for item in self.decision_prices]
        if self.opportunities is not None:
            payload["opportunities"] = [
                item.to_canonical_dict() for item in self.opportunities
            ]
        return payload

    @classmethod
    def from_canonical_dict(cls, payload: Mapping[str, Any]) -> StrategyRuntimeInput:
        candidate_payload = _mapping(payload["candidate_set"])
        return cls(
            origin=StrategyRunOrigin(str(payload["origin"])),
            authority_mode=RuntimeAuthorityMode(str(payload["authority_mode"])),
            parent_run_reference=_reference(payload["parent_run_reference"]),
            parent_tick_reference=_reference(payload["parent_tick_reference"]),
            candidate_set=CandidateSet.from_canonical_dict(dict(candidate_payload)),
            dataset_reference=_reference(payload["dataset_reference"]),
            decision_time=datetime.fromisoformat(str(payload["decision_time"])),
            positions=tuple(StrategyPositionState.from_canonical_dict(_mapping(item)) for item in _sequence(payload["positions"])),
            code_reference=_reference(payload["code_reference"]),
            configuration_reference=_reference(payload["configuration_reference"]),
            decision_prices=(
                None
                if "decision_prices" not in payload
                else tuple(StrategyDecisionPrice.from_canonical_dict(_mapping(item)) for item in _sequence(payload["decision_prices"]))
            ),
            opportunities=(
                None
                if "opportunities" not in payload
                else tuple(
                    StrategyOpportunityInput.from_canonical_dict(_mapping(item))
                    for item in _sequence(payload["opportunities"])
                )
            ),
        )


@dataclass(frozen=True, slots=True)
class GateAttribution:
    symbol: str
    eligibility_status: StrategyEligibilityStatus
    candidate_status: str
    rank: int | None
    action: CanonicalStrategyAction
    reason_codes: tuple[str, ...]

    def __post_init__(self) -> None:
        require_text("symbol", self.symbol)
        require_text("candidate_status", self.candidate_status)
        if self.rank is not None and self.rank <= 0:
            raise ValueError("Strategy gate rank must be positive")
        _require_text_set("Strategy gate reason", self.reason_codes)

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "eligibility_status": self.eligibility_status.value,
            "candidate_status": self.candidate_status,
            "rank": self.rank,
            "action": self.action.value,
            "reason_codes": list(self.reason_codes),
        }

    @classmethod
    def from_canonical_dict(cls, payload: Mapping[str, Any]) -> GateAttribution:
        rank = payload["rank"]
        return cls(
            symbol=str(payload["symbol"]),
            eligibility_status=StrategyEligibilityStatus(str(payload["eligibility_status"])),
            candidate_status=str(payload["candidate_status"]),
            rank=None if rank is None else int(rank),
            action=CanonicalStrategyAction(str(payload["action"])),
            reason_codes=_strings(payload["reason_codes"]),
        )


@dataclass(frozen=True, slots=True)
class StrategyProposal:
    proposal_id: ArtifactId
    proposal_hash: str
    strategy_run_id: ArtifactId
    strategy_version_reference: RuntimeArtifactReference
    candidate_reference: RuntimeArtifactReference
    symbol: str
    action: CanonicalStrategyAction
    desired_weight: Decimal
    utility_score: Decimal | None
    reason_codes: tuple[str, ...]
    limitations: tuple[str, ...]
    schema_version: str = "strategy-proposal/v1"

    def __post_init__(self) -> None:
        if self.schema_version != "strategy-proposal/v1":
            raise ValueError("unsupported Strategy Proposal schema")
        require_sha256("proposal_hash", self.proposal_hash)
        require_text("symbol", self.symbol)
        if not Decimal("-1") <= self.desired_weight <= Decimal("1"):
            raise ValueError("Strategy desired weight must be within [-1, 1]")
        if self.action in {CanonicalStrategyAction.NO_ACTION, CanonicalStrategyAction.HOLD} and self.desired_weight != 0:
            raise ValueError("NO_ACTION/HOLD cannot request a weight delta")
        if self.action in {CanonicalStrategyAction.ENTER, CanonicalStrategyAction.ADD} and self.desired_weight <= 0:
            raise ValueError("ENTER/ADD require a positive desired weight")
        if self.action in {CanonicalStrategyAction.REDUCE, CanonicalStrategyAction.EXIT} and self.desired_weight >= 0:
            raise ValueError("REDUCE/EXIT require a negative desired weight")
        _require_text_set("Strategy Proposal reason", self.reason_codes)
        _require_text_set("Strategy Proposal limitation", self.limitations)
        digest = canonical_hash(self.identity_payload())
        if digest != self.proposal_hash or str(self.proposal_id) != f"strategy-proposal:{digest[7:]}":
            raise ValueError("Strategy Proposal identity mismatch")

    @classmethod
    def create(cls, **values: Any) -> StrategyProposal:
        normalized = dict(values)
        normalized["reason_codes"] = tuple(sorted(set(values["reason_codes"])))
        normalized["limitations"] = tuple(sorted(set(values["limitations"])))
        normalized.setdefault("schema_version", "strategy-proposal/v1")
        digest = canonical_hash(_proposal_payload(**normalized))
        return cls(
            proposal_id=ArtifactId(f"strategy-proposal:{digest[7:]}"),
            proposal_hash=digest,
            **normalized,
        )

    def identity_payload(self) -> dict[str, Any]:
        return _proposal_payload(
            strategy_run_id=self.strategy_run_id,
            strategy_version_reference=self.strategy_version_reference,
            candidate_reference=self.candidate_reference,
            symbol=self.symbol,
            action=self.action,
            desired_weight=self.desired_weight,
            utility_score=self.utility_score,
            reason_codes=self.reason_codes,
            limitations=self.limitations,
            schema_version=self.schema_version,
        )

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "proposal_id": str(self.proposal_id),
            "proposal_hash": self.proposal_hash,
            **self.identity_payload(),
        }

    @classmethod
    def from_canonical_dict(cls, payload: Mapping[str, Any]) -> StrategyProposal:
        utility_score = payload["utility_score"]
        return cls(
            proposal_id=ArtifactId(str(payload["proposal_id"])),
            proposal_hash=str(payload["proposal_hash"]),
            strategy_run_id=ArtifactId(str(payload["strategy_run_id"])),
            strategy_version_reference=_reference(payload["strategy_version_reference"]),
            candidate_reference=_reference(payload["candidate_reference"]),
            symbol=str(payload["symbol"]),
            action=CanonicalStrategyAction(str(payload["action"])),
            desired_weight=Decimal(str(payload["desired_weight"])),
            utility_score=(None if utility_score is None else Decimal(str(utility_score))),
            reason_codes=_strings(payload["reason_codes"]),
            limitations=_strings(payload["limitations"]),
            schema_version=str(payload["schema_version"]),
        )


@dataclass(frozen=True, slots=True)
class StrategyRun:
    run_id: ArtifactId
    run_hash: str
    cycle_id: ArtifactId
    strategy_version_reference: RuntimeArtifactReference
    origin: StrategyRunOrigin
    authority_mode: RuntimeAuthorityMode
    decision_time: datetime
    input_hash: str
    status: StrategyRunStatus
    gate_attributions: tuple[GateAttribution, ...]
    proposals: tuple[StrategyProposal, ...]
    reason_codes: tuple[str, ...]
    schema_version: str = "strategy-run/v1"

    def __post_init__(self) -> None:
        require_sha256("run_hash", self.run_hash)
        require_sha256("input_hash", self.input_hash)
        canonical_datetime(self.decision_time)
        symbols = tuple(item.symbol for item in self.gate_attributions)
        if symbols != tuple(sorted(set(symbols))):
            raise ValueError("Strategy Run gate attribution must cover unique sorted symbols")
        proposal_ids = tuple(str(item.proposal_id) for item in self.proposals)
        if proposal_ids != tuple(sorted(set(proposal_ids))):
            raise ValueError("Strategy Run proposals must be unique and sorted")
        if any(item.strategy_run_id != self.run_id for item in self.proposals):
            raise ValueError("Strategy Proposal belongs to another Strategy Run")
        _require_text_set("Strategy Run reason", self.reason_codes)
        digest = canonical_hash(self.identity_payload())
        if digest != self.run_hash:
            raise ValueError("Strategy Run hash mismatch")

    @staticmethod
    def identity(cycle_id: ArtifactId, version: StrategyVersion) -> ArtifactId:
        digest = canonical_hash({"cycle_id": str(cycle_id), "strategy_version_id": str(version.version_id)})
        return ArtifactId(f"strategy-run:{digest[7:]}")

    @classmethod
    def create(cls, **values: Any) -> StrategyRun:
        normalized = dict(values)
        normalized["gate_attributions"] = tuple(sorted(values["gate_attributions"], key=lambda item: item.symbol))
        normalized["proposals"] = tuple(sorted(values["proposals"], key=lambda item: str(item.proposal_id)))
        normalized["reason_codes"] = tuple(sorted(set(values["reason_codes"])))
        normalized.setdefault("schema_version", "strategy-run/v1")
        digest = canonical_hash(_run_payload(**normalized))
        return cls(run_hash=digest, **normalized)

    def identity_payload(self) -> dict[str, Any]:
        return _run_payload(
            run_id=self.run_id,
            cycle_id=self.cycle_id,
            strategy_version_reference=self.strategy_version_reference,
            origin=self.origin,
            authority_mode=self.authority_mode,
            decision_time=self.decision_time,
            input_hash=self.input_hash,
            status=self.status,
            gate_attributions=self.gate_attributions,
            proposals=self.proposals,
            reason_codes=self.reason_codes,
            schema_version=self.schema_version,
        )

    def to_canonical_dict(self) -> dict[str, Any]:
        return {"run_hash": self.run_hash, **self.identity_payload()}

    @classmethod
    def from_canonical_dict(cls, payload: Mapping[str, Any]) -> StrategyRun:
        return cls(
            run_id=ArtifactId(str(payload["run_id"])),
            run_hash=str(payload["run_hash"]),
            cycle_id=ArtifactId(str(payload["cycle_id"])),
            strategy_version_reference=_reference(payload["strategy_version_reference"]),
            origin=StrategyRunOrigin(str(payload["origin"])),
            authority_mode=RuntimeAuthorityMode(str(payload["authority_mode"])),
            decision_time=datetime.fromisoformat(str(payload["decision_time"])),
            input_hash=str(payload["input_hash"]),
            status=StrategyRunStatus(str(payload["status"])),
            gate_attributions=tuple(
                GateAttribution.from_canonical_dict(_mapping(item)) for item in _sequence(payload["gate_attributions"])
            ),
            proposals=tuple(StrategyProposal.from_canonical_dict(_mapping(item)) for item in _sequence(payload["proposals"])),
            reason_codes=_strings(payload["reason_codes"]),
            schema_version=str(payload["schema_version"]),
        )


@dataclass(frozen=True, slots=True)
class MultiStrategyCycle:
    cycle_id: ArtifactId
    cycle_hash: str
    runtime_input: StrategyRuntimeInput
    runs: tuple[StrategyRun, ...]
    created_at: datetime
    schema_version: str = "multi-strategy-cycle/v1"

    def __post_init__(self) -> None:
        require_sha256("cycle_hash", self.cycle_hash)
        canonical_datetime(self.created_at)
        version_ids = tuple(str(item.strategy_version_reference.artifact_id) for item in self.runs)
        if version_ids != tuple(sorted(set(version_ids))):
            raise ValueError("Multi-Strategy Cycle versions must be unique and sorted")
        if any(item.cycle_id != self.cycle_id for item in self.runs):
            raise ValueError("Strategy Run belongs to another cycle")
        if self.cycle_id != self.identity(
            self.runtime_input,
            tuple(item.strategy_version_reference for item in self.runs),
        ):
            raise ValueError("Multi-Strategy Cycle identity omits Strategy Version set")
        if canonical_hash(self.identity_payload()) != self.cycle_hash:
            raise ValueError("Multi-Strategy Cycle hash mismatch")

    @staticmethod
    def identity(
        runtime_input: StrategyRuntimeInput,
        strategy_version_references: tuple[RuntimeArtifactReference, ...],
    ) -> ArtifactId:
        versions = _references(strategy_version_references)
        digest = canonical_hash(
            {
                "schema_version": "multi-strategy-cycle-seed/v2",
                "runtime_input": runtime_input.to_canonical_dict(),
                "strategy_version_references": [item.to_canonical_dict() for item in versions],
            }
        )
        return ArtifactId(f"multi-strategy-cycle:{digest[7:]}")

    @classmethod
    def create(
        cls,
        *,
        cycle_id: ArtifactId,
        runtime_input: StrategyRuntimeInput,
        runs: tuple[StrategyRun, ...],
        created_at: datetime,
    ) -> MultiStrategyCycle:
        ordered = tuple(sorted(runs, key=lambda item: str(item.strategy_version_reference.artifact_id)))
        digest = canonical_hash(
            _cycle_payload(
                cycle_id=cycle_id,
                runtime_input=runtime_input,
                runs=ordered,
                created_at=created_at,
                schema_version="multi-strategy-cycle/v1",
            )
        )
        return cls(
            cycle_id=cycle_id,
            cycle_hash=digest,
            runtime_input=runtime_input,
            runs=ordered,
            created_at=created_at,
            schema_version="multi-strategy-cycle/v1",
        )

    def identity_payload(self) -> dict[str, Any]:
        return _cycle_payload(
            cycle_id=self.cycle_id,
            runtime_input=self.runtime_input,
            runs=self.runs,
            created_at=self.created_at,
            schema_version=self.schema_version,
        )

    def to_canonical_dict(self) -> dict[str, Any]:
        return {"cycle_hash": self.cycle_hash, **self.identity_payload()}

    @classmethod
    def from_canonical_dict(cls, payload: Mapping[str, Any]) -> MultiStrategyCycle:
        return cls(
            cycle_id=ArtifactId(str(payload["cycle_id"])),
            cycle_hash=str(payload["cycle_hash"]),
            runtime_input=StrategyRuntimeInput.from_canonical_dict(_mapping(payload["runtime_input"])),
            runs=tuple(StrategyRun.from_canonical_dict(_mapping(item)) for item in _sequence(payload["runs"])),
            created_at=datetime.fromisoformat(str(payload["created_at"])),
            schema_version=str(payload["schema_version"]),
        )


def strategy_reference(version: StrategyVersion) -> RuntimeArtifactReference:
    return RuntimeArtifactReference("STRATEGY_VERSION", version.version_id, version.version_hash)


def _contract_fields() -> tuple[str, ...]:
    return (
        "strategy_id",
        "family",
        "semantic_version",
        "objective",
        "universe_reference",
        "target_references",
        "decision_times",
        "horizon_sessions",
        "candidate_policy_version",
        "action_policy_version",
        "portfolio_weighting",
        "top_k",
        "strategy_budget",
        "cost_model_reference",
        "evaluation_protocol_reference",
        "code_reference",
        "configuration_reference",
        "parameters",
        "limitations",
        "forecast_requirement",
        "schema_version",
    )


def _contract_payload(**values: Any) -> dict[str, Any]:
    payload = {
        "schema_version": values["schema_version"],
        "strategy_id": str(values["strategy_id"]),
        "family": values["family"].value,
        "semantic_version": values["semantic_version"],
        "objective": values["objective"],
        "universe_reference": values["universe_reference"].to_canonical_dict(),
        "target_references": [item.to_canonical_dict() for item in values["target_references"]],
        "decision_times": list(values["decision_times"]),
        "horizon_sessions": list(values["horizon_sessions"]),
        "candidate_policy_version": values["candidate_policy_version"],
        "action_policy_version": values["action_policy_version"],
        "portfolio_weighting": values["portfolio_weighting"].value,
        "top_k": values["top_k"],
        "strategy_budget": str(values["strategy_budget"]),
        "cost_model_reference": values["cost_model_reference"].to_canonical_dict(),
        "evaluation_protocol_reference": values["evaluation_protocol_reference"].to_canonical_dict(),
        "code_reference": values["code_reference"].to_canonical_dict(),
        "configuration_reference": values["configuration_reference"].to_canonical_dict(),
        "parameters": [list(item) for item in values["parameters"]],
        "limitations": list(values["limitations"]),
    }
    if values["schema_version"] == "strategy-contract/v2":
        payload["forecast_requirement"] = values["forecast_requirement"].value
    return payload


def _strategy_version_payload(**values: Any) -> dict[str, Any]:
    return {
        "schema_version": values["schema_version"],
        "contract_reference": values["contract_reference"].to_canonical_dict(),
        "family": values["family"].value,
        "semantic_version": values["semantic_version"],
        "lifecycle_status": values["lifecycle_status"],
        "research_status": values["research_status"],
        "limitations": list(values["limitations"]),
    }


def _proposal_payload(**values: Any) -> dict[str, Any]:
    return {
        "schema_version": values["schema_version"],
        "strategy_run_id": str(values["strategy_run_id"]),
        "strategy_version_reference": values["strategy_version_reference"].to_canonical_dict(),
        "candidate_reference": values["candidate_reference"].to_canonical_dict(),
        "symbol": values["symbol"],
        "action": values["action"].value,
        "desired_weight": str(values["desired_weight"]),
        "utility_score": None if values["utility_score"] is None else str(values["utility_score"]),
        "reason_codes": list(values["reason_codes"]),
        "limitations": list(values["limitations"]),
    }


def _run_payload(**values: Any) -> dict[str, Any]:
    return {
        "schema_version": values["schema_version"],
        "run_id": str(values["run_id"]),
        "cycle_id": str(values["cycle_id"]),
        "strategy_version_reference": values["strategy_version_reference"].to_canonical_dict(),
        "origin": values["origin"].value,
        "authority_mode": values["authority_mode"].value,
        "decision_time": canonical_datetime(values["decision_time"]),
        "input_hash": values["input_hash"],
        "status": values["status"].value,
        "gate_attributions": [item.to_canonical_dict() for item in values["gate_attributions"]],
        "proposals": [item.to_canonical_dict() for item in values["proposals"]],
        "reason_codes": list(values["reason_codes"]),
    }


def _cycle_payload(**values: Any) -> dict[str, Any]:
    return {
        "schema_version": values["schema_version"],
        "cycle_id": str(values["cycle_id"]),
        "runtime_input": values["runtime_input"].to_canonical_dict(),
        "runs": [item.to_canonical_dict() for item in values["runs"]],
        "created_at": canonical_datetime(values["created_at"]),
    }


def _reference(value: object) -> RuntimeArtifactReference:
    if not isinstance(value, Mapping):
        raise ValueError("expected Artifact reference object")
    return RuntimeArtifactReference.from_canonical_dict(value)


def _references_from(value: object) -> tuple[RuntimeArtifactReference, ...]:
    if not isinstance(value, list):
        raise ValueError("expected Artifact reference array")
    return _references(tuple(_reference(item) for item in value))


def _references(values: tuple[RuntimeArtifactReference, ...]) -> tuple[RuntimeArtifactReference, ...]:
    return tuple(
        sorted(
            set(values),
            key=lambda item: (item.reference_kind, str(item.artifact_id), item.content_hash),
        )
    )


def _require_references(label: str, values: tuple[RuntimeArtifactReference, ...]) -> None:
    if not values or values != _references(values):
        raise ValueError(f"{label} references must be non-empty, unique, and sorted")


def _require_pairs(label: str, values: tuple[tuple[str, str], ...]) -> None:
    if values != tuple(sorted(set(values))):
        raise ValueError(f"{label} values must be unique and sorted")
    for name, value in values:
        require_text(f"{label} name", name)
        require_text(f"{label} value", value)


def _require_text_set(label: str, values: tuple[str, ...]) -> None:
    if not values or values != tuple(sorted(set(values))):
        raise ValueError(f"{label} values must be non-empty, unique, and sorted")
    for value in values:
        require_text(label, value)


def _strings(value: object) -> tuple[str, ...]:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ValueError("expected string array")
    return tuple(value)


def _integers(value: object) -> tuple[int, ...]:
    if not isinstance(value, list) or any(isinstance(item, bool) or not isinstance(item, int) for item in value):
        raise ValueError("expected integer array")
    return tuple(value)


def _pairs(value: object) -> tuple[tuple[str, str], ...]:
    if not isinstance(value, list):
        raise ValueError("expected pair array")
    pairs: list[tuple[str, str]] = []
    for item in value:
        if not isinstance(item, list) or len(item) != 2:
            raise ValueError("expected pair")
        pairs.append((str(item[0]), str(item[1])))
    return tuple(pairs)


def _mapping(value: object) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError("expected object")
    return value


def _sequence(value: object) -> list[object]:
    if not isinstance(value, list):
        raise ValueError("expected array")
    return value


__all__ = [
    "CanonicalStrategyAction",
    "GateAttribution",
    "MultiStrategyCycle",
    "PortfolioWeightingMethod",
    "PriceFreshnessStatus",
    "StrategyContract",
    "StrategyDecisionPrice",
    "StrategyEligibilityStatus",
    "StrategyFamily",
    "StrategyForecastRequirement",
    "StrategyOpportunityInput",
    "StrategyPositionState",
    "StrategyProposal",
    "StrategyRegistry",
    "StrategyRun",
    "StrategyRunOrigin",
    "StrategyRunStatus",
    "StrategyRuntimeInput",
    "StrategyVersion",
    "strategy_reference",
]
