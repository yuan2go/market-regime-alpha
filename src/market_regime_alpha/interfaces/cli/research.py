"""Research declarations over the existing canonical execution entry points."""

import argparse
from datetime import date
import json
from pathlib import Path
from uuid import UUID

from market_regime_alpha.bootstrap import TargetSettings, bootstrap_application, database_identity
from market_regime_alpha.interfaces.archive import require_isolated_operational_target
from market_regime_alpha.interfaces.historical_study import prepare_study
from market_regime_alpha.research_qualification.domain.historical_study import HistoricalStudyPlan


def add_historical_parser(commands) -> None:
    from market_regime_alpha.interfaces.cli.holdout import add_holdout_parsers
    add_holdout_parsers(commands)
    recorded=commands.add_parser("provider-recording-check")
    recorded.add_argument("--contract",required=True,type=Path)
    recorded.add_argument("--recording",required=True,type=Path)
    recorded.add_argument("--expected-sha256",required=True)
    recorded.add_argument("--normalization-evidence",type=Path,help="Exact mapping evidence embedded in a new v3 Capture; required for Market normalization")
    recorded.add_argument("--expected-database-name",required=True)
    recorded.add_argument("--expected-database-oid",required=True,type=int)
    recorded.add_argument("--capture-product-id",type=UUID)
    recorded.add_argument("--capture-key")
    recorded.add_argument("--actor-id",default="historical-research-operator")
    replay=commands.add_parser("provider-recording-replay")
    replay.add_argument("--capture-id",required=True,type=UUID)
    replay.add_argument("--expected-database-name",required=True)
    replay.add_argument("--expected-database-oid",required=True,type=int)
    normalize=commands.add_parser("provider-recording-normalize")
    normalize.add_argument("--capture-id",required=True,type=UUID)
    normalize.add_argument("--expected-database-name",required=True)
    normalize.add_argument("--expected-database-oid",required=True,type=int)
    normalize.add_argument("--idempotency-key",required=True)
    normalize.add_argument("--actor-id",required=True)
    recorded_archive=commands.add_parser("prepare-recorded-archive")
    recorded_archive.add_argument("--recording-capture-id",required=True,type=UUID)
    recorded_archive.add_argument("--reference-capture-id",required=True,type=UUID,action="append")
    recorded_archive.add_argument("--archive-code",required=True)
    for name in ("wheel","lockfile","source-checkout","output"):
        recorded_archive.add_argument("--"+name,required=True,type=Path)
    recorded_archive.add_argument("--code-sha",required=True)
    recorded_archive.add_argument("--reserved-free-bytes",type=int,default=1_073_741_824)
    recorded_archive.add_argument("--maximum-slice-bytes",type=int,default=134_000_000)
    recorded_archive.add_argument("--maximum-archive-bytes",type=int,default=1_072_000_000)
    recorded_archive.add_argument("--expected-database-name",required=True)
    recorded_archive.add_argument("--expected-database-oid",required=True,type=int)
    recorded_archive.add_argument("--actor-id",required=True)
    source=commands.add_parser("source-compare")
    for name in ("left-run-id", "right-run-id"):
        source.add_argument("--"+name,required=True,type=UUID)
    for name in ("left-arm", "right-arm"):
        source.add_argument("--"+name,required=True)
    for name in ("start-date", "end-date"):
        source.add_argument("--"+name,required=True,type=date.fromisoformat)
    source.add_argument("--mode",required=True,choices=("FIXED_MODEL_REPLAY","FIXED_PROTOCOL_RETRAIN","FIXED_DATA_MODELS"))
    source.add_argument("--expected-database-name",required=True)
    source.add_argument("--expected-database-oid",required=True,type=int)
    comparison=commands.add_parser("history-compare")
    comparison.add_argument("--run-id",required=True,type=UUID)
    comparison.add_argument("--expected-database-name",required=True)
    comparison.add_argument("--expected-database-oid",required=True,type=int)
    comparison.add_argument("--projection-version",type=int,choices=(3,),help="Opt in to independent IC summaries; omission preserves original v1/v2 projection bytes")
    comparison.add_argument("--publish",action="store_true")
    comparison.add_argument("--actor-id",default="historical-research-operator")
    inventory = commands.add_parser("history-inventory")
    inventory.add_argument("--archive-id", required=True, type=UUID)
    inventory.add_argument("--seal-id", required=True, type=UUID)
    inventory.add_argument("--expected-database-name", required=True)
    inventory.add_argument("--expected-database-oid", required=True, type=int)
    for command in ("prepare-historical", "prepare-history-data"):
        prepare = commands.add_parser(command)
        for name in ("plan", "wheel", "lockfile", "source-checkout", "output"):
            prepare.add_argument("--" + name, required=True, type=Path)
        prepare.add_argument("--code-sha", required=True)
        prepare.add_argument("--expected-database-name", required=True)
        prepare.add_argument("--expected-database-oid", required=True, type=int)
        prepare.add_argument("--actor-id", required=True)
        if command == "prepare-historical":
            prepare.add_argument("--reuse-contracts-from", type=UUID)
            prepare.add_argument("--source-contracts-from", type=UUID,help="Reuse exact Target/Feature/protocol on a distinct sealed source; new training, never fresh holdout")


