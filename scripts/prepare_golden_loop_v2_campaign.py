#!/usr/bin/env python3
"""Clone one immutable Phase E3 command into a Golden Loop V2 campaign."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
import json
from pathlib import Path
from typing import Any

from market_regime_alpha.application.historical_corpus.frozen_experiment import (
    create_golden_loop_v2_historical_experiment,
)
from market_regime_alpha.application.historical_corpus.golden_loop import (
    GoldenLoopScoringContract,
)
from market_regime_alpha.application.historical_corpus.postgres_evidence import (
    PostgresHistoricalEvidenceRepository,
)
from market_regime_alpha.application.historical_research.contracts import (
    HistoricalResearchCommand,
)
from market_regime_alpha.application.historical_research.postgres_journal import (
    PostgresHistoricalResearchJournal,
)
from market_regime_alpha.application.research_evaluation.postgres_target_repository import (
    PostgresTargetOutcomeRepository,
)
from market_regime_alpha.application.research_validation.common import (
    ValidationArtifactReference,
)
from market_regime_alpha.application.research_validation.postgres_repository import (
    PostgresResearchValidationRepository,
)
from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.persistence.postgres.connection import (
    PostgresConnectionFactory,
)
from market_regime_alpha.persistence.settings import DatabaseSettings


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database-url", required=True)
    parser.add_argument("--application-schema", required=True)
    parser.add_argument("--source-run-id", required=True)
    parser.add_argument("--code-revision", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--metadata-output", type=Path, required=True)
    parser.add_argument("--max-stage-commits", type=int, default=200)
    parser.add_argument(
        "--superseded-reference",
        action="append",
        default=[],
        metavar="KIND|ID|SHA256",
        help="Exact external V1 Evidence reference, repeatable.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.max_stage_commits <= 0:
        raise ValueError("--max-stage-commits must be positive")
    created_at = datetime.now(UTC).replace(microsecond=0)
    settings = DatabaseSettings.from_sources(
        database_url=args.database_url,
        application_schema=args.application_schema,
        environ={},
    )
    factory = PostgresConnectionFactory(
        settings,
        min_size=0,
        application_schema=args.application_schema,
    )
    try:
        source = PostgresHistoricalResearchJournal(
            factory,
        ).get_run(ArtifactId(args.source_run_id))
        target = PostgresTargetOutcomeRepository(
            factory,
            apply_migrations=False,
        ).get_protocol(source.command.target_protocol_reference.artifact_id)
        validation = PostgresResearchValidationRepository(
            factory,
            apply_migrations=False,
        )
        source_experiment = validation.get_historical_experiment_definition(
            source.command.experiment_definition_reference.artifact_id
        )
        economics = validation.get_historical_strategy_economics_policy_set(
            source_experiment.cost_policy_reference.artifact_id
        )
        experiment = create_golden_loop_v2_historical_experiment(
            target,
            locked_at=economics.created_at,
        )
        validation.record_historical_experiment_definition(
            experiment,
            recorded_at=created_at,
        )
        source_evidence = PostgresHistoricalEvidenceRepository(
            factory,
            apply_migrations=False,
        ).list_for_run(source.command.run_id)
        external = tuple(
            _reference_from_text(value) for value in args.superseded_reference
        )
        superseded = _references(
            (*tuple(item.reference for item in source_evidence), *external)
        )
        scoring = GoldenLoopScoringContract.create_v2()
        command = HistoricalResearchCommand.create(
            idempotency_key=(
                "wp-golden-loop-v2-"
                f"{source.command.command_hash[7:19]}-{args.code_revision[:12]}"
            ),
            start_date=source.command.start_date,
            end_date=source.command.end_date,
            trading_sessions=source.command.trading_sessions,
            decision_local_time=source.command.decision_local_time,
            timezone_name=source.command.timezone_name,
            trading_calendar_id=source.command.trading_calendar_id,
            trading_calendar_hash=source.command.trading_calendar_hash,
            runtime_scope_policy_id=source.command.runtime_scope_policy_id,
            runtime_scope_policy_hash=source.command.runtime_scope_policy_hash,
            decision_policy_id=source.command.decision_policy_id,
            decision_policy_hash=source.command.decision_policy_hash,
            target_protocol_reference=source.command.target_protocol_reference,
            experiment_definition_reference=ValidationArtifactReference(
                "RESEARCH_EXPERIMENT_DEFINITION",
                experiment.definition_id,
                experiment.definition_hash,
            ),
            configuration_references=_references(
                (
                    *source.command.configuration_references,
                    scoring.reference,
                    *superseded,
                )
            ),
            data_authority_mode=source.command.data_authority_mode,
            evidence_qualification=source.command.evidence_qualification,
            code_revision=args.code_revision,
            created_at=created_at,
        )
        _write_json(
            args.output,
            {
                "command": command.to_canonical_dict(),
                "max_stage_commits": args.max_stage_commits,
            },
        )
        metadata = {
            "schema_version": "golden-loop-v2-campaign-metadata/v1",
            "source_run_reference": {
                "artifact_kind": "HISTORICAL_RESEARCH_RUN",
                "artifact_id": str(source.command.run_id),
                "content_hash": source.command.command_hash,
            },
            "command": command.to_canonical_dict(),
            "experiment": experiment.to_canonical_dict(),
            "scoring_contract": scoring.to_canonical_dict(),
            "superseded_evidence_references": [
                item.to_canonical_dict() for item in superseded
            ],
            "methodology_change_only": True,
            "frozen_unchanged_inputs": {
                "target_references": [
                    item.to_canonical_dict() for item in experiment.target_references
                ],
                "feature_reference": experiment.feature_reference.to_canonical_dict(),
                "cost_policy_reference": experiment.cost_policy_reference.to_canonical_dict(),
                "decision_policy_id": str(command.decision_policy_id),
                "decision_policy_hash": command.decision_policy_hash,
                "trading_calendar_id": str(command.trading_calendar_id),
                "trading_calendar_hash": command.trading_calendar_hash,
                "runtime_scope_policy_id": str(command.runtime_scope_policy_id),
                "runtime_scope_policy_hash": command.runtime_scope_policy_hash,
            },
        }
        _write_json(args.metadata_output, metadata)
        print(
            json.dumps(
                {
                    "run_id": str(command.run_id),
                    "command_hash": command.command_hash,
                    "experiment_id": str(experiment.definition_id),
                    "experiment_hash": experiment.definition_hash,
                    "scoring_contract_hash": scoring.contract_hash,
                    "session_count": command.session_count,
                    "superseded_evidence_count": len(superseded),
                    "output": str(args.output.resolve()),
                    "metadata_output": str(args.metadata_output.resolve()),
                },
                sort_keys=True,
            )
        )
    finally:
        factory.close()
    return 0


def _reference_from_text(value: str) -> ValidationArtifactReference:
    parts = value.split("|", 2)
    if len(parts) != 3:
        raise ValueError("superseded reference must be KIND|ID|SHA256")
    return ValidationArtifactReference(
        artifact_kind=parts[0],
        artifact_id=ArtifactId(parts[1]),
        content_hash=parts[2],
    )


def _references(
    values: tuple[ValidationArtifactReference, ...],
) -> tuple[ValidationArtifactReference, ...]:
    keyed = {
        (item.artifact_kind, str(item.artifact_id), item.content_hash): item
        for item in values
    }
    return tuple(keyed[key] for key in sorted(keyed))


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    raise SystemExit(main())
