"""Physical scans against a frozen database roster, without integrity writes."""

from __future__ import annotations

from hashlib import sha256
from pathlib import Path, PurePosixPath
from typing import Any


class FilesystemEvidenceIntegrity:
    def __init__(self, root: Path) -> None:
        self._root = root.resolve()

    def verify(self, references: list[dict[str, Any]]) -> dict[str, Any]:
        mismatches = []
        expected = set()
        for reference in references:
            locator = PurePosixPath(reference["locator"])
            path = (self._root / locator).resolve()
            expected.add(str(locator))
            reason = None
            if locator.is_absolute() or ".." in locator.parts or not path.is_relative_to(self._root):
                reason = "ARTIFACT_LOCATOR_ESCAPE"
            elif not path.is_file():
                reason = "ARTIFACT_BYTES_MISSING"
            else:
                payload = path.read_bytes()
                if len(payload) != reference["size_bytes"] or sha256(payload).hexdigest() != reference["content_sha256"]:
                    reason = "ARTIFACT_BYTES_MISMATCH"
            if reason:
                mismatches.append({"artifact_id": reference["artifact_id"], "reason": reason})
        physical = {str(path.relative_to(self._root)) for path in (self._root / "objects").rglob("*") if path.is_file()}
        return {
            "matched": not mismatches,
            "mismatch_count": len(mismatches),
            "verified_artifacts": len(references) - len(mismatches),
            "mismatches": mismatches,
            "unreferenced_objects": sorted(physical - expected),
            "extra_object_count": len(physical - expected),
        }
