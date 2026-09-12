"""Research declarations over the existing canonical execution entry points."""

import argparse
from pathlib import Path

from market_regime_alpha.bootstrap import TargetSettings, bootstrap_application, database_identity
from market_regime_alpha.interfaces.archive import require_isolated_operational_target
from market_regime_alpha.interfaces.historical_study import prepare_study
from market_regime_alpha.research_qualification.domain.historical_study import HistoricalStudyPlan


def add_research_parser(areas) -> None:
    research = areas.add_parser("research")
    commands = research.add_subparsers(dest="research_command", required=True)
    prepare = commands.add_parser("prepare-historical")
    for name in ("plan", "wheel", "lockfile", "output"):
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
    plan = HistoricalStudyPlan.from_bytes(arguments.plan.read_bytes())
    with bootstrap_application(settings) as app:
        return prepare_study(app, plan, wheel=arguments.wheel, lockfile=arguments.lockfile,
            code_sha=arguments.code_sha, output=arguments.output, actor_id=arguments.actor_id)
