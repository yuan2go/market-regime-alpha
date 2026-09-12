"""Research declarations over the existing canonical execution entry points."""

import argparse
import json
from pathlib import Path
from uuid import UUID

from market_regime_alpha.bootstrap import TargetSettings, bootstrap_application, database_identity
from market_regime_alpha.interfaces.archive import require_isolated_operational_target
from market_regime_alpha.interfaces.historical_study import prepare_study
from market_regime_alpha.research_qualification.domain.historical_study import HistoricalStudyPlan


def add_historical_parser(commands) -> None:
    comparison=commands.add_parser("history-compare")
    comparison.add_argument("--run-id",required=True,type=UUID)
    comparison.add_argument("--expected-database-name",required=True)
    comparison.add_argument("--expected-database-oid",required=True,type=int)
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


def execute_research(settings: TargetSettings, arguments: argparse.Namespace) -> object:
    require_isolated_operational_target(settings, expected_database_name=arguments.expected_database_name)
    identity = database_identity(settings)
    if identity.database_oid != arguments.expected_database_oid:
        raise ValueError("research database OID differs from operator intent")
    with bootstrap_application(settings) as app:
        if arguments.research_command=="history-compare":
            payload=app.historical_comparison.project(arguments.run_id)
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
        if isinstance(root,dict) and root.get("schema")=="mra-historical-matrix-v1":
            from market_regime_alpha.research_qualification.domain.historical_matrix import HistoricalMatrixPlan
            matrix=HistoricalMatrixPlan.from_bytes(content)
            return prepare_study(app,matrix.baseline,wheel=arguments.wheel,lockfile=arguments.lockfile,
                source_checkout=arguments.source_checkout,code_sha=arguments.code_sha,output=arguments.output,actor_id=arguments.actor_id,matrix=matrix)
        plan = HistoricalStudyPlan.from_bytes(content)
        return prepare_study(app, plan, wheel=arguments.wheel, lockfile=arguments.lockfile,
            source_checkout=arguments.source_checkout, code_sha=arguments.code_sha, output=arguments.output, actor_id=arguments.actor_id)
