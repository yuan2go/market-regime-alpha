"""Read-only, content-aware branch reconciliation for the retained Skill."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path
from typing import NamedTuple, Sequence


class GitAuditError(RuntimeError):
    """Raised when Git cannot establish a required reconciliation fact."""


class BranchAudit(NamedTuple):
    branch: str
    head_sha: str
    ahead: int
    behind: int
    classification: str
    evidence: str
    proposed_action: str


def _git(
    repository: Path,
    *arguments: str,
    accepted_return_codes: tuple[int, ...] = (0,),
) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(
        ["git", *arguments],
        cwd=repository,
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode not in accepted_return_codes:
        detail = completed.stderr.strip() or completed.stdout.strip()
        raise GitAuditError(
            f"git {' '.join(arguments)} failed with {completed.returncode}: {detail}"
        )
    return completed


def _resolve_commit(repository: Path, reference: str) -> str:
    return _git(
        repository,
        "rev-parse",
        "--verify",
        "--end-of-options",
        f"{reference}^{{commit}}",
    ).stdout.strip()


def _changed_paths(repository: Path, older: str, newer: str) -> set[str]:
    output = _git(
        repository,
        "diff",
        "--name-only",
        "-z",
        "--diff-filter=ACDMRTUXB",
        f"{older}..{newer}",
        "--",
    ).stdout
    return {path for path in output.split("\0") if path}


def _current_branch(repository: Path) -> str | None:
    completed = _git(
        repository,
        "symbolic-ref",
        "--quiet",
        "--short",
        "HEAD",
        accepted_return_codes=(0, 1),
    )
    return completed.stdout.strip() or None


def classify_branch(
    repository: Path,
    comparison_ref: str,
    branch_ref: str,
) -> BranchAudit:
    """Classify one branch using only local, read-only Git evidence."""

    repository = repository.resolve()
    root = Path(_git(repository, "rev-parse", "--show-toplevel").stdout.strip())
    comparison_sha = _resolve_commit(root, comparison_ref)
    branch_sha = _resolve_commit(root, branch_ref)
    counts = _git(
        root,
        "rev-list",
        "--left-right",
        "--count",
        f"{comparison_sha}...{branch_sha}",
    ).stdout.split()
    if len(counts) != 2:
        raise GitAuditError("git rev-list returned an invalid ahead/behind count")
    behind, ahead = (int(value) for value in counts)

    if branch_ref == _current_branch(root):
        return BranchAudit(
            branch_ref,
            branch_sha,
            ahead,
            behind,
            "CURRENT_WORK_BRANCH",
            "branch_is_current_checkout",
            "PRESERVE_WORKTREE",
        )

    ancestor = _git(
        root,
        "merge-base",
        "--is-ancestor",
        branch_sha,
        comparison_sha,
        accepted_return_codes=(0, 1),
    )
    if ancestor.returncode == 0:
        return BranchAudit(
            branch_ref,
            branch_sha,
            ahead,
            behind,
            "CONTAINED_IN_COMPARISON",
            "branch_is_ancestor_of_comparison",
            "NONE",
        )

    merge_base = _git(root, "merge-base", comparison_sha, branch_sha).stdout.strip()
    branch_paths = _changed_paths(root, merge_base, branch_sha)
    if not branch_paths:
        return BranchAudit(
            branch_ref,
            branch_sha,
            ahead,
            behind,
            "CONTAINED_IN_COMPARISON",
            "branch_has_no_effective_content_change",
            "NONE",
        )

    same_content = _git(
        root,
        "diff",
        "--quiet",
        branch_sha,
        comparison_sha,
        "--",
        *sorted(branch_paths),
        accepted_return_codes=(0, 1),
    )
    if same_content.returncode == 0:
        return BranchAudit(
            branch_ref,
            branch_sha,
            ahead,
            behind,
            "CONTAINED_IN_COMPARISON",
            "branch_changed_paths_match_comparison",
            "NONE",
        )

    comparison_paths = _changed_paths(root, merge_base, comparison_sha)
    overlap = sorted(branch_paths & comparison_paths)
    if not overlap:
        return BranchAudit(
            branch_ref,
            branch_sha,
            ahead,
            behind,
            "UNMERGED_UNIQUE_CONTENT",
            "branch_paths_unmodified_in_comparison",
            "REVIEW_FOR_INTEGRATION",
        )

    return BranchAudit(
        branch_ref,
        branch_sha,
        ahead,
        behind,
        "UNKNOWN_REQUIRES_REVIEW",
        f"overlapping_divergent_paths={','.join(overlap)}",
        "MANUAL_REVIEW",
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Classify named branches against one local comparison ref."
    )
    parser.add_argument("--repository", type=Path, required=True)
    parser.add_argument("--comparison", required=True)
    parser.add_argument("--branch", action="append", required=True)
    parser.add_argument(
        "--authorization",
        choices=("READ_ONLY", "FETCH_ALLOWED", "PR_ALLOWED", "MERGE_ALLOWED"),
        default="READ_ONLY",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        repository = args.repository.resolve()
        comparison_sha = _resolve_commit(repository, args.comparison)
        audits = [
            classify_branch(repository, args.comparison, branch)
            for branch in args.branch
        ]
    except (GitAuditError, OSError, ValueError) as exc:
        print(f"RECONCILIATION_FAILED | {exc}", file=sys.stderr)
        return 2

    print(
        "REPOSITORY | COMPARISON_REF | COMPARISON_SHA | AUTHORIZATION"
    )
    print(
        f"{repository} | {args.comparison} | {comparison_sha} | "
        f"{args.authorization}"
    )
    print(
        "BRANCH | HEAD | PR | AHEAD/BEHIND | CLASSIFICATION | "
        "EVIDENCE | PROPOSED_ACTION"
    )
    for audit in audits:
        print(
            f"{audit.branch} | {audit.head_sha} | UNKNOWN | "
            f"{audit.ahead}/{audit.behind} | {audit.classification} | "
            f"{audit.evidence} | {audit.proposed_action}"
        )
    print("SIDE_EFFECTS_PERFORMED | NONE")
    unresolved = [
        audit.branch
        for audit in audits
        if audit.classification == "UNKNOWN_REQUIRES_REVIEW"
    ]
    print(
        "UNRESOLVED_STATE | "
        + (",".join(unresolved) if unresolved else "NONE")
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
