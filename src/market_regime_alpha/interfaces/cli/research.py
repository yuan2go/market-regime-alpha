"""Research declarations over the existing canonical execution entry points."""

import argparse
from pathlib import Path
from uuid import UUID

from market_regime_alpha.bootstrap import TargetSettings, bootstrap_application, database_identity
from market_regime_alpha.interfaces.archive import require_isolated_operational_target
from market_regime_alpha.interfaces.historical_study import prepare_study
from market_regime_alpha.research_qualification.domain.historical_study import HistoricalStudyPlan


def add_historical_parser(commands) -> None:
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
        if arguments.research_command == "history-inventory":
            return app.historical_inventory.inspect(arguments.archive_id, arguments.seal_id)
        if arguments.research_command == "prepare-history-data":
            from market_regime_alpha.market.domain.historical_acquisition import HistoricalAcquisitionPlan
            from market_regime_alpha.interfaces.historical_acquisition import prepare_historical_archive
            return prepare_historical_archive(app, HistoricalAcquisitionPlan.from_bytes(arguments.plan.read_bytes()),
                wheel=arguments.wheel, lockfile=arguments.lockfile, source_checkout=arguments.source_checkout,
                code_sha=arguments.code_sha, output=arguments.output, actor_id=arguments.actor_id)
        plan = HistoricalStudyPlan.from_bytes(arguments.plan.read_bytes())
        return prepare_study(app, plan, wheel=arguments.wheel, lockfile=arguments.lockfile,
            source_checkout=arguments.source_checkout, code_sha=arguments.code_sha, output=arguments.output, actor_id=arguments.actor_id)
