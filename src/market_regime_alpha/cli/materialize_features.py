"""Materialize a verified canonical Feature Bundle without execution authority."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import NoReturn, Sequence

from market_regime_alpha.cli._feature_output import (
    EXIT_ARGUMENT_ERROR,
    EXIT_COMPUTATION_FAILED,
    EXIT_DATA_INSUFFICIENT,
    EXIT_INPUT_TAMPERED,
    EXIT_IO_ERROR,
    EXIT_PARTIAL_COVERAGE,
    EXIT_SUCCESS,
    emit,
    emit_error,
    load_feature_set,
    parse_symbols,
    require_decision_scope,
)
from market_regime_alpha.features import (
    FeatureConfigurationInvalidError,
    FeatureComputationFailedError,
    FeatureMaterializationExecutionMode,
    FeatureMaterializationRunner,
    FeatureMaterializationStatus,
)
from market_regime_alpha.market_data import load_verified_market_data_dataset


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        raise ValueError(message)


def build_parser() -> argparse.ArgumentParser:
    parser = _Parser(description=__doc__)
    parser.add_argument("--market-data-manifest", type=Path, required=True)
    parser.add_argument("--feature-set-config", type=Path, required=True)
    parser.add_argument("--decision-date", required=True)
    parser.add_argument("--as-of", required=True)
    parser.add_argument("--symbols", action="append", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--idempotency-key", required=True)
    parser.add_argument("--code-revision", required=True)
    parser.add_argument("--max-workers", type=int, default=1)
    parser.add_argument(
        "--execution-mode",
        choices=[item.value for item in FeatureMaterializationExecutionMode],
        default=FeatureMaterializationExecutionMode.START_NEW.value,
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    try:
        args = build_parser().parse_args(argv)
        _, decision_time = require_decision_scope(
            decision_date=str(args.decision_date), as_of=str(args.as_of)
        )
        selected_symbols = parse_symbols(args.symbols)
        dataset = load_verified_market_data_dataset(
            args.market_data_manifest.resolve(), symbols=selected_symbols
        )
        if dataset.artifact.decision_time != decision_time:
            raise ValueError("Market Data Dataset DecisionTime differs from --as-of")
        feature_set = load_feature_set(args.feature_set_config)
        receipt = FeatureMaterializationRunner(max_workers=args.max_workers).run(
            verified_dataset=dataset,
            feature_set=feature_set,
            decision_time=decision_time,
            created_at=dataset.artifact.created_at,
            selected_symbols=selected_symbols,
            code_revision=str(args.code_revision),
            output_root=args.output_dir.resolve(),
            idempotency_key=str(args.idempotency_key),
            execution_mode=FeatureMaterializationExecutionMode(
                str(args.execution_mode)
            ),
        )
    except (FileNotFoundError, PermissionError, OSError) as exc:
        emit_error(status="IO_ERROR", reason_code="FEATURE_IO_ERROR", error=exc)
        return EXIT_IO_ERROR
    except FeatureConfigurationInvalidError as exc:
        emit_error(
            status="CONFIGURATION_INVALID",
            reason_code="FEATURE_CONFIGURATION_INVALID",
            error=exc,
        )
        return EXIT_ARGUMENT_ERROR
    except FeatureComputationFailedError as exc:
        emit_error(
            status="COMPUTATION_FAILED",
            reason_code="FEATURE_COMPUTATION_FAILED",
            error=exc,
        )
        return EXIT_COMPUTATION_FAILED
    except ValueError as exc:
        reason = (
            "FEATURE_INPUT_TAMPERED"
            if any(token in str(exc).lower() for token in ("checksum", "hash mismatch", "identity"))
            else "FEATURE_COMMAND_INVALID"
        )
        emit_error(status="REJECTED", reason_code=reason, error=exc)
        return EXIT_INPUT_TAMPERED if reason == "FEATURE_INPUT_TAMPERED" else EXIT_ARGUMENT_ERROR
    except Exception as exc:  # pragma: no cover - defensive CLI boundary
        emit_error(status="COMPUTATION_FAILED", reason_code="FEATURE_COMPUTATION_FAILED", error=exc)
        return EXIT_COMPUTATION_FAILED

    emit(
        {
            "status": receipt.status.value,
            "run_id": str(receipt.receipt_id),
            "dataset_id": str(receipt.dataset_id),
            "feature_bundle_id": str(receipt.bundle_id),
            "feature_bundle_hash": receipt.bundle_hash,
            "coverage": {
                "artifact_count": receipt.artifact_count,
                "available_value_count": receipt.available_value_count,
            },
            "missingness": {"missing_value_count": receipt.missing_value_count},
            "limitations": list(receipt.limitations),
        }
    )
    return (
        EXIT_DATA_INSUFFICIENT
        if receipt.status is FeatureMaterializationStatus.BLOCKED_REQUIRED_FEATURE
        else EXIT_PARTIAL_COVERAGE
        if receipt.status is FeatureMaterializationStatus.PARTIAL_COVERAGE
        else EXIT_SUCCESS
    )


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
