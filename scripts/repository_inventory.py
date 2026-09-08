"""Regenerable source and test index; static references are not reachability proof."""

from __future__ import annotations

import argparse
import ast
from collections import defaultdict
from hashlib import sha256
from importlib.util import resolve_name
import json
from pathlib import Path
import re
import tomllib
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = Path("docs/architecture/code-inventory.json")
_SQL = re.compile(r"\b(FROM|JOIN|INSERT\s+INTO|UPDATE|DELETE\s+FROM)\s+(?:mra\.)?([a-z][a-z0-9_]+)", re.I)
_TABLE = re.compile(r"\bCREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?(?:mra\.)?([a-z][a-z0-9_]+)", re.I)

# Maintenance dispositions are reviewed metadata, never business routing or an admission registry.
CONSUMER_DISPOSITIONS = {
    'docs/operations/templates/refresh_backup.py': ('RETAIN', 'Canonical evidence / prospective CLI', 'DEPLOYMENT', 'Calls canonical mra inspection/backup/serve; supervisor lifecycle is not business scheduling authority.'),
    'docs/operations/templates/verify_prospective_artifacts.py': ('RETAIN', 'Canonical evidence / prospective CLI', 'DEPLOYMENT', 'Calls canonical mra inspection/backup/serve; supervisor lifecycle is not business scheduling authority.'),
    'historical_tools/analyze_capture_bias_stability.py': ('ARCHIVE', 'Capture bias historical analysis', 'HISTORICAL_TOOL', 'Moved from scripts without byte changes; uninstalled and undeployed; fixed protocol/Artifact identities are not current research authority.'),
    'historical_tools/benchmark_feature_materialization.py': ('ARCHIVE', 'Historical Feature benchmark', 'HISTORICAL_TOOL', 'Moved from scripts without byte changes; uninstalled and undeployed; fixed protocol/Artifact identities are not current research authority.'),
    'historical_tools/build_composite_operational_manifest.py': ('ARCHIVE', 'Historical composite manifest', 'HISTORICAL_TOOL', 'Moved from scripts without byte changes; uninstalled and undeployed; fixed protocol/Artifact identities are not current research authority.'),
    'historical_tools/cosco_timing_report.py': ('ARCHIVE', 'Historical timing Artifact', 'HISTORICAL_TOOL', 'Moved from scripts without byte changes; uninstalled and undeployed; fixed protocol/Artifact identities are not current research authority.'),
    'historical_tools/prepare_golden_loop_v2_campaign.py': ('ARCHIVE', 'Historical protocol preparation', 'HISTORICAL_TOOL', 'Moved from scripts without byte changes; uninstalled and undeployed; fixed protocol/Artifact identities are not current research authority.'),
    'historical_tools/run_mr1_overnight_morning_pop_validation.py': ('ARCHIVE', 'Historical overnight-morning protocol', 'HISTORICAL_TOOL', 'Moved from scripts without byte changes; uninstalled and undeployed; fixed protocol/Artifact identities are not current research authority.'),
    'historical_tools/run_mr2_morning_pop_failure_decomposition.py': ('ARCHIVE', 'Historical failure decomposition', 'HISTORICAL_TOOL', 'Moved from scripts without byte changes; uninstalled and undeployed; fixed protocol/Artifact identities are not current research authority.'),
    'historical_tools/run_mr2a_leak_free_regime.py': ('ARCHIVE', 'Historical regime protocol', 'HISTORICAL_TOOL', 'Moved from scripts without byte changes; uninstalled and undeployed; fixed protocol/Artifact identities are not current research authority.'),
    'historical_tools/run_mr2b_f2b_statistical_closure.py': ('ARCHIVE', 'Historical statistical closure', 'HISTORICAL_TOOL', 'Moved from scripts without byte changes; uninstalled and undeployed; fixed protocol/Artifact identities are not current research authority.'),
    'historical_tools/run_mr2b_f2b_v2_statistical_closure.py': ('ARCHIVE', 'Historical statistical closure', 'HISTORICAL_TOOL', 'Moved from scripts without byte changes; uninstalled and undeployed; fixed protocol/Artifact identities are not current research authority.'),
    'historical_tools/run_mr2b_f2b_v3_statistical_closure.py': ('ARCHIVE', 'Historical statistical closure', 'HISTORICAL_TOOL', 'Moved from scripts without byte changes; uninstalled and undeployed; fixed protocol/Artifact identities are not current research authority.'),
    'historical_tools/run_operational_research.py': ('ARCHIVE', 'Historical operational bridge', 'HISTORICAL_TOOL', 'Moved from scripts without byte changes; uninstalled and undeployed; fixed protocol/Artifact identities are not current research authority.'),
    'historical_tools/run_pit_candidate_replication.py': ('ARCHIVE', 'Historical candidate replication', 'HISTORICAL_TOOL', 'Moved from scripts without byte changes; uninstalled and undeployed; fixed protocol/Artifact identities are not current research authority.'),
    'historical_tools/run_pit_candidate_replication_v2.py': ('ARCHIVE', 'Historical candidate replication', 'HISTORICAL_TOOL', 'Moved from scripts without byte changes; uninstalled and undeployed; fixed protocol/Artifact identities are not current research authority.'),
    'historical_tools/run_prr_mvp_1_candidate_backtest.py': ('ARCHIVE', 'Historical candidate protocol', 'HISTORICAL_TOOL', 'Moved from scripts without byte changes; uninstalled and undeployed; fixed protocol/Artifact identities are not current research authority.'),
    'historical_tools/run_research_layer.py': ('ARCHIVE', 'Historical research protocol', 'HISTORICAL_TOOL', 'Moved from scripts without byte changes; uninstalled and undeployed; fixed protocol/Artifact identities are not current research authority.'),
    'historical_tools/run_signal_path_research.py': ('ARCHIVE', 'Historical signal protocol', 'HISTORICAL_TOOL', 'Moved from scripts without byte changes; uninstalled and undeployed; fixed protocol/Artifact identities are not current research authority.'),
    'historical_tools/run_tencent_composite_exploratory.py': ('ARCHIVE', 'Historical auxiliary composite protocol', 'HISTORICAL_TOOL', 'Moved from scripts without byte changes; uninstalled and undeployed; fixed protocol/Artifact identities are not current research authority.'),
    'historical_tools/run_wp3_candidate_research.py': ('ARCHIVE', 'Historical candidate protocol', 'HISTORICAL_TOOL', 'Moved from scripts without byte changes; uninstalled and undeployed; fixed protocol/Artifact identities are not current research authority.'),
    'scripts/apply_postgres_migrations.py': ('RETAIN', 'PostgresMigrator', 'ACCOUNT_DATABASE_ADMIN', 'Explicit retained schema family; canonical research uses SchemaManager/evidence commands, never selects this by availability.'),
    'scripts/assess_risk_reduction.py': ('RETAIN', 'Risk reduction / RepositoryFactory', 'ACCOUNT_ADMIN', 'Exact approval/account/Fill contracts lack a canonical replacement; hypothetical research results cannot substitute.'),
    'scripts/bootstrap_postgres.py': ('RETAIN', 'Postgres bootstrap role/database preflight', 'ACCOUNT_DATABASE_ADMIN', 'Explicit retained schema family; canonical research uses SchemaManager/evidence commands, never selects this by availability.'),
    'scripts/build_thesis_health.py': ('RETAIN', 'Thesis health / RepositoryFactory', 'ACCOUNT_ADMIN', 'Exact approval/account/Fill contracts lack a canonical replacement; hypothetical research results cannot substitute.'),
    'scripts/check_docs_links.py': ('RETAIN', 'Repository maintenance', 'DEVELOPMENT', 'Source/docs/Git inspection only; no research or account authority.'),
    'scripts/check_repository_hygiene.py': ('RETAIN', 'Repository maintenance', 'DEVELOPMENT', 'Source/docs/Git inspection only; no research or account authority.'),
    'scripts/confirm_risk_reduction.py': ('RETAIN', 'RiskReductionManualIntent / RepositoryFactory', 'ACCOUNT_ADMIN', 'Exact approval/account/Fill contracts lack a canonical replacement; hypothetical research results cannot substitute.'),
    'scripts/fetch_baostock_5min_batch.py': ('RETAIN', 'Auxiliary Provider raw export', 'RAW_SOURCE_TOOL', 'Raw bytes and failures remain auxiliary input; not Capture/Archive or formal/PIT authority.'),
    'scripts/fetch_dividend_5min_csv.py': ('RETAIN', 'Auxiliary Provider raw export', 'RAW_SOURCE_TOOL', 'Raw bytes and failures remain auxiliary input; not Capture/Archive or formal/PIT authority.'),
    'scripts/fetch_tushare_bars.py': ('RETAIN', 'Auxiliary Provider raw export', 'RAW_SOURCE_TOOL', 'Raw bytes and failures remain auxiliary input; not Capture/Archive or formal/PIT authority.'),
    'scripts/fetch_yfinance_5min.py': ('RETAIN', 'Auxiliary Provider raw export', 'RAW_SOURCE_TOOL', 'Raw bytes and failures remain auxiliary input; not Capture/Archive or formal/PIT authority.'),
    'scripts/qualify_generic_backtest_archive.py': ('RETAIN', 'bootstrap_application / MarketArchiveOperations', 'CANONICAL_ARCHIVE_OPERATOR', 'Freezes and seals archive inputs via canonical owner; no independent Backtest algorithm.'),
    'scripts/reconcile_branches.py': ('RETAIN', 'Repository maintenance', 'DEVELOPMENT', 'Source/docs/Git inspection only; no research or account authority.'),
    'scripts/record_manual_fill.py': ('RETAIN', 'Observed manual Fill / RepositoryFactory', 'ACCOUNT_ADMIN', 'Exact approval/account/Fill contracts lack a canonical replacement; hypothetical research results cannot substitute.'),
    'scripts/record_manual_trade.py': ('RETAIN', 'Manual trade intent / RepositoryFactory', 'ACCOUNT_ADMIN', 'Exact approval/account/Fill contracts lack a canonical replacement; hypothetical research results cannot substitute.'),
    'scripts/replay_lifecycle_review.py': ('RETAIN', 'TradingLifecycle review Artifact', 'ACCOUNT_REVIEW', 'Explicit manual lifecycle input/Artifact; no live execution or alternate research Runtime.'),
    'scripts/repository_inventory.py': ('RETAIN', 'Repository maintenance', 'DEVELOPMENT', 'Source/docs/Git inspection only; no research or account authority.'),
    'scripts/run_decision_lifecycle.py': ('RETAIN', 'Decision lifecycle / RepositoryFactory', 'ACCOUNT_ADMIN', 'Exact approval/account/Fill contracts lack a canonical replacement; hypothetical research results cannot substitute.'),
    'scripts/run_engineering_verification.py': ('RETAIN', 'EngineeringVerificationRecord / legacy schema head', 'ACCOUNT_DATABASE_ADMIN', 'Explicit retained schema family; canonical research uses SchemaManager/evidence commands, never selects this by availability.'),
    'scripts/run_lifecycle_review.py': ('RETAIN', 'TradingLifecycle review Artifact', 'ACCOUNT_REVIEW', 'Explicit manual lifecycle input/Artifact; no live execution or alternate research Runtime.'),
    'scripts/run_mr2b_f2a_conditionality_inputs.py': ('ARCHIVE', 'Exact historical conditionality input reader', 'HISTORICAL_PINNED_PATH', 'Reader validates this exact relative path and source hash; preserve bytes/path, not a current research entry.'),
    'scripts/run_portfolio_risk.py': ('RETAIN', 'Account portfolio risk / RepositoryFactory', 'ACCOUNT_ADMIN', 'Exact approval/account/Fill contracts lack a canonical replacement; hypothetical research results cannot substitute.'),
    'scripts/verify_disaster_recovery.py': ('RETAIN', 'Postgres disaster recovery', 'ACCOUNT_DATABASE_ADMIN', 'Explicit retained schema family; canonical research uses SchemaManager/evidence commands, never selects this by availability.'),
    'src/market_regime_alpha/cli/create_manual_trade_from_risk_decision.py': ('RETAIN', 'RiskReductionManualIntent', 'ACCOUNT_ADMIN', 'Called by confirm_risk_reduction; approved risk decision is not an observed Fill.'),
    'src/market_regime_alpha/cli/decision_system.py': ('RETAIN', 'DecisionSystemApplication / DecisionRuntime / observed account owners', 'ACCOUNT_ADMIN', 'Typed old Runtime claim/fence and ModelLineage are required; no canonical observed-Fill/account replacement.'),
    'src/market_regime_alpha/cli/model_governance.py': ('RETAIN', 'ModelGovernanceOperations / PostgreSQL formal governance', 'FORMAL_GOVERNANCE_ADMIN', 'Formal model evidence floors, revocation and selection are distinct from experimental Model use.'),
    'src/market_regime_alpha/cli/pit_authority.py': ('RETAIN', 'PitAuthorityOperations / PostgreSQL PIT authority', 'FORMAL_GOVERNANCE_ADMIN', 'Exact provider evidence, qualifications and ACL/revocation have no canonical replacement.'),
    'src/market_regime_alpha/cli/replay_canonical_lifecycle.py': ('RETAIN', 'Lifecycle durable replay', 'HISTORICAL_API', 'Creates a source-bound verification journal and report; source business results remain immutable; not zero-write replay.'),
    'src/market_regime_alpha/cli/replay_controlled_operation.py': ('RETAIN', 'Controlled operation exact-package replay', 'HISTORICAL_API', 'Requires exact package and PostgreSQL runtime binding; no availability-selected report or execution runner.'),
    'src/market_regime_alpha/cli/replay_feature_bundle.py': ('RETAIN', 'Feature exact-bundle replay', 'HISTORICAL_API', 'Recomputes the historical serialization from its exact Dataset; cannot publish new research authority.'),
    'src/market_regime_alpha/interfaces/cli/__init__.py': ('RETAIN', 'bootstrap_application / canonical context Applications', 'CURRENT_RESEARCH', 'Only installed current research composition; explicit schema and Artifact scope.'),
    'src/market_regime_alpha/legacy/inspect_runtime.py': ('MERGE', 'ContinuousResearch journal / Shadow report-replay / State pool decoder', 'HISTORICAL_READ_ONLY', 'Exact IDs and read-only connections; absorbs retained reads from retired entry points; never schedules or writes.'),
    'tools/xuntou/export_pit_validation_bundle_v4.py': ('RETAIN', 'Xuntou capability/evidence export', 'RAW_SOURCE_TOOL', 'Provider observation for explicit qualification review; cannot grant provider or trading authority.'),
    'tools/xuntou/probe_xtquant_pit_capabilities.py': ('RETAIN', 'Xuntou capability/evidence export', 'RAW_SOURCE_TOOL', 'Provider observation for explicit qualification review; cannot grant provider or trading authority.'),
}


