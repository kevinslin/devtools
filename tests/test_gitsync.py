from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "bin" / "gitsync"


def run(args: list[str], *, cwd: Path | None = None, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    merged = os.environ.copy()
    if env:
        merged.update(env)
    return subprocess.run(args, cwd=cwd, env=merged, capture_output=True, text=True, check=False)


def git(repo: Path, *args: str) -> str:
    result = run(["git", *args], cwd=repo)
    if result.returncode:
        raise AssertionError(result.stderr)
    return result.stdout.strip()


class GitsyncTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.state = self.root / "state"
        self.remote = self.root / "remote.git"
        git(self.root, "init", "--bare", str(self.remote))
        seed = self.root / "seed"
        git(self.root, "clone", str(self.remote), str(seed))
        git(seed, "config", "user.name", "Test User")
        git(seed, "config", "user.email", "test@example.com")
        (seed / "README.md").write_text("initial\n", encoding="utf-8")
        git(seed, "add", "README.md")
        git(seed, "commit", "-m", "initial")
        git(seed, "branch", "-M", "main")
        git(seed, "push", "-u", "origin", "main")
        git(self.remote, "symbolic-ref", "HEAD", "refs/heads/main")
        self.repo = self.root / "repo"
        git(self.root, "clone", str(self.remote), str(self.repo))
        git(self.repo, "config", "user.name", "Test User")
        git(self.repo, "config", "user.email", "test@example.com")
        self.config = self.root / "agcron.json"
        self.write_config()

    def tearDown(self) -> None:
        self.temp.cleanup()

    def write_config(self, **overrides: object) -> None:
        item = {
            "name": "test",
            "path": str(self.repo),
            "repo": str(self.remote),
            "sync_schedule": "0 * * * *",
        }
        item.update(overrides)
        self.config.write_text(json.dumps({"repos": [item]}), encoding="utf-8")

    def cli(self, *args: str, extra_env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
        env = {"GITSYNC_STATE_DIR": str(self.state)}
        if extra_env:
            env.update(extra_env)
        return run([sys.executable, str(CLI), "--config", str(self.config), *args], env=env)

    def test_validate_accepts_cron_lists_ranges_and_steps(self) -> None:
        self.write_config(sync_schedule="*/15 8-18 * * 1,3,5")
        result = self.cli("validate")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["status"], "valid")

    def test_validate_rejects_invalid_cron_and_extra_fields(self) -> None:
        self.write_config(sync_schedule="60 * * * *")
        result = self.cli("validate")
        self.assertEqual(result.returncode, 2)
        self.assertIn("expected values from 0 through 59", result.stderr)
        raw = json.loads(self.config.read_text())
        raw["repos"][0]["surprise"] = True
        self.config.write_text(json.dumps(raw))
        result = self.cli("validate")
        self.assertEqual(result.returncode, 2)
        self.assertIn("must contain exactly", result.stderr)

    def test_all_pulls_remote_and_pushes_local_commits(self) -> None:
        peer = self.root / "peer"
        git(self.root, "clone", str(self.remote), str(peer))
        git(peer, "config", "user.name", "Test User")
        git(peer, "config", "user.email", "test@example.com")
        (peer / "remote.txt").write_text("remote\n", encoding="utf-8")
        git(peer, "add", "remote.txt")
        git(peer, "commit", "-m", "remote")
        git(peer, "push")
        (self.repo / "local.txt").write_text("local\n", encoding="utf-8")
        git(self.repo, "add", "local.txt")
        git(self.repo, "commit", "-m", "local")

        result = self.cli("sync", "--all")
        self.assertEqual(result.returncode, 0, result.stderr)
        summary = json.loads(result.stdout)
        self.assertTrue(summary["results"][0]["pulled"])
        self.assertIn(summary["results"][0]["push"], ("pushed", "pushed-after-retry"))
        verify = self.root / "verify"
        git(self.root, "clone", str(self.remote), str(verify))
        self.assertTrue((verify / "remote.txt").exists())
        self.assertTrue((verify / "local.txt").exists())

    def test_no_op_sync_still_runs_push_path(self) -> None:
        result = self.cli("sync", "--name", "test")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["results"][0]["push"], "no-op")

    def test_force_manually_syncs_all_repositories_without_force_push(self) -> None:
        result = self.cli("sync", "--force")
        self.assertEqual(result.returncode, 0, result.stderr)
        summary = json.loads(result.stdout)
        self.assertEqual(summary["selected"], 1)
        self.assertEqual(summary["results"][0]["push"], "no-op")

    def test_missing_repository_is_cloned(self) -> None:
        missing = self.root / "missing"
        self.write_config(path=str(missing))
        result = self.cli("sync", "--all")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue((missing / ".git").exists())
        self.assertTrue(json.loads(result.stdout)["results"][0]["cloned"])

    def test_dirty_detached_missing_upstream_and_remote_mismatch_block(self) -> None:
        (self.repo / "dirty").write_text("x", encoding="utf-8")
        result = self.cli("sync", "--all")
        self.assertEqual(result.returncode, 1)
        self.assertIn("dirty worktree", result.stdout)
        (self.repo / "dirty").unlink()

        git(self.repo, "checkout", "--detach")
        result = self.cli("sync", "--all")
        self.assertIn("detached HEAD", result.stdout)
        git(self.repo, "checkout", "main")

        git(self.repo, "branch", "--unset-upstream")
        result = self.cli("sync", "--all")
        self.assertIn("has no upstream", result.stdout)
        git(self.repo, "branch", "--set-upstream-to=origin/main")

        self.write_config(repo=str(self.root / "other.git"))
        result = self.cli("sync", "--all")
        self.assertIn("remote identity mismatch", result.stdout)

        self.write_config(repo=str(self.remote))
        git(self.repo, "remote", "set-url", "--push", "origin", str(self.root / "wrong-push.git"))
        result = self.cli("sync", "--all")
        self.assertIn("origin push", result.stdout)

    def test_concurrent_run_is_blocked(self) -> None:
        digest = __import__("hashlib").sha256(str(self.repo.resolve()).encode()).hexdigest()[:12]
        lock = self.state / "locks" / f"repo-{digest}.lock"
        lock.parent.mkdir(parents=True)
        holder = subprocess.Popen(
            [
                sys.executable,
                "-c",
                "import fcntl,sys,time; f=open(sys.argv[1],'a+'); "
                "fcntl.flock(f.fileno(),fcntl.LOCK_EX); print('locked',flush=True); time.sleep(30)",
                str(lock),
            ],
            stdout=subprocess.PIPE,
            text=True,
        )
        try:
            assert holder.stdout is not None
            self.assertEqual(holder.stdout.readline().strip(), "locked")
            result = self.cli("sync", "--all")
        finally:
            holder.terminate()
            holder.wait(timeout=5)
            if holder.stdout is not None:
                holder.stdout.close()
        self.assertEqual(result.returncode, 1)
        self.assertIn("concurrent sync already running", result.stdout)

    def test_push_targets_upstream_when_local_branch_name_differs(self) -> None:
        git(self.repo, "branch", "-m", "local-name")
        git(self.repo, "branch", "--set-upstream-to=origin/main")
        (self.repo / "local-branch.txt").write_text("local\n", encoding="utf-8")
        git(self.repo, "add", "local-branch.txt")
        git(self.repo, "commit", "-m", "local branch commit")

        result = self.cli("sync", "--all")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(
            git(self.remote, "rev-parse", "refs/heads/main"),
            git(self.repo, "rev-parse", "HEAD"),
        )
        remote_refs = git(
            self.remote,
            "for-each-ref",
            "--format=%(refname)",
            "refs/heads",
        )
        self.assertNotIn("refs/heads/local-name", remote_refs)

    def test_due_claim_runs_once_per_minute(self) -> None:
        now = datetime.now()
        self.write_config(sync_schedule=f"{now.minute} {now.hour} * * *")
        first = self.cli("sync", "--due")
        second = self.cli("sync", "--due")
        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertEqual(json.loads(first.stdout)["selected"], 1)
        self.assertEqual(json.loads(second.stdout)["selected"], 0)

    def test_launchd_plist_uses_due_mode_and_minute_trigger(self) -> None:
        result = self.cli("launchd-plist")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("<integer>60</integer>", result.stdout)
        self.assertIn("<string>--due</string>", result.stdout)
        self.assertIn(str(self.config), result.stdout)

    def test_cron_day_fields_follow_standard_wildcard_and_or_semantics(self) -> None:
        import importlib.machinery
        import importlib.util

        loader = importlib.machinery.SourceFileLoader("gitsync", str(CLI))
        spec = importlib.util.spec_from_loader(loader.name, loader)
        assert spec is not None
        module = importlib.util.module_from_spec(spec)
        sys.modules[loader.name] = module
        loader.exec_module(module)
        monday = datetime(2026, 8, 3, 12, 0)
        self.assertTrue(module.cron_matches("0 12 3 * *", monday))
        self.assertFalse(module.cron_matches("0 12 4 * *", monday))
        self.assertTrue(module.cron_matches("0 12 * * 1", monday))
        self.assertFalse(module.cron_matches("0 12 * * 2", monday))
        self.assertTrue(module.cron_matches("0 12 4 * 1", monday))
        self.assertTrue(module.cron_matches("0 12 3 * 2", monday))
        self.assertFalse(module.cron_matches("0 12 4 * 2", monday))

    def _make_conflict(self) -> None:
        peer = self.root / "conflict-peer"
        git(self.root, "clone", str(self.remote), str(peer))
        git(peer, "config", "user.name", "Test User")
        git(peer, "config", "user.email", "test@example.com")
        (peer / "README.md").write_text("remote intent\n", encoding="utf-8")
        git(peer, "add", "README.md")
        git(peer, "commit", "-m", "remote intent")
        git(peer, "push")
        (self.repo / "README.md").write_text("local intent\n", encoding="utf-8")
        git(self.repo, "add", "README.md")
        git(self.repo, "commit", "-m", "local intent")

    def test_merge_conflict_invokes_codex_and_resumes_sync(self) -> None:
        self._make_conflict()
        record = self.root / "codex-record.json"
        fake = self.root / "fake-codex"
        fake.write_text(
            "#!/usr/bin/env python3\n"
            "import json,os,subprocess,sys\n"
            "from pathlib import Path\n"
            "Path(os.environ['CODEX_RECORD']).write_text(json.dumps({'argv':sys.argv[1:],'cwd':os.getcwd()}))\n"
            "Path('README.md').write_text('local intent\\nremote intent\\n')\n"
            "subprocess.run(['git','add','README.md'],check=True)\n"
            "subprocess.run(['git','commit','--no-edit'],check=True)\n",
            encoding="utf-8",
        )
        fake.chmod(0o755)
        result = self.cli(
            "sync",
            "--all",
            extra_env={"GITSYNC_CODEX_BIN": str(fake), "CODEX_RECORD": str(record)},
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        invocation = json.loads(record.read_text())
        self.assertEqual(invocation["cwd"], str(self.repo.resolve()))
        self.assertEqual(invocation["argv"][0], "exec")
        self.assertIn("Resolve only the current Git merge conflict", invocation["argv"][1])
        verify = self.root / "conflict-verify"
        git(self.root, "clone", str(self.remote), str(verify))
        self.assertEqual((verify / "README.md").read_text(), "local intent\nremote intent\n")

    def test_codex_failure_leaves_exact_conflict_blocker(self) -> None:
        self._make_conflict()
        fake = self.root / "failing-codex"
        fake.write_text("#!/bin/sh\necho unsafe >&2\nexit 42\n", encoding="utf-8")
        fake.chmod(0o755)
        result = self.cli("sync", "--all", extra_env={"GITSYNC_CODEX_BIN": str(fake)})
        self.assertEqual(result.returncode, 1)
        self.assertIn("Codex could not safely resolve sync conflict: unsafe", result.stdout)
        self.assertTrue(git(self.repo, "diff", "--name-only", "--diff-filter=U"))


if __name__ == "__main__":
    unittest.main()
