from __future__ import annotations

from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from market_regime_alpha.dividend_t.git_publish import publish_paths  # noqa: E402


class GitPublishTests(unittest.TestCase):
    def test_publish_paths_commits_only_requested_file_without_push(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _git(root, "init")
            _git(root, "config", "user.email", "test@example.com")
            _git(root, "config", "user.name", "Test User")
            target = root / "docs" / "data" / "dividend_trends.json"
            target.parent.mkdir(parents=True)
            target.write_text('{"rows":[]}\n', encoding="utf-8")

            result = publish_paths(repo_root=root, paths=[target], commit_message="Update snapshot", push=False)

            log = _git(root, "log", "--oneline", "-1")
            self.assertTrue(result.changed)
            self.assertTrue(result.committed)
            self.assertFalse(result.pushed)
            self.assertIsNotNone(result.commit_hash)
            self.assertIn("Update snapshot", log)

    def test_publish_paths_skips_when_file_has_no_changes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _git(root, "init")
            _git(root, "config", "user.email", "test@example.com")
            _git(root, "config", "user.name", "Test User")
            target = root / "docs" / "data" / "dividend_trends.json"
            target.parent.mkdir(parents=True)
            target.write_text('{"rows":[]}\n', encoding="utf-8")
            first = publish_paths(repo_root=root, paths=[target], commit_message="Update snapshot", push=False)
            second = publish_paths(repo_root=root, paths=[target], commit_message="Update snapshot", push=False)

            self.assertTrue(first.committed)
            self.assertFalse(second.changed)
            self.assertEqual(second.message, "no changes to publish")


def _git(root: Path, *args: str) -> str:
    completed = subprocess.run(["git", *args], cwd=root, check=True, capture_output=True, text=True)
    return completed.stdout


if __name__ == "__main__":
    unittest.main()
