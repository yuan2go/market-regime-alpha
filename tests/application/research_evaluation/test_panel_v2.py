from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from market_regime_alpha.application.continuous_research.journal import (
    RuntimeArtifactReference,
)
from market_regime_alpha.application.research_evaluation.panel_v2 import (
    FrozenResearchPanelV2,
    ResearchFactorValue,
    ResearchPanelRow,
    ResearchPanelSliceV2,
    load_research_panel_v2,
    publish_research_panel_v2,
)
from market_regime_alpha.application.research_evaluation.targets import (
    engineering_multi_horizon_protocol,
)
from market_regime_alpha.core.identity import ArtifactId


NOW = datetime(2026, 8, 12, 8, 0, tzinfo=UTC)
HASH = "sha256:" + "a" * 64


def _ref(kind: str, value: str) -> RuntimeArtifactReference:
    return RuntimeArtifactReference(kind, ArtifactId(value), HASH)


def _row(symbol: str, *, included: bool, selected: bool) -> ResearchPanelRow:
    return ResearchPanelRow.create(
        symbol=symbol,
        universe_eligible=True,
        pool_included=included,
        pool_gate_result="INCLUDED" if included else "EXCLUDED",
        pool_exclusion_reasons=() if included else ("POOL_GATE_CLOSED",),
        candidate_status="SELECTED" if selected else "REJECTED",
        candidate_rank=1 if selected else None,
        candidate_score=Decimal("0.8") if selected else Decimal("0.2"),
        candidate_reason_codes=("CANDIDATE_EVALUATED",),
        factor_values=(
            ResearchFactorValue(
                factor_id="price",
                raw_exposure=Decimal("0.2"),
                normalized_exposure=Decimal("0.1"),
                contribution=Decimal("0.05"),
            ),
            ResearchFactorValue(
                factor_id="volume",
                raw_exposure=Decimal("0.3"),
                normalized_exposure=Decimal("0.2"),
                contribution=Decimal("0.07"),
            ),
        ),
        signal_features=(("signal_score", Decimal("0.4")),),
        forecast_outputs=(("path_score", Decimal("0.3")),),
        target_labels=(_ref("TARGET_OUTCOME_LABEL", f"label-{symbol}"),),
        reason_codes=("FULL_EVALUATED_UNIVERSE_ROW",),
    )


def test_panel_v2_preserves_selected_and_excluded_full_population(tmp_path) -> None:
    protocol = engineering_multi_horizon_protocol()
    rows = (
        _row("000001.SZ", included=False, selected=False),
        _row("600000.SH", included=True, selected=True),
    )
    panel_slice = ResearchPanelSliceV2.create(
        trading_date=date(2026, 8, 10),
        run_id=ArtifactId("run-1"),
        tick_id=ArtifactId("tick-1"),
        shadow_decision=_ref("SHADOW_DECISION", "decision-1"),
        summary=_ref("SUMMARY", "summary-1"),
        source_manifest=_ref("SOURCE_MANIFEST", "manifest-1"),
        dataset=_ref("DATASET", "dataset-1"),
        feature_bundle=_ref("FEATURE", "feature-1"),
        market_state=_ref("MARKET_STATE", "market-1"),
        etf_state=_ref("ETF_STATE", "etf-1"),
        theme_state=_ref("THEME_STATE", "theme-1"),
        capital_state=_ref("CAPITAL_STATE", "capital-1"),
        dynamic_pool=_ref("DYNAMIC_POOL", "pool-1"),
        candidate_set=_ref("CANDIDATE_SET", "candidate-1"),
        signal=_ref("SIGNAL", "signal-1"),
        forecast=_ref("FORECAST", "forecast-1"),
        model_references=(_ref("MODEL_SELECTION", "model-1"),),
        configuration_references=(_ref("CONFIGURATION", "config-1"),),
        state_policy_references=(_ref("STATE_POLICY", "policy-1"),),
        target_protocol=RuntimeArtifactReference("OUTCOME_TARGET_PROTOCOL", protocol.protocol_id, protocol.protocol_hash),
        targeted_outcome=_ref("TARGETED_SHADOW_OUTCOME", "outcome-1"),
        rows=rows,
        reason_codes=("FROZEN_FULL_RESEARCH_PANEL",),
    )
    panel = FrozenResearchPanelV2.create(
        target_protocol=protocol,
        slices=(panel_slice,),
        created_at=NOW,
    )

    path = publish_research_panel_v2(root=tmp_path, panel=panel)

    assert panel.row_count == 2
    assert load_research_panel_v2(path) == panel
    assert panel.slices[0].rows[0].pool_included is False
    assert panel.slices[0].rows[1].candidate_status == "SELECTED"
    assert {item.factor_id for item in panel.slices[0].rows[1].factor_values} == {
        "price",
        "volume",
    }

    payload = panel.to_canonical_dict()
    payload["slices"][0]["rows"][0]["universe_eligible"] = "true"
    with pytest.raises(ValueError, match="boolean"):
        FrozenResearchPanelV2.from_canonical_dict(payload)