def execute_research(settings: TargetSettings, arguments: argparse.Namespace) -> object:
    require_isolated_operational_target(settings, expected_database_name=arguments.expected_database_name)
    identity = database_identity(settings)
    if identity.database_oid != arguments.expected_database_oid:
        raise ValueError("research database OID differs from operator intent")
    with bootstrap_application(settings) as app:
        if arguments.research_command=="prepare-recorded-archive":
            from market_regime_alpha.interfaces.professional_archive import prepare_recorded_archive
            return prepare_recorded_archive(app,settings,arguments)
        if arguments.research_command=="provider-recording-normalize":
            from market_regime_alpha.interfaces.professional_normalization import normalize_recorded_capture
            return normalize_recorded_capture(app,settings,arguments)
        if arguments.research_command=="provider-recording-replay":
            from market_regime_alpha.infrastructure.postgres.queries.professional_recording import replay_recorded_capture
            from market_regime_alpha.infrastructure.artifacts.local import LocalArtifactStore
            return replay_recorded_capture(app._pool,LocalArtifactStore(settings.artifact_root),arguments.capture_id)
        if arguments.research_command=="provider-recording-check":
            from market_regime_alpha.market.domain.professional_daily import ProfessionalDailyContract
            from market_regime_alpha.infrastructure.recorded_professional_provider import RecordedProfessionalMarketProvider
            from market_regime_alpha.market.ports.provider import CaptureRequest
            from market_regime_alpha.runtime.application import CommandContext, ActorType
            if arguments.contract.stat().st_size>100_000:
                raise ValueError("professional contract exceeds byte budget")
            contract=ProfessionalDailyContract.from_bytes(arguments.contract.read_bytes())
            if arguments.recording.stat().st_size>contract.maximum_bytes:
                raise ValueError("professional recording exceeds frozen byte budget")
            mapping = None
            if arguments.normalization_evidence is not None:
                if arguments.normalization_evidence.stat().st_size>100_000:
                    raise ValueError("professional normalization evidence exceeds byte budget")
                mapping=arguments.normalization_evidence.read_bytes()
            provider=RecordedProfessionalMarketProvider(contract,arguments.recording.read_bytes(),expected_sha256=arguments.expected_sha256,
                normalization_evidence=mapping)
            result=dict(provider.verification)
            if arguments.capture_product_id is not None:
                if not arguments.capture_key:
                    raise ValueError("canonical recorded capture requires an explicit capture key")
                from market_regime_alpha.shared.hashing import canonical_json_sha256
                from market_regime_alpha.shared.identity import ContentHash
                captured=app.market.capture(CaptureRequest(arguments.capture_product_id,arguments.capture_key,
                    provider.resource,ContentHash(canonical_json_sha256({}))),provider,
                    CommandContext(arguments.capture_key,ActorType.OPERATOR,arguments.actor_id,"LOCAL_RECORDED_PROVIDER_CONTRACT"))
                result["capture_id"]=captured.capture.capture_id
            elif arguments.capture_key:
                raise ValueError("capture key requires the exact original Provider product")
            return result
        if arguments.research_command.startswith("holdout-"):
            from market_regime_alpha.interfaces.cli.holdout import execute_holdout
            return execute_holdout(app, arguments)
        if arguments.research_command=="source-compare":
            return app.historical_comparison.compare_sources(left_run_id=arguments.left_run_id,right_run_id=arguments.right_run_id,
                left_arm=arguments.left_arm,right_arm=arguments.right_arm,start_date=arguments.start_date,end_date=arguments.end_date,mode=arguments.mode)
        if arguments.research_command=="history-compare":
            payload=(app.historical_comparison.project(arguments.run_id) if arguments.projection_version is None else
                app.historical_comparison.project(arguments.run_id,projection_version=arguments.projection_version))
            if arguments.publish:
                from market_regime_alpha.interfaces.historical_study import _json
                from market_regime_alpha.runtime.application import CommandContext, ActorType
                artifact=app.artifacts.publish(_json(payload),media_type="application/json",context=CommandContext(
                    "historical-comparison:"+str(payload["projection_sha256"]),ActorType.OPERATOR,arguments.actor_id,"HISTORICAL_COMPARISON"))
                return {"projection":payload,"artifact_id":artifact.artifact_id,"content_sha256":artifact.content_sha256,"size_bytes":artifact.size_bytes}
            return payload
        if arguments.research_command == "history-inventory":
            return app.historical_inventory.inspect(arguments.archive_id, arguments.seal_id)
        if arguments.research_command == "prepare-history-data":
            from market_regime_alpha.market.domain.historical_acquisition import HistoricalAcquisitionPlan
            from market_regime_alpha.interfaces.historical_acquisition import prepare_historical_archive
            return prepare_historical_archive(app, HistoricalAcquisitionPlan.from_bytes(arguments.plan.read_bytes()),
                wheel=arguments.wheel, lockfile=arguments.lockfile, source_checkout=arguments.source_checkout,
                code_sha=arguments.code_sha, output=arguments.output, actor_id=arguments.actor_id)
        content=arguments.plan.read_bytes()
        root=json.loads(content)
        if isinstance(root,dict) and root.get("schema")=="mra-historical-rolling-v2":
            from market_regime_alpha.research_qualification.domain.historical_rolling import HistoricalRollingPlan
            rolling = HistoricalRollingPlan.from_bytes(content)
            return prepare_study(app,rolling.baseline,wheel=arguments.wheel,lockfile=arguments.lockfile,
                source_checkout=arguments.source_checkout,code_sha=arguments.code_sha,output=arguments.output,actor_id=arguments.actor_id,matrix=rolling,
                reuse_contracts_from=arguments.reuse_contracts_from,source_contracts_from=arguments.source_contracts_from)
        if arguments.source_contracts_from is not None:
            raise ValueError("source contrast preparation requires the distinct rolling v2 contract")
        if isinstance(root,dict) and root.get("schema")=="mra-historical-matrix-v1":
            from market_regime_alpha.research_qualification.domain.historical_matrix import HistoricalMatrixPlan
            matrix=HistoricalMatrixPlan.from_bytes(content)
            return prepare_study(app,matrix.baseline,wheel=arguments.wheel,lockfile=arguments.lockfile,
                source_checkout=arguments.source_checkout,code_sha=arguments.code_sha,output=arguments.output,actor_id=arguments.actor_id,matrix=matrix,
                reuse_contracts_from=arguments.reuse_contracts_from)
        plan = HistoricalStudyPlan.from_bytes(content)
        if arguments.reuse_contracts_from is not None:
            raise ValueError("contract reuse requires a historical matrix")
        return prepare_study(app, plan, wheel=arguments.wheel, lockfile=arguments.lockfile,
            source_checkout=arguments.source_checkout, code_sha=arguments.code_sha, output=arguments.output, actor_id=arguments.actor_id)
