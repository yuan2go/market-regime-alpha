"""Validate repository-local Markdown links and current-document authority rules."""
from __future__ import annotations
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
LINK_RE = re.compile(r"(?<!!)\[[^\]]*\]\(([^)]+)\)")
CURRENT_STATUS = "docs/status/Current-State.md"


def resolve(source: Path, raw: str) -> Path | None:
    value = raw.strip().split()[0].strip("<>").split("#", 1)[0]
    if not value or re.match(r"^(?:https?|mailto|tel):", value):
        return None
    if value.startswith("/"):
        return ROOT / value.lstrip("/")
    candidate = (source.parent / value).resolve()
    if candidate.exists():
        return candidate
    return (ROOT / value).resolve()


def main() -> int:
    errors: list[str] = []
    for source in sorted((ROOT / "docs").rglob("*.md")):
        text = source.read_text(encoding="utf-8")
        for match in LINK_RE.finditer(text):
            target = resolve(source, match.group(1))
            if target is not None and not target.exists():
                errors.append(f"broken link: {source.relative_to(ROOT)} -> {match.group(1)}")
        if source.name != "README.md" and "> **Status:**" not in text[:2500]:
            errors.append(f"missing document status header: {source.relative_to(ROOT)}")
    if not (ROOT / CURRENT_STATUS).exists():
        errors.append(f"missing unique current status: {CURRENT_STATUS}")
    if errors:
        print("\n".join(errors))
        return 1
    print("documentation links and status headers: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
