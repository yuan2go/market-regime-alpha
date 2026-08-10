"""Validate the small canonical documentation set and its local links."""

from __future__ import annotations

import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ALLOWED_STATUSES = {
    "CONSTITUTION",
    "CURRENT_ARCHITECTURE",
    "CURRENT_RESEARCH_PROGRAM",
    "CURRENT_STATUS",
    "ROADMAP",
    "HISTORICAL",
    "SUPERSEDED",
}
STATUS_RE = re.compile(r"^\s*>\s*\*\*Status:\*\*\s*(.+?)\s*$", re.IGNORECASE)
META_RE = re.compile(r"^\s*>\s*\*\*([^*]+):\*\*\s*(.*?)\s*$")
LINK_RE = re.compile(r"(?<!!)\[[^\]]*\]\(([^)]+)\)")
CODE_EVIDENCE_PATH_RE = re.compile(r"`([^`]+)`")

CANONICAL_DOCS = frozenset(
    {
        "docs/README.md",
        "docs/architecture/System-Architecture.md",
        "docs/architecture/Authority-Map.md",
        "docs/architecture/Data-and-Evidence-Architecture.md",
        "docs/architecture/Research-Strategy-Lifecycle.md",
        "docs/status/Current-State.md",
        "docs/status/Capability-Matrix.md",
        "docs/status/Gap-Register.md",
        "docs/status/Roadmap.md",
        "docs/operations/Runtime-Runbook.md",
        "docs/research/Negative-and-Inconclusive-Results.md",
        "docs/archive/README.md",
    }
)
SUPPLEMENTARY_DOC_ROOTS = (
    "docs/archive/",
    "docs/architecture/decisions/",
    "docs/references/",
    "docs/research/protocols/",
)


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
    return (source.parent / value).resolve()


def check_links(root: Path, docs: list[Path]) -> list[str]:
    errors: list[str] = []
    for source in docs + [root / "README.md", root / "AGENTS.md", root / "CLAUDE.md"]:
        if not source.exists():
            continue
        for match in LINK_RE.finditer(source.read_text(encoding="utf-8")):
            target = resolve_link(root, source, match.group(1))
            if target is not None and not target.exists():
                errors.append(
                    f"broken link: {source.relative_to(root)} -> {match.group(1)}"
                )
    return errors


def check_statuses(docs: list[Path]) -> list[str]:
    errors: list[str] = []
    for path in docs:
        matches = [
            (number, match.group(1).strip())
            for number, line in lines_outside_fences(
                path.read_text(encoding="utf-8")
            )
            if (match := STATUS_RE.match(line))
        ]
        if len(matches) != 1:
            errors.append(
                f"{path}: expected exactly one Status metadata field, "
                f"found {len(matches)}"
            )
            continue
        number, status = matches[0]
        if status not in ALLOWED_STATUSES:
            errors.append(f"{path}:{number}: invalid status {status!r}")
    return errors


def check_canonical_inventory(root: Path, docs: list[Path]) -> list[str]:
    actual = {
        path.relative_to(root).as_posix()
        for path in docs
        if "docs/constitution/" not in path.relative_to(root).as_posix()
    }
    missing = sorted(CANONICAL_DOCS - actual)
    unexpected = sorted(
        path
        for path in actual - CANONICAL_DOCS
        if not path.startswith(SUPPLEMENTARY_DOC_ROOTS)
    )
    return [
        *(f"missing canonical document: {path}" for path in missing),
        *(
            f"unexpected document outside canonical or supplementary set: {path}"
            for path in unexpected
        ),
    ]


def check_authority_split(root: Path) -> list[str]:
    errors: list[str] = []
    for relative in ("docs/README.md", "AGENTS.md"):
        text = (root / relative).read_text(encoding="utf-8")
        for heading in (
            "Normative authority order",
            "Implementation fact authority order",
        ):
            if heading.lower() not in text.lower():
                errors.append(f"{relative}: missing {heading}")
    return errors


def check_current_metadata(root: Path) -> list[str]:
    errors: list[str] = []
    for relative in sorted(CANONICAL_DOCS):
        metadata = parse_metadata(root / relative)
        if relative == "docs/archive/README.md":
            continue
        value = metadata.get("Code Evidence", "")
        evidence_paths = CODE_EVIDENCE_PATH_RE.findall(value)
        if not evidence_paths:
            errors.append(f"{relative}: missing resolvable Code Evidence paths")
            continue
        for evidence_path in evidence_paths:
            if Path(evidence_path).is_absolute() or ".." in Path(evidence_path).parts:
                errors.append(
                    f"{relative}: Code Evidence must be repository-relative: "
                    f"{evidence_path}"
                )
                continue
            matches = list(root.glob(evidence_path))
            if not matches:
                errors.append(
                    f"{relative}: Code Evidence path does not resolve: "
                    f"{evidence_path}"
                )
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
        if parse_metadata(path).get("Status") != "CONSTITUTION":
            continue
        for line_no, line in lines_outside_fences(path.read_text(encoding="utf-8")):
            if forbidden_heading.search(line):
                errors.append(
                    f"{path}:{line_no}: implementation-state heading in Constitution"
                )
            if forbidden_fact.search(line):
                errors.append(
                    f"{path}:{line_no}: implementation-state fact in Constitution"
                )
    return errors


def validate(root: Path = ROOT) -> list[str]:
    docs = markdown_files(root)
    return [
        *check_links(root, docs),
        *check_statuses(docs),
        *check_canonical_inventory(root, docs),
        *check_authority_split(root),
        *check_current_metadata(root),
        *check_constitution(root),
    ]


def main() -> int:
    errors = validate(ROOT)
    if errors:
        print("\n".join(errors))
        return 1
    print("canonical documentation inventory, metadata and links: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
