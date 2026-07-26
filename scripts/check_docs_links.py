"""Validate documentation authority, links, evidence and migration consistency."""
from __future__ import annotations

import ast
import csv
import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ALLOWED_STATUSES = {
    "CONSTITUTION",
    "CURRENT_ARCHITECTURE",
    "CURRENT_RESEARCH_PROGRAM",
    "CURRENT_SPECIFICATION",
    "CURRENT_STATUS",
    "ROADMAP",
    "HISTORICAL",
    "SUPERSEDED",
    "DRAFT",
}
STATUS_RE = re.compile(r"^\s*>\s*\*\*Status:\*\*\s*(.+?)\s*$", re.IGNORECASE)
META_RE = re.compile(r"^\s*>\s*\*\*([^*]+):\*\*\s*(.*?)\s*$")
LINK_RE = re.compile(r"(?<!!)\[[^\]]*\]\(([^)]+)\)")
PATH_TOKEN_RE = re.compile(r"(?:\.\.?/)?[A-Za-z0-9_./-]+\.md")


def markdown_files(root: Path) -> list[Path]:
    return sorted((root / "docs").rglob("*.md"))


def lines_outside_fences(text: str) -> list[tuple[int, str]]:
    result: list[tuple[int, str]] = []
    in_fence = False
    for number, line in enumerate(text.splitlines(), start=1):
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
            continue
        if not in_fence:
            result.append((number, line))
    return result


def parse_metadata(path: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for _, line in lines_outside_fences(path.read_text(encoding="utf-8"))[:80]:
        match = META_RE.match(line)
        if match:
            result[match.group(1).strip()] = match.group(2).strip()
    return result


def resolve_link(root: Path, source: Path, raw: str) -> Path | None:
    value = raw.strip().split()[0].strip("<>").split("#", 1)[0]
    if not value or re.match(r"^(?:https?|mailto|tel):", value):
        return None
    if value.startswith("/"):
        return root / value.lstrip("/")
    candidate = (source.parent / value).resolve()
    if candidate.exists():
        return candidate
    return (root / value).resolve()


def check_links(root: Path, docs: list[Path]) -> list[str]:
    errors: list[str] = []
    for source in docs + [root / "README.md", root / "AGENTS.md"]:
        if not source.exists():
            continue
        text = source.read_text(encoding="utf-8")
        for match in LINK_RE.finditer(text):
            target = resolve_link(root, source, match.group(1))
            if target is not None and not target.exists():
                errors.append(f"broken link: {source.relative_to(root)} -> {match.group(1)}")
    return errors


def check_statuses(docs: list[Path]) -> list[str]:
    errors: list[str] = []
    for path in docs:
        outside = lines_outside_fences(path.read_text(encoding="utf-8"))
        matches = [
            (number, match.group(1).strip())
            for number, line in outside
            if (match := STATUS_RE.match(line))
        ]
        if len(matches) != 1:
            errors.append(f"{path}: expected exactly one Status metadata field, found {len(matches)}")
            continue
        number, status = matches[0]
        if status not in ALLOWED_STATUSES:
            errors.append(f"{path}:{number}: invalid status {status!r}")
        if status == "SUPERSEDED":
            for line_no, line in outside:
                if line_no == number:
                    continue
                if re.match(r"^\s*(?:>\s*)?(?:\*\*)?Current Authority(?:\*\*)?:", line, re.IGNORECASE):
                    errors.append(f"{path}:{line_no}: active Current authority field in SUPERSEDED document")
                if re.match(r"^\s*(?:>\s*)?Status:\s*CURRENT\b", line, re.IGNORECASE):
                    errors.append(f"{path}:{line_no}: secondary active CURRENT status")
    return errors


def check_authority_split(root: Path) -> list[str]:
    errors: list[str] = []
    for relative in ("docs/README.md", "AGENTS.md"):
        text = (root / relative).read_text(encoding="utf-8")
        for heading in ("Normative authority order", "Implementation fact authority order"):
            if heading not in text:
                errors.append(f"{relative}: missing {heading}")
    return errors


def check_supersession(root: Path) -> list[str]:
    errors: list[str] = []
    registry = root / "docs/audit/Supersession-Registry.tsv"
    if not registry.exists():
        return ["missing docs/audit/Supersession-Registry.tsv"]
    with registry.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle, delimiter="\t"))
    registered = {(row["source_path"], row["target_path"]) for row in rows}
    for source_path, target_path in registered:
        source = root / source_path
        target = root / target_path
        if not source.exists():
            errors.append(f"supersession source missing: {source_path}")
            continue
        if not target.exists():
            errors.append(f"supersession target missing: {target_path}")
            continue
        meta = parse_metadata(source)
        target_tokens = PATH_TOKEN_RE.findall(meta.get("Superseded By", ""))
        resolved = {
            p.relative_to(root).as_posix()
            for token in target_tokens
            if (p := resolve_link(root, source, token)) is not None and p.exists()
        }
        if target_path not in resolved:
            errors.append(f"supersession metadata mismatch: {source_path} -> {target_path}")
        if meta.get("Status") != "SUPERSEDED":
            errors.append(f"supersession source not SUPERSEDED: {source_path}")
    return errors


