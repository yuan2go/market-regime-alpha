"""Guard current context, commentary and schema projections without touching a database."""

from __future__ import annotations

import ast
import io
from pathlib import Path
import re
import sys
import tokenize

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.check_docs_links import CANONICAL_DOCS
from scripts.repository_inventory import OUTPUT, encoded, inventory
from market_regime_alpha.infrastructure.postgres.schema import EXPECTED_TARGET_TABLES, SCHEMA_EPOCH

_HISTORY = re.compile(r"\bWP(?:[-_][A-Z0-9]+)+|\bWP\d+[A-Z]*", re.I)


def check_commentary(root: Path) -> list[str]:
    errors = []
    for path in sorted((root / "src").rglob("*.py")):
        text = path.read_text()
        notes = [
            (tok.start[0], tok.string)
            for tok in tokenize.generate_tokens(io.StringIO(text).readline)
            if tok.type == tokenize.COMMENT
        ]
        for node in ast.walk(ast.parse(text)):
            if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                doc = ast.get_docstring(node)
                if doc:
                    notes.append((node.body[0].lineno, doc))
        for line, note in notes:
            if _HISTORY.search(note):
                errors.append(f"{path.relative_to(root)}:{line}: historical work-package commentary")
    return errors


def schema_facts() -> str:
    return (
        "<!-- schema-facts:start -->\n"
        f"Epoch: `{SCHEMA_EPOCH}`.\n"
        f"Research table count: **{len(EXPECTED_TARGET_TABLES)}**.\n"
        "<!-- schema-facts:end -->"
    )


def check_schema_facts(root: Path) -> list[str]:
    path = root / "docs/status/Current-State.md"
    if not path.exists() or schema_facts() not in path.read_text():
        return ["Current-State schema facts differ from executable schema contract"]
    return []


def check_active_context(root: Path) -> list[str]:
    errors = []
    paths = [*sorted(CANONICAL_DOCS - {"docs/archive/README.md"}), "README.md", "AGENTS.md", "CLAUDE.md"]
    for relative in paths:
        path = root / relative
        if not path.exists():
            continue
        text = path.read_text()
        if _HISTORY.search(text) or re.search(r"\]\([^)]*(?:pre-hygiene|references/WP)", text):
            errors.append(f"{relative}: historical task in current development context")
    return errors


def main() -> int:
    errors = [
        *check_active_context(ROOT), *check_commentary(ROOT), *check_schema_facts(ROOT),
    ]
    path = ROOT / OUTPUT
    if not path.exists() or path.read_text() != encoded(inventory(ROOT)):
        errors.append("source/test/schema inventory drift; regenerate scripts/repository_inventory.py --write")
    if errors:
        print("\n".join(errors))
        return 1
    print("current context, commentary, schema and inventory: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
