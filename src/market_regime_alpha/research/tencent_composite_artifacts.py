"""Atomic, non-overwriting evidence artifacts for Tencent composite runs."""

from __future__ import annotations

from dataclasses import fields, is_dataclass
from datetime import date, datetime
from enum import Enum
import json
from pathlib import Path
import shutil
from typing import Any, Mapping, Protocol

from market_regime_alpha.core.identity import StableId
from market_regime_alpha.core.time import SemanticTime
from market_regime_alpha.research.tencent_composite_contracts import CompositeQualityReport


OUTPUT_FILENAMES = (
    "manifest.json",
    "quality.json",
    "source_conflicts.json",
    "candidate_panel_summary.json",
    "b0_b1_evaluation.json",
    "candidate_report.md",
    "dividend_t_refresh.json",
)


class CandidateRunSummary(Protocol):
    def panel_summary(self) -> dict[str, object]: ...

    def evaluation_summary(self) -> dict[str, object]: ...


def write_tencent_composite_run(
    *,
    root: str | Path,
    run_id: str,
    manifest: Mapping[str, Any],
    quality: CompositeQualityReport,
    conflicts: tuple[Any, ...],
    candidate_run: CandidateRunSummary,
    dividend_refresh: Any,
) -> Path:
    """Write the exact evidence set to a staged directory, then rename atomically."""

    if not run_id or run_id != run_id.strip() or Path(run_id).name != run_id:
        raise ValueError("run_id must be one non-empty path-safe name")
    eligibility = manifest.get("data_eligibility")
    if isinstance(eligibility, Enum):
        eligibility = eligibility.value
    if eligibility != "EXPLORATORY":
        raise ValueError("Tencent composite run manifest must remain EXPLORATORY")

    root_path = Path(root)
    final = root_path / run_id
    stage = root_path / f".{run_id}.staging"
    if final.exists():
        raise FileExistsError(f"run already exists: {final}")
    if stage.exists():
        raise FileExistsError(f"staging run already exists: {stage}")
    stage.mkdir(parents=True)
    try:
        panel_summary = candidate_run.panel_summary()
        evaluation_summary = candidate_run.evaluation_summary()
        _write_json(stage / "manifest.json", manifest)
        _write_json(stage / "quality.json", quality)
        _write_json(stage / "source_conflicts.json", conflicts)
        _write_json(stage / "candidate_panel_summary.json", panel_summary)
        _write_json(stage / "b0_b1_evaluation.json", evaluation_summary)
        (stage / "candidate_report.md").write_text(
            render_candidate_report(
                manifest=manifest,
                quality=quality,
                panel_summary=panel_summary,
                evaluation_summary=evaluation_summary,
            ),
            encoding="utf-8",
        )
        _write_json(stage / "dividend_t_refresh.json", dividend_refresh)
        if {path.name for path in stage.iterdir()} != set(OUTPUT_FILENAMES):
            raise RuntimeError("Tencent composite staging artifact set is incomplete")
        stage.rename(final)
    except Exception:
        shutil.rmtree(stage, ignore_errors=True)
        raise
    return final


def write_tencent_composite_quality_failure(
    *,
    root: str | Path,
    run_id: str,
    manifest: Mapping[str, Any],
    quality: CompositeQualityReport,
) -> Path:
    """Persist a non-overwriting failed quality decision for diagnosis."""

    if manifest.get("data_eligibility") != "EXPLORATORY":
        raise ValueError("Tencent composite failure manifest must remain EXPLORATORY")
    root_path = Path(root)
    final = root_path / run_id
    stage = root_path / f".{run_id}.staging"
    if final.exists() or stage.exists():
        raise FileExistsError(f"failed run artifact already exists: {final}")
    stage.mkdir(parents=True)
    try:
        _write_json(stage / "manifest.json", manifest)
        _write_json(stage / "quality.json", quality)
        (stage / "FAILURE.txt").write_text(
            "Tencent composite quality gate failed; no Candidate or dividend-T run was executed.\n",
            encoding="utf-8",
        )
        stage.rename(final)
    except Exception:
        shutil.rmtree(stage, ignore_errors=True)
        raise
    return final


def render_candidate_report(
    *,
    manifest: Mapping[str, Any],
    quality: CompositeQualityReport,
    panel_summary: Mapping[str, Any],
    evaluation_summary: Mapping[str, Any],
) -> str:
    """Render audit facts before descriptive model metrics."""

    rejected = tuple(
        disposition
        for disposition in quality.dispositions
        if disposition.symbol not in set(quality.accepted_symbols)
    )
    first_date = quality.common_session_dates[0].isoformat() if quality.common_session_dates else "n/a"
    last_date = quality.common_session_dates[-1].isoformat() if quality.common_session_dates else "n/a"
    limitations = manifest.get("limitations", ())
    if not isinstance(limitations, (tuple, list)):
        limitations = (str(limitations),)
    conflict_count = manifest.get("source_conflict_count", "unknown")
    lines = [
        "# Tencent Composite Exploratory Candidate Report",
        "",
        "## Population and data coverage",
        "",
        f"- Accepted symbols: {len(quality.accepted_symbols)}/{len(quality.requested_symbols)}",
        f"- Accepted list: {', '.join(quality.accepted_symbols) or 'none'}",
        f"- Rejected list: {', '.join(item.symbol for item in rejected) or 'none'}",
        f"- Common complete sessions: {len(quality.common_session_dates)}",
        f"- Common date range: {first_date} to {last_date}",
        f"- Decision dates evaluated: {panel_summary.get('decision_date_count', 'unknown')}",
        "",
        "## Authority and limitations",
        "",
        f"- Data eligibility: {manifest.get('data_eligibility', 'unknown')}",
        "- Canonical provider authority: unchanged; Xuntou remains primary.",
        "- This report is descriptive exploratory evidence, not an Alpha claim.",
        *[f"- Limitation: {item}" for item in limitations],
        "",
        "## Source conflicts",
        "",
        f"- Retained conflicts: {conflict_count}",
        "- Conflict details are preserved in `source_conflicts.json`.",
        "",
        "## Model metrics",
        "",
        "- Selection policy: "
        f"{evaluation_summary.get('selection_policy', 'FIXED_UNTUNED_NO_WINNER_SELECTION')}",
        "- Full metrics are preserved in `b0_b1_evaluation.json`.",
        "",
    ]
    return "\n".join(lines)


def _write_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(
            _json_value(value),
            ensure_ascii=False,
            sort_keys=True,
            indent=2,
            allow_nan=False,
        )
        + "\n",
        encoding="utf-8",
    )


def _json_value(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, StableId):
        return str(value)
    if isinstance(value, SemanticTime):
        return value.isoformat()
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Path):
        return str(value)
    if is_dataclass(value) and not isinstance(value, type):
        return {
            field.name: _json_value(getattr(value, field.name))
            for field in fields(value)
        }
    if isinstance(value, Mapping):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (tuple, list, set)):
        return [_json_value(item) for item in value]
    return value
