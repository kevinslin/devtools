from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "bin" / "agent-sync"


def _run(cmd: list[str], *, cwd: Path | None = None, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    merged_env = os.environ.copy()
    if env:
        merged_env.update(env)
    return subprocess.run(
        cmd,
        cwd=cwd,
        env=merged_env,
        capture_output=True,
        text=True,
        check=False,
    )


def _git(repo: Path, *args: str) -> str:
    proc = _run(["git", *args], cwd=repo)
    if proc.returncode != 0:
        raise AssertionError(f"git {' '.join(args)} failed:\nSTDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}")
    return proc.stdout.strip()


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _write_config(path: Path, *, source_dir: Path, repo_dir: Path, bootstrap: str, paths: list[str], state_file: Path) -> None:
    payload = {
        "source_dir": str(source_dir),
        "repo_dir": str(repo_dir),
        "bootstrap": bootstrap,
        "paths": paths,
        "state_file": str(state_file),
        "branch": "main",
        "remote": "origin",
        "git_author_name": "Agent Sync",
        "git_author_email": "agent-sync@example.com",
    }
    _write(path, json.dumps(payload, indent=2) + "\n")


class AgentSyncCliTest(unittest.TestCase):
    def run_cli_args(
        self,
        *args: str,
        cwd: Path | None = None,
        env: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        return _run([sys.executable, str(CLI), *args], cwd=cwd or ROOT, env=env)

    def run_cli(self, config_path: Path, *extra_args: str) -> subprocess.CompletedProcess[str]:
        return self.run_cli_args(*extra_args, str(config_path))

    def _create_remote_and_clone(self, tmp_path: Path) -> tuple[Path, Path]:
        remote = tmp_path / "remote.git"
        repo_dir = tmp_path / "repo"
        seed = tmp_path / "seed"

        _run(["git", "init", "--bare", "--initial-branch=main", str(remote)])
        _run(["git", "clone", str(remote), str(seed)])
        _git(seed, "config", "user.name", "Test User")
        _git(seed, "config", "user.email", "test@example.com")
        _write(seed / ".gitkeep", "seed\n")
        _git(seed, "add", ".")
        _git(seed, "commit", "-m", "seed")
        _git(seed, "push", "origin", "main")
        _run(["git", "clone", "--branch", "main", str(remote), str(repo_dir)])
        _git(repo_dir, "config", "user.name", "Test User")
        _git(repo_dir, "config", "user.email", "test@example.com")
        return remote, repo_dir

    def test_bootstrap_from_source_commits_local_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            remote, repo_dir = self._create_remote_and_clone(tmp_path)
            source_dir = tmp_path / "source"
            state_file = tmp_path / "state" / "sync.json"
            config_path = tmp_path / "config.json"

            _write(source_dir / "config/settings.json", '{"theme":"light"}\n')
            _write(source_dir / "prompts/system.txt", "You are local.\n")
            _write_config(
                config_path,
                source_dir=source_dir,
                repo_dir=repo_dir,
                bootstrap="source",
                paths=["config", "prompts"],
                state_file=state_file,
            )

            result = self.run_cli(config_path)
            self.assertEqual(result.returncode, 0, msg=result.stderr)
            summary = json.loads(result.stdout)
            self.assertEqual(summary["bootstrap"], "source")
            self.assertCountEqual(summary["source_to_repo"], ["config/settings.json", "prompts/system.txt"])

            verify = tmp_path / "verify"
            _run(["git", "clone", "--branch", "main", str(remote), str(verify)])
            self.assertEqual((verify / "config/settings.json").read_text(encoding="utf-8"), '{"theme":"light"}\n')
            self.assertEqual((verify / "prompts/system.txt").read_text(encoding="utf-8"), "You are local.\n")

            state = json.loads(state_file.read_text(encoding="utf-8"))
            self.assertIn("config/settings.json", state["snapshot"])
            self.assertIn("prompts/system.txt", state["snapshot"])
            self.assertFalse(summary["dry_run"])

    def test_dry_run_reports_changes_without_writing_repo_or_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            remote, repo_dir = self._create_remote_and_clone(tmp_path)
            source_dir = tmp_path / "source"
            state_file = tmp_path / "state" / "sync.json"
            config_path = tmp_path / "config.json"

            _write(source_dir / "config/settings.json", '{"theme":"light"}\n')
            _write_config(
                config_path,
                source_dir=source_dir,
                repo_dir=repo_dir,
                bootstrap="source",
                paths=["config"],
                state_file=state_file,
            )

            initial = self.run_cli(config_path)
            self.assertEqual(initial.returncode, 0, msg=initial.stderr)
            original_state = state_file.read_text(encoding="utf-8")

            _write(source_dir / "config/settings.json", '{"theme":"dark"}\n')

            result = self.run_cli(config_path, "--dry-run")
            self.assertEqual(result.returncode, 0, msg=result.stderr)
            summary = json.loads(result.stdout)
            self.assertTrue(summary["dry_run"])
            self.assertFalse(summary["pushed"])
            self.assertEqual(summary["source_to_repo"], ["config/settings.json"])
            self.assertEqual(summary["repo_to_source"], [])

            self.assertEqual((repo_dir / "config/settings.json").read_text(encoding="utf-8"), '{"theme":"light"}\n')
            self.assertEqual(state_file.read_text(encoding="utf-8"), original_state)

            verify = tmp_path / "verify"
            _run(["git", "clone", "--branch", "main", str(remote), str(verify)])
            self.assertEqual((verify / "config/settings.json").read_text(encoding="utf-8"), '{"theme":"light"}\n')

    def test_init_writes_codex_defaults_in_current_directory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            home = tmp_path / "home"
            repo_dir = tmp_path / "repo"
            home.mkdir()
            repo_dir.mkdir()

            result = self.run_cli_args("init", cwd=repo_dir, env={"HOME": str(home)})
            self.assertEqual(result.returncode, 0, msg=result.stderr)
            summary = json.loads(result.stdout)
            self.assertEqual(summary["status"], "initialized")

            config_path = repo_dir / "agent-sync.json"
            self.assertTrue(config_path.exists())

            payload = json.loads(config_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["source_dir"], str(home / ".codex"))
            self.assertEqual(payload["repo_dir"], str(repo_dir.resolve()))
            self.assertEqual(payload["bootstrap"], "source")
            self.assertEqual(
                payload["paths"],
                ["AGENTS.md", "agents", "automations", "config.toml", "memories", "rules", "skills"],
            )

    def test_init_refuses_to_overwrite_existing_config_without_force(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            repo_dir = tmp_path / "repo"
            repo_dir.mkdir()
            existing = repo_dir / "agent-sync.json"
            _write(existing, '{"keep":"me"}\n')

            result = self.run_cli_args("init", cwd=repo_dir)
            self.assertEqual(result.returncode, 2)
            self.assertIn("config already exists", result.stderr)
            self.assertEqual(existing.read_text(encoding="utf-8"), '{"keep":"me"}\n')

    def test_bootstrap_from_repo_populates_empty_source(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            remote, repo_dir = self._create_remote_and_clone(tmp_path)
            source_dir = tmp_path / "source"
            state_file = tmp_path / "state" / "sync.json"
            config_path = tmp_path / "config.json"

            peer = tmp_path / "peer"
            _run(["git", "clone", "--branch", "main", str(remote), str(peer)])
            _git(peer, "config", "user.name", "Test User")
            _git(peer, "config", "user.email", "test@example.com")
            _write(peer / "profiles/default.toml", 'model = "gpt-5"\n')
            _git(peer, "add", ".")
            _git(peer, "commit", "-m", "add profile")
            _git(peer, "push", "origin", "main")

            _write_config(
                config_path,
                source_dir=source_dir,
                repo_dir=repo_dir,
                bootstrap="repo",
                paths=["profiles"],
                state_file=state_file,
            )

            result = self.run_cli(config_path)
            self.assertEqual(result.returncode, 0, msg=result.stderr)
            summary = json.loads(result.stdout)
            self.assertEqual(summary["bootstrap"], "repo")
            self.assertEqual(summary["repo_to_source"], ["profiles/default.toml"])
            self.assertFalse(summary["dry_run"])
            self.assertEqual((source_dir / "profiles/default.toml").read_text(encoding="utf-8"), 'model = "gpt-5"\n')

    def test_non_overlapping_changes_merge_in_both_directions(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            remote, repo_dir = self._create_remote_and_clone(tmp_path)
            source_dir = tmp_path / "source"
            state_file = tmp_path / "state" / "sync.json"
            config_path = tmp_path / "config.json"

            peer = tmp_path / "peer"
            _run(["git", "clone", "--branch", "main", str(remote), str(peer)])
            _git(peer, "config", "user.name", "Test User")
            _git(peer, "config", "user.email", "test@example.com")
            _write(peer / "config/a.txt", "base-a\n")
            _write(peer / "config/b.txt", "base-b\n")
            _git(peer, "add", ".")
            _git(peer, "commit", "-m", "add base config")
            _git(peer, "push", "origin", "main")

            _write_config(
                config_path,
                source_dir=source_dir,
                repo_dir=repo_dir,
                bootstrap="repo",
                paths=["config"],
                state_file=state_file,
            )
            initial = self.run_cli(config_path)
            self.assertEqual(initial.returncode, 0, msg=initial.stderr)

            _write(source_dir / "config/a.txt", "local-a\n")
            _write(peer / "config/b.txt", "remote-b\n")
            _git(peer, "add", ".")
            _git(peer, "commit", "-m", "remote change to b")
            _git(peer, "push", "origin", "main")

            result = self.run_cli(config_path)
            self.assertEqual(result.returncode, 0, msg=result.stderr)
            summary = json.loads(result.stdout)
            self.assertEqual(summary["source_to_repo"], ["config/a.txt"])
            self.assertEqual(summary["repo_to_source"], ["config/b.txt"])
            self.assertFalse(summary["dry_run"])
            self.assertEqual((source_dir / "config/a.txt").read_text(encoding="utf-8"), "local-a\n")
            self.assertEqual((source_dir / "config/b.txt").read_text(encoding="utf-8"), "remote-b\n")

            verify = tmp_path / "verify"
            _run(["git", "clone", "--branch", "main", str(remote), str(verify)])
            self.assertEqual((verify / "config/a.txt").read_text(encoding="utf-8"), "local-a\n")
            self.assertEqual((verify / "config/b.txt").read_text(encoding="utf-8"), "remote-b\n")

    def test_same_file_conflict_returns_exit_code_1(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            remote, repo_dir = self._create_remote_and_clone(tmp_path)
            source_dir = tmp_path / "source"
            state_file = tmp_path / "state" / "sync.json"
            config_path = tmp_path / "config.json"

            peer = tmp_path / "peer"
            _run(["git", "clone", "--branch", "main", str(remote), str(peer)])
            _git(peer, "config", "user.name", "Test User")
            _git(peer, "config", "user.email", "test@example.com")
            _write(peer / "config/shared.txt", "base\n")
            _git(peer, "add", ".")
            _git(peer, "commit", "-m", "add base file")
            _git(peer, "push", "origin", "main")

            _write_config(
                config_path,
                source_dir=source_dir,
                repo_dir=repo_dir,
                bootstrap="repo",
                paths=["config"],
                state_file=state_file,
            )
            initial = self.run_cli(config_path)
            self.assertEqual(initial.returncode, 0, msg=initial.stderr)

            _write(source_dir / "config/shared.txt", "local\n")
            _write(peer / "config/shared.txt", "remote\n")
            _git(peer, "add", ".")
            _git(peer, "commit", "-m", "remote edit")
            _git(peer, "push", "origin", "main")

            result = self.run_cli(config_path)
            self.assertEqual(result.returncode, 1)
            self.assertIn("config/shared.txt", result.stderr)
            self.assertEqual((source_dir / "config/shared.txt").read_text(encoding="utf-8"), "local\n")


if __name__ == "__main__":
    unittest.main()