def module_name(path: Path) -> str:
    parts = path.with_suffix("").parts
    if parts[0] == "src":
        parts = parts[1:]
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def imports(tree: ast.AST, module: str, is_package: bool) -> list[str]:
    result: set[str] = set()
    package = module if is_package else module.rpartition(".")[0]
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            result.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            base = node.module or ""
            if node.level:
                base = resolve_name("." * node.level + base, package)
            result.add(base)
            result.update(base + "." + alias.name for alias in node.names)
    return sorted(result)


def unresolved_imports(tree: ast.AST, module: str, is_package: bool, known: set[str]) -> list[str]:
    package = module if is_package else module.rpartition(".")[0]
    declared: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            declared.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            name = node.module or ""
            declared.add(resolve_name("." * node.level + name, package) if node.level else name)
            if not node.level and name in {"scripts", "historical_tools"}:
                declared.update(name + "." + alias.name for alias in node.names)
    return sorted(name for name in declared
                  if name.startswith(("market_regime_alpha.", "tests.", "tests_historical.", "scripts.", "historical_tools."))
                  and name not in known)


def _contract_kind(path: str, node: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
    tokens = path.lower() + " " + node.name.lower()
    if path.startswith("tests_historical/"):
        return "historical-reconciliation"
    if "/architecture/" in path or "boundar" in path or "architecture" in path:
        return "architecture"
    if "/scripts/" in path or path.endswith("test_reproducible_environment.py"):
        return "repository-tooling"
    if any(term in tokens for term in ("migration", "schema", "bootstrap", "upgrade")):
        return "migration"
    if any(term in tokens for term in ("runtime", "lease", "fence", "concurr", "recovery", "idempoten")):
        return "runtime-and-recovery"
    if any(term in tokens for term in ("episode", "economics", "evaluation_formula", "target_kernel")):
        return "research-correctness"
    args = {a.arg for a in node.args.args}
    if "postgres" in path or args & {"target_database_url", "postgres_factory"}:
        return "postgres-integration"
    if "/application/" in path or "_application" in path or "/cli/" in path:
        return "application"
    return "domain-and-serialization"


def consumer_graph(source: dict[str, Any], entry_points: dict[str, str]) -> dict[str, Any]:
    """Index actual executable roots and their static adapter closure, including uninstalled APIs."""
    installed: dict[str, list[str]] = {}
    for name, entry in entry_points.items():
        module = "src/" + entry.split(":")[0].replace(".", "/")
        path = module + ".py" if module + ".py" in source else module + "/__init__.py"
        installed.setdefault(path, []).append(name)
    roots = {
        path for path, record in source.items()
        if path in installed or record["module_entry"]
        or (path.startswith(("scripts/", "historical_tools/", "tools/", "docs/operations/"))
            and not Path(path).name.startswith("_"))
        or (path.startswith("src/market_regime_alpha/cli/")
            and any(name == "main" or name.endswith("_main") for name in record["symbols"]))
    }
    result = {}
    for path in sorted(roots):
        seen: set[str] = set()
        pending = [path]
        while pending:
            dependency = pending.pop()
            if dependency in seen:
                continue
            seen.add(dependency)
            pending.extend(source.get(dependency, {}).get("imports", []))
        decision = CONSUMER_DISPOSITIONS.get(path)
        result[path] = {
            "disposition": decision[0] if decision else None,
            "owner": decision[1] if decision else None,
            "scope": decision[2] if decision else None,
            "reason": decision[3] if decision else None,
            "installed_as": sorted(installed.get(path, [])),
            "direct_imports": source[path]["imports"],
            "reachable_modules": sorted(seen),
            "sql_adapters": sorted(p for p in seen if source.get(p, {}).get("sql_references")),
            "legacy_persistence_dependencies": sorted(p for p in seen if "/persistence/" in p),
            "canonical_postgres_dependencies": sorted(p for p in seen if "/infrastructure/postgres/" in p),
        }
    return result


def inventory(root: Path = ROOT) -> dict[str, Any]:
    paths = sorted({
        *root.glob("src/**/*.py"), *root.glob("scripts/**/*.py"), *root.glob("historical_tools/**/*.py"),
        *root.glob("tools/**/*.py"), *root.glob("docs/operations/**/*.py"),
        *root.glob("tests/**/*.py"), *root.glob("tests_historical/**/*.py"),
    })
    trees = {p: ast.parse(p.read_text(), filename=str(p)) for p in paths}
    modules = {module_name(p.relative_to(root)): p.relative_to(root).as_posix() for p in paths}
    known = {".".join(name.split(".")[:i]) for name in modules for i in range(1, len(name.split(".")) + 1)}
    unresolved = {}
    users: dict[str, set[str]] = defaultdict(set)
    dependencies: dict[str, list[str]] = {}
    for path, tree in trees.items():
        relative = path.relative_to(root).as_posix()
        missing = unresolved_imports(tree, module_name(path.relative_to(root)), path.name == "__init__.py", known)
        if missing:
            unresolved[relative] = missing
        resolved = set()
        for imported in imports(tree, module_name(path.relative_to(root)), path.name == "__init__.py"):
            name = imported
            while name and name not in modules:
                name = name.rpartition(".")[0]
            if name:
                resolved.add(modules[name])
                users[modules[name]].add(relative)
        dependencies[relative] = sorted(resolved)
    source = {}
    tests = {}
    for path, tree in trees.items():
        relative = path.relative_to(root).as_posix()
        if relative.startswith(("tests/", "tests_historical/")):
            contracts = {}
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test_"):
                    contracts[node.name] = {
                        "kind": _contract_kind(relative, node),
                        "assertions": sum(isinstance(n, ast.Assert) for n in ast.walk(node)),
                        "raises_contract": any(
                            isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                            and n.func.attr == "raises" for n in ast.walk(node)
                        ),
                    }
            tests[relative] = {
                "contracts": contracts,
                "imports": dependencies[relative],
                "consumers": sorted(users[relative]),
            }
        else:
            text = path.read_text()
            relations: dict[str, set[str]] = defaultdict(set)
            for match in _SQL.finditer(text):
                operation, table = match.groups()
                relations[table].add("write" if operation.upper().startswith(("INSERT", "UPDATE", "DELETE")) else "read")
            source[relative] = {
                "symbols": [n.name for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))],
                "imports": dependencies[relative],
                "consumers": sorted(users[relative]),
                "sql_references": {k: sorted(v) for k, v in sorted(relations.items())},
                "module_entry": any(
                    isinstance(n, ast.If) and "__name__" in ast.unparse(n.test)
                    for n in tree.body
                ),
            }
    schema = {
        p.relative_to(root).as_posix(): {
            "sha256": sha256(p.read_bytes()).hexdigest(),
            "declared_tables": sorted(set(_TABLE.findall(p.read_text()))),
        }
        for p in sorted((root / "src").rglob("*.sql"))
    }
    project = tomllib.loads((root / "pyproject.toml").read_text())
    return {
        "limitations": [
            "Static import and SQL-literal references, not proof of dynamic reachability or deployment.",
            "CTEs/unqualified/dynamic SQL require owner review; schema declarations disambiguate actual tables.",
            "Test names identify declared contracts, not sufficiency; assertion and PostgreSQL execution evidence is separate.",
            "A module with no static consumers may be a public API, module CLI or historical decoder; do not auto-delete.",
        ],
        "entry_points": project["project"]["scripts"],
        "consumer_graph": consumer_graph(source, project["project"]["scripts"]),
        "unresolved_internal_modules": unresolved,
        "source": source,
        "schema": schema,
        "tests": tests,
    }


def encoded(value: dict[str, Any]) -> str:
    # One record per line keeps the generated index diffable without making it startup prose.
    lines = ["{"]
    for index, (key, content) in enumerate(value.items()):
        if index:
            lines[-1] += ","
        if isinstance(content, dict):
            lines.append(json.dumps(key) + ": {")
            for ordinal, (name, record) in enumerate(content.items()):
                if ordinal:
                    lines[-1] += ","
                lines.append(json.dumps(name) + ": " + json.dumps(record, sort_keys=True, ensure_ascii=False))
            lines.append("}")
        else:
            lines.append(json.dumps(key) + ": " + json.dumps(content, ensure_ascii=False))
    return "\n".join(lines + ["}"]) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    result = encoded(inventory())
    path = ROOT / OUTPUT
    if args.write:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(result)
        print("source/test/schema inventory regenerated")
        return 0
    if not path.exists() or path.read_text() != result:
        print("source/test/schema inventory drift: uv run python scripts/repository_inventory.py --write")
        return 1
    print("source/test/schema inventory matches")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
