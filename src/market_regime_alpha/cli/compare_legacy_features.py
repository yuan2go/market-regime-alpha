"""Compare canonical technical observables with bounded lossy Legacy adapters."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import NoReturn, Sequence

from market_regime_alpha.cli._feature_output import (
    EXIT_ARGUMENT_ERROR,
    EXIT_CANONICAL_REGRESSION,
    EXIT_INPUT_TAMPERED,
    EXIT_IO_ERROR,
    EXIT_SUCCESS,
    emit,
    emit_error,
    load_feature_set,
    parse_symbols,
    read_canonical_object,
)
from market_regime_alpha.features import (
    FeatureMaterializationExecutionMode,
    FeatureMaterializationRunner,
    load_verified_feature_bundle_v2,
)
from market_regime_alpha.market_data import load_verified_market_data_dataset
from market_regime_alpha.migration.comparison import (
    TechnicalObservableComparisonPolicy,
    canonical_technical_comparison_policy,
    compare_technical_observables,
    publish_technical_comparison,
)


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        raise ValueError(message)


def build_parser() -> argparse.ArgumentParser:
    parser = _Parser(description=__doc__)
    parser.add_argument("--market-data-manifest", type=Path, required=True)
    parser.add_argument("--feature-set-config", type=Path, required=True)
    parser.add_argument("--comparison-policy", type=Path)
    parser.add_argument("--feature-id", action="append", required=True)
    parser.add_argument("--symbols", action="append", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--code-revision", required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    try:
        args = build_parser().parse_args(argv)
        symbols = parse_symbols(args.symbols)
        feature_set = load_feature_set(args.feature_set_config)
        requested = parse_symbols(args.feature_id)
        configured = {item.feature_id for item in feature_set.definitions}
        if not set(requested).issubset(configured):
            raise ValueError("requested Feature ID is not in Feature Set")
        dataset = load_verified_market_data_dataset(
            args.market_data_manifest.resolve(), symbols=symbols
        )
        policy = (
            TechnicalObservableComparisonPolicy.from_canonical_dict(
                read_canonical_object(args.comparison_policy, "Comparison Policy")
            )
            if args.comparison_policy is not None
            else canonical_technical_comparison_policy()
        )
        output_root = args.output_dir.resolve()
        receipt = FeatureMaterializationRunner(max_workers=1).run(
            verified_dataset=dataset,
            feature_set=feature_set,
            decision_time=dataset.artifact.decision_time,
            created_at=dataset.artifact.created_at,
            selected_symbols=symbols,
            code_revision=str(args.code_revision),
            output_root=output_root,
            idempotency_key=(
                f"legacy-comparison:{dataset.artifact.dataset_id}:"
                f"{feature_set.feature_set_id}"
            ),
            execution_mode=FeatureMaterializationExecutionMode.START_NEW,
        )
        bundle = load_verified_feature_bundle_v2(
            output_root / receipt.bundle_locator,
            artifact_root=output_root / "feature-artifacts",
        )
        reports = tuple(
            compare_technical_observables(
                verified_dataset=dataset,
                feature_bundle=bundle,
                symbol=symbol,
                policy=policy,
            )
            for symbol in symbols
        )
        paths = tuple(
            publish_technical_comparison(
                root=output_root / "technical-comparisons",
                report=report,
                policy=policy,
            )
            for report in reports
        )
    except (FileNotFoundError, PermissionError, OSError) as exc:
        emit_error(status="IO_ERROR", reason_code="LEGACY_COMPARISON_IO_ERROR", error=exc)
        return EXIT_IO_ERROR
    except (TypeError, ValueError) as exc:
        emit_error(status="REJECTED", reason_code="LEGACY_COMPARISON_INPUT_REJECTED", error=exc)
        return EXIT_INPUT_TAMPERED if "hash" in str(exc).lower() else EXIT_ARGUMENT_ERROR

    regression = any(item.canonical_regression for item in reports)
    emit(
        {
            "status": "CANONICAL_REGRESSION" if regression else "COMPARED",
            "run_id": str(receipt.receipt_id),
            "dataset_id": str(receipt.dataset_id),
            "feature_bundle_id": str(receipt.bundle_id),
            "feature_bundle_hash": receipt.bundle_hash,
            "comparison_classifications": {
                report.symbol: {
                    item.family.value: item.classification.value for item in report.items
                }
                for report in reports
            },
            "comparison_packages": [str(path) for path in paths],
            "requested_feature_ids": list(requested),
            "limitations": sorted(
                {limitation for report in reports for limitation in report.limitations}
            ),
        }
    )
    return EXIT_CANONICAL_REGRESSION if regression else EXIT_SUCCESS


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
