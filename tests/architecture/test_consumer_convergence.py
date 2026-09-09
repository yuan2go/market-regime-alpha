from pathlib import Path
import tomllib


ROOT = Path(__file__).resolve().parents[2]


def test_installed_commands_have_one_research_entry_and_explicit_account_governance_owners() -> None:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text())
    assert project["project"]["scripts"] == {
        "mra": "market_regime_alpha.interfaces.cli:main",
        "decision-system": "market_regime_alpha.cli.decision_system:main",
        "model-governance": "market_regime_alpha.cli.model_governance:main",
        "pit-authority": "market_regime_alpha.cli.pit_authority:main",
    }


def test_canonical_research_composition_does_not_reach_retired_research_authorities() -> None:
    from scripts.repository_inventory import inventory

    snapshot = inventory(ROOT)
    graph = snapshot["consumer_graph"]
    canonical = graph["src/market_regime_alpha/interfaces/cli/__init__.py"]
    assert canonical["legacy_persistence_dependencies"] == []
    assert not any(
        part in path
        for path in canonical["reachable_modules"]
        for part in ("/research/", "/platform/", "/application/historical_corpus/")
    )
    assert "src/market_regime_alpha/bootstrap.py" in canonical["reachable_modules"]
    assert canonical["canonical_postgres_dependencies"]
    assert snapshot["unresolved_internal_modules"] == {}


def test_all_executable_roots_have_explicit_dispositions_and_no_empty_migration_globs() -> None:
    from scripts.repository_inventory import CONSUMER_DISPOSITIONS, inventory

    graph = inventory(ROOT)["consumer_graph"]
    assert set(graph) == set(CONSUMER_DISPOSITIONS)
    for row in graph.values():
        assert row["disposition"] in {"RETAIN", "MIGRATE", "MERGE", "ARCHIVE", "DELETE"}
        assert all(row[key] for key in ("owner", "scope", "reason"))
    project = tomllib.loads((ROOT / "pyproject.toml").read_text())
    for patterns in project["tool"]["setuptools"]["package-data"].values():
        for pattern in patterns:
            assert list((ROOT / "src/market_regime_alpha").glob(pattern)), pattern


def test_retained_account_migrations_and_source_bound_historical_tool_keep_exact_bytes() -> None:
    from hashlib import sha256
    import json

    migrations = {
        path.relative_to(ROOT).as_posix(): sha256(path.read_bytes()).hexdigest()
        for path in sorted((ROOT / "src/market_regime_alpha/persistence/postgres/migrations").glob("*.sql"))
    }
    assert len(migrations) == 106
    assert sha256(json.dumps(migrations, sort_keys=True, separators=(",", ":")).encode()).hexdigest() == (
        "cdba77bdde1d95bf2f0783c52c100e57d0956e9088efe90424301410b32b9b65"
    )
    pinned = ROOT / "scripts/run_mr2b_f2a_conditionality_inputs.py"
    assert sha256(pinned.read_bytes()).hexdigest() == "802c3739fa83013372c78d536565dd70a6bca1eb54368f9104d5e5a0c54af5b7"
