from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "bin" / "diff"


class DiffCliTest(unittest.TestCase):
    def run_cli(
        self,
        repo: Path,
        args: list[str],
        *,
        now: str = "2026-03-10T12:00:00+00:00",
    ) -> subprocess.CompletedProcess[str]:
        env = os.environ.copy()
        env["TOOL_DIFF_NOW"] = now
        return subprocess.run(
            [sys.executable, str(CLI), *args],
            cwd=repo,
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )

    def run_git(
        self,
        repo: Path,
        args: list[str],
        *,
        env: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        final_env = os.environ.copy()
        if env:
            final_env.update(env)
        return subprocess.run(
            ["git", *args],
            cwd=repo,
            env=final_env,
            capture_output=True,
            text=True,
            check=False,
        )

    def setup_repo(self, root: Path) -> Path:
        repo = root / "repo"
        repo.mkdir(parents=True, exist_ok=True)

        init = self.run_git(repo, ["init", "--initial-branch", "main"])
        self.assertEqual(init.returncode, 0, msg=init.stderr)

        email = self.run_git(repo, ["config", "user.email", "test@example.com"])
        self.assertEqual(email.returncode, 0, msg=email.stderr)
        name = self.run_git(repo, ["config", "user.name", "Test User"])
        self.assertEqual(name.returncode, 0, msg=name.stderr)
        return repo

    def commit_file(
        self,
        repo: Path,
        relative_path: str,
        content: str,
        *,
        message: str,
        when: str,
    ) -> None:
        path = repo / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

        add = self.run_git(repo, ["add", relative_path])
        self.assertEqual(add.returncode, 0, msg=add.stderr)

        commit_env = {
            "GIT_AUTHOR_DATE": when,
            "GIT_COMMITTER_DATE": when,
        }
        commit = self.run_git(repo, ["commit", "-m", message], env=commit_env)
        self.assertEqual(commit.returncode, 0, msg=commit.stderr)

    def test_default_window_shows_only_last_24_hours(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.setup_repo(Path(tmp))
            self.commit_file(
                repo,
                "old.txt",
                "old\n",
                message="old change",
                when="2026-03-08T09:00:00+00:00",
            )
            self.commit_file(
                repo,
                "note.txt",
                "before\n",
                message="baseline before cutoff",
                when="2026-03-09T10:00:00+00:00",
            )
            self.commit_file(
                repo,
                "note.txt",
                "before\nafter\n",
                message="recent update",
                when="2026-03-10T08:00:00+00:00",
            )
            self.commit_file(
                repo,
                "recent.txt",
                "brand new\n",
                message="recent file",
                when="2026-03-10T09:00:00+00:00",
            )

            result = self.run_cli(repo, [])

            self.assertEqual(result.returncode, 0, msg=result.stderr)
            self.assertIn("diff --git a/note.txt b/note.txt", result.stdout)
            self.assertIn("+after", result.stdout)
            self.assertIn("diff --git a/recent.txt b/recent.txt", result.stdout)
            self.assertNotIn("diff --git a/old.txt b/old.txt", result.stdout)

    def test_custom_window_can_include_older_changes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.setup_repo(Path(tmp))
            self.commit_file(
                repo,
                "baseline.txt",
                "base\n",
                message="baseline",
                when="2026-03-06T09:00:00+00:00",
            )
            self.commit_file(
                repo,
                "weekly.txt",
                "week-old change\n",
                message="within one week",
                when="2026-03-08T15:00:00+00:00",
            )

            default_result = self.run_cli(repo, [])
            self.assertEqual(default_result.returncode, 0, msg=default_result.stderr)
            self.assertNotIn("weekly.txt", default_result.stdout)

            weekly_result = self.run_cli(repo, ["1w"])
            self.assertEqual(weekly_result.returncode, 0, msg=weekly_result.stderr)
            self.assertIn("diff --git a/weekly.txt b/weekly.txt", weekly_result.stdout)

    def test_name_only_lists_each_changed_file_once(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.setup_repo(Path(tmp))
            self.commit_file(
                repo,
                "shared.txt",
                "one\n",
                message="baseline",
                when="2026-03-08T09:00:00+00:00",
            )
            self.commit_file(
                repo,
                "shared.txt",
                "one\ntwo\n",
                message="recent shared update",
                when="2026-03-10T07:00:00+00:00",
            )
            self.commit_file(
                repo,
                "shared.txt",
                "one\ntwo\nthree\n",
                message="second shared update",
                when="2026-03-10T08:00:00+00:00",
            )
            self.commit_file(
                repo,
                "other.txt",
                "other\n",
                message="recent other file",
                when="2026-03-10T09:00:00+00:00",
            )

            result = self.run_cli(repo, ["1w", "--name-only"])

            self.assertEqual(result.returncode, 0, msg=result.stderr)
            self.assertEqual(result.stdout.splitlines(), ["other.txt", "shared.txt"])

    def test_invalid_window_returns_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.setup_repo(Path(tmp))

            result = self.run_cli(repo, ["yesterday"])

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("invalid time window", result.stderr)


if __name__ == "__main__":
    unittest.main()
