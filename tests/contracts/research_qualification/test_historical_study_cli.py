from pathlib import Path

from market_regime_alpha.interfaces.cli.main import _parser, _dispatch


def test_historical_entry_extends_existing_research_root_and_dispatches(monkeypatch):
    parser = _parser()
    args = parser.parse_args(["research", "prepare-historical", "--plan", "plan.json", "--wheel", "code.whl", "--lockfile", "uv.lock",
        "--source-checkout", "checkout", "--output", "persistent", "--code-sha", "a" * 40, "--expected-database-name", "study", "--expected-database-oid", "32", "--actor-id", "researcher"])
    called = []
    def prepare(settings, arguments):
        called.append(arguments.plan)
        return {"state": "DISPATCH_TEST_ONLY"}
    monkeypatch.setattr("market_regime_alpha.interfaces.cli.research.execute_research", prepare)
    assert _dispatch(args, None) == {"state": "DISPATCH_TEST_ONLY"}
    assert called == [Path("plan.json")]
    assert parser.parse_args(["research", "daily", "backlog"]).daily_command == "backlog"
    assert parser.parse_args(["research", "validity", "daily"]).validity_command == "daily"
    assert parser.parse_args(["db", "verify"]).db_command == "verify"
