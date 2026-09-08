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


def module_name(path: Path) -> str:
    parts = path.with_suffix("").parts
    if parts[0] == "src":
        parts = parts[1:]
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def imports(tree: ast.AST, module: str, is_package: bool) -> list[str]:
    result = set()
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


def inventory(root: Path = ROOT) -> dict[str, Any]:
    paths = sorted({
        *root.glob("src/**/*.py"), *root.glob("scripts/**/*.py"),
        *root.glob("tools/**/*.py"), *root.glob("docs/operations/**/*.py"),
        *root.glob("tests/**/*.py"), *root.glob("tests_historical/**/*.py"),
    })
    trees = {p: ast.parse(p.read_text(), filename=str(p)) for p in paths}
    modules = {module_name(p.relative_to(root)): p.relative_to(root).as_posix() for p in paths}
    users: dict[str, set[str]] = defaultdict(set)
    dependencies: dict[str, list[str]] = {}
    for path, tree in trees.items():
        relative = path.relative_to(root).as_posix()
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