def check_orphans(root: Path, docs: list[Path]) -> list[str]:
    inbound: dict[Path, int] = defaultdict(int)
    sources = docs + [root / "README.md", root / "AGENTS.md"]
    for source in sources:
        if not source.exists():
            continue
        for match in LINK_RE.finditer(source.read_text(encoding="utf-8")):
            target = resolve_link(root, source, match.group(1))
            if target is not None and target.exists() and target.suffix == ".md":
                inbound[target.resolve()] += 1
    errors: list[str] = []
    for path in docs:
        meta = parse_metadata(path)
        if meta.get("Status") in {"HISTORICAL", "SUPERSEDED"}:
            continue
        if "docs/archive/" in path.relative_to(root).as_posix():
            continue
        if path.name == "README.md":
            continue
        if inbound[path.resolve()] == 0:
            errors.append(f"orphan current document: {path.relative_to(root)}")
    return errors


def build_symbol_index(root: Path) -> set[str]:
    names: set[str] = set()
    for path in (root / "src").rglob("*.py"):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError):
            continue
        for node in ast.walk(tree):
            if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                names.add(node.name)
    return names


def check_code_evidence(root: Path) -> list[str]:
    registry = root / "docs/audit/Code-Evidence-Registry.tsv"
    if not registry.exists():
        return ["missing docs/audit/Code-Evidence-Registry.tsv"]
    symbols = build_symbol_index(root)
    errors: list[str] = []
    with registry.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle, delimiter="\t"))
    for row in rows:
        if not (root / row["document_path"]).exists():
            errors.append(f"code evidence document missing: {row['document_path']}")
        required = row.get("required", "true").lower() == "true"
        if row["evidence_type"] == "path":
            matches = list(root.glob(row["evidence_ref"]))
            if required and not matches:
                errors.append(f"code evidence path missing: {row['evidence_ref']}")
        elif row["evidence_type"] == "symbol":
            if required and row["evidence_ref"] not in symbols:
                errors.append(f"code evidence symbol missing: {row['evidence_ref']}")
        else:
            errors.append(f"unknown evidence_type: {row['evidence_type']}")
    return errors


def check_constitution(root: Path) -> list[str]:
    errors: list[str] = []
    forbidden_heading = re.compile(
        r"^#{1,6}\s+.*(?:Current Repository Migration Audit|Current Capability Matrix|Implementation Status)\b",
        re.IGNORECASE,
    )
    forbidden_fact = re.compile(
        r"\b(?:IMPLEMENTED_AND_VERIFIED|BLOCKED_EXTERNAL_INPUT|NOT_STARTED|PENDING_PR)\b|"
        r"\bmain@[0-9a-f]{7,40}\b|\bPR\s*#\d+\b",
        re.IGNORECASE,
    )
    for path in sorted((root / "docs/constitution").glob("*.md")):
        metadata = parse_metadata(path)
        if metadata.get("Status") != "CONSTITUTION":
            continue
        for line_no, line in lines_outside_fences(path.read_text(encoding="utf-8")):
            if forbidden_heading.search(line):
                errors.append(f"{path}:{line_no}: implementation-state heading in Constitution")
            if forbidden_fact.search(line):
                errors.append(f"{path}:{line_no}: implementation-state fact in Constitution")
    return errors


def check_inventory(root: Path) -> list[str]:
    path = root / "docs/audit/Docs-Inventory.tsv"
    if not path.exists():
        return ["missing Docs-Inventory.tsv"]
    errors: list[str] = []
    with path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle, delimiter="\t"))
    required_columns = {"actual_action", "target_path", "verification_status"}
    if rows and not required_columns.issubset(rows[0]):
        return ["Docs-Inventory.tsv missing actual outcome columns"]
    for row in rows:
        if row.get("verification_status") != "VERIFIED":
            errors.append(f"inventory unresolved: {row.get('path')}")
            continue
        target = row.get("target_path", "")
        if not target or not (root / target).exists():
            errors.append(f"inventory target missing: {row.get('path')} -> {target}")
    return errors


def validate(root: Path = ROOT) -> list[str]:
    docs = markdown_files(root)
    errors: list[str] = []
    errors.extend(check_links(root, docs))
    errors.extend(check_statuses(docs))
    errors.extend(check_authority_split(root))
    errors.extend(check_supersession(root))
    errors.extend(check_orphans(root, docs))
    errors.extend(check_code_evidence(root))
    errors.extend(check_constitution(root))
    errors.extend(check_inventory(root))
    return errors


def main() -> int:
    errors = validate(ROOT)
    if errors:
        print("\n".join(errors))
        return 1
    print("documentation authority, links, evidence, supersession and inventory: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
