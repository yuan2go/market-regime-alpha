from __future__ import annotations

from datetime import date, timedelta
import json

import pytest

from market_regime_alpha.research.tencent_composite_artifacts import (
    write_tencent_composite_run,
)
from market_regime_alpha.research.tencent_composite_contracts import (
    CompositeDispositionCode,
    CompositeQualityReport,
    CompositeSymbolDisposition,
)


class FakeCandidateRun:
    def panel_summary(self) -> dict[str, object]:
        return {
            "data_eligibility": "EXPLORATORY",
            "decision_date_count": 60,
            "accepted_symbols": ["000001.SZ"],
        }

    def evaluation_summary(self) -> dict[str, object]:
        return {
            "selection_policy": "FIXED_UNTUNED_NO_WINNER_SELECTION",
            "targets": [],
        }


def _quality() -> CompositeQualityReport:
    symbols = tuple(f"{index + 1:06d}.SZ" for index in range(20))
    accepted = symbols[:16]
    return CompositeQualityReport(
        requested_symbols=symbols,
        accepted_symbols=accepted,
        dispositions=tuple(
            CompositeSymbolDisposition(
                symbol=symbol,
                code=(
                    CompositeDispositionCode.ACCEPTED
                    if symbol in accepted
                    else CompositeDispositionCode.REJECTED_FETCH_FAILURE
                ),
                complete_session_count=82 if symbol in accepted else 0,
                findings=(),
            )
            for symbol in symbols
        ),
        common_session_dates=tuple(
            date(2026, 1, 1) + timedelta(days=index)
            for index in range(82)
        ),
        required_session_count=82,
        minimum_accepted_symbols=16,
    )


def test_writer_creates_complete_non_overwriting_run(tmp_path) -> None:
    manifest = {
        "run_id": "run-abc123",
        "data_eligibility": "EXPLORATORY",
        "limitations": ["CURRENT_WATCHLIST_BACKFILL_BIAS"],
        "source_conflict_count": 0,
    }
    output = write_tencent_composite_run(
        root=tmp_path,
        run_id="run-abc123",
        manifest=manifest,
        quality=_quality(),
        conflicts=(),
        candidate_run=FakeCandidateRun(),
        dividend_refresh={"status": "not-run"},
    )

    assert {path.name for path in output.iterdir()} == {
        "manifest.json",
        "quality.json",
        "source_conflicts.json",
        "candidate_panel_summary.json",
        "b0_b1_evaluation.json",
        "candidate_report.md",
        "dividend_t_refresh.json",
    }
    assert json.loads((output / "manifest.json").read_text())["data_eligibility"] == (
        "EXPLORATORY"
    )
    report = (output / "candidate_report.md").read_text()
    assert report.index("Authority and limitations") < report.index("Model metrics")

    with pytest.raises(FileExistsError):
        write_tencent_composite_run(
            root=tmp_path,
            run_id="run-abc123",
            manifest=manifest,
            quality=_quality(),
            conflicts=(),
            candidate_run=FakeCandidateRun(),
            dividend_refresh={"status": "not-run"},
        )


def test_writer_rejects_non_exploratory_manifest(tmp_path) -> None:
    with pytest.raises(ValueError, match="EXPLORATORY"):
        write_tencent_composite_run(
            root=tmp_path,
            run_id="run-invalid",
            manifest={"data_eligibility": "REHEARSAL"},
            quality=_quality(),
            conflicts=(),
            candidate_run=FakeCandidateRun(),
            dividend_refresh={},
        )
