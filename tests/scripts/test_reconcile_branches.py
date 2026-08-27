from __future__ import annotations

import importlib.util
import subprocess
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[2] / "scripts" / "reconcile_branches.py"
SPEC = importlib.util.spec_from_file_location("reconcile_branches", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
reconcile = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(reconcile)


def git(repo: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def commit_file(repo: Path, path: str, content: str, message: str) -> None:
    target = repo / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    git(repo, "add", path)
    git(repo, "commit", "-m", message)


def repository(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init", "--initial-branch=main")
    git(repo, "config", "user.name", "Fixture User")
    git(repo, "config", "user.email", "fixture@example.invalid")
    commit_file(repo, "base.txt", "base\n", "base")
    return repo


def test_merged_branch_is_contained(tmp_path: Path) -> None:
    repo = repository(tmp_path)
    git(repo, "switch", "-c", "feature")
    commit_file(repo, "feature.txt", "merged\n", "feature")
    git(repo, "switch", "main")
    git(repo, "merge", "--no-ff", "feature", "-m", "merge feature")

    audit = reconcile.classify_branch(repo, "main", "feature")

    assert audit.classification == "CONTAINED_IN_COMPARISON"
    assert audit.evidence == "branch_is_ancestor_of_comparison"


def test_squashed_branch_is_content_contained(tmp_path: Path) -> None:
    repo = repository(tmp_path)
    git(repo, "switch", "-c", "feature")
    commit_file(repo, "feature.txt", "one\n", "feature one")
    commit_file(repo, "feature.txt", "one\ntwo\n", "feature two")
    git(repo, "switch", "main")
    git(repo, "merge", "--squash", "feature")
    git(repo, "commit", "-m", "squash feature")

    audit = reconcile.classify_branch(repo, "main", "feature")

    assert audit.classification == "CONTAINED_IN_COMPARISON"
    assert audit.evidence == "branch_changed_paths_match_comparison"


def test_rebased_equivalent_branch_is_content_contained(tmp_path: Path) -> None:
    repo = repository(tmp_path)
    git(repo, "switch", "-c", "feature-original")
    commit_file(repo, "feature.txt", "feature\n", "feature")
    git(repo, "switch", "main")
    commit_file(repo, "main.txt", "main\n", "main change")
    git(repo, "switch", "-c", "rebased")
    git(repo, "cherry-pick", "feature-original")
    git(repo, "switch", "main")

    audit = reconcile.classify_branch(repo, "rebased", "feature-original")

    assert audit.classification == "CONTAINED_IN_COMPARISON"
    assert audit.evidence == "branch_changed_paths_match_comparison"


def test_divergent_supersession_requires_manual_review(tmp_path: Path) -> None:
    repo = repository(tmp_path)
    git(repo, "switch", "-c", "feature")
    commit_file(repo, "base.txt", "candidate-v2\n", "candidate change")
    git(repo, "switch", "main")
    commit_file(repo, "base.txt", "superseding-v3\n", "superseding change")

    audit = reconcile.classify_branch(repo, "main", "feature")

    assert audit.classification == "UNKNOWN_REQUIRES_REVIEW"
    assert audit.evidence == "overlapping_divergent_paths=base.txt"


def test_disjoint_branch_change_is_unique_content(tmp_path: Path) -> None:
    repo = repository(tmp_path)
    git(repo, "switch", "-c", "feature")
    commit_file(repo, "feature.txt", "unique\n", "unique feature")
    git(repo, "switch", "main")
    commit_file(repo, "main.txt", "unrelated\n", "unrelated main")

    audit = reconcile.classify_branch(repo, "main", "feature")

    assert audit.classification == "UNMERGED_UNIQUE_CONTENT"
    assert audit.evidence == "branch_paths_unmodified_in_comparison"
