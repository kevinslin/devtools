from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest


ROOT = Path(__file__).resolve().parents[1]
HOOK = ROOT / "tools" / "gitsync" / "scripts" / "supervisor-sync"
PROGRAM = "kevinlin-gitsync"


class SupervisorSyncTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.home = Path(self.temporary_directory.name)
        self.config = self.home / ".config" / "supervisor" / "supervisord.conf"
        self.config.parent.mkdir(parents=True)
        self.config.write_text("[supervisord]\n", encoding="utf-8")
        self.state = self.home / "state"
        self.calls = self.home / "supervisorctl.jsonl"
        self.bin = self.home / "bin"
        self.bin.mkdir()
        self.authorization = "synthetic-authorization-fixture"
        supervisorctl = self.bin / "supervisorctl"
        supervisorctl.write_text(
            f"#!{sys.executable}\n"
            "import json\n"
            "import os\n"
            "from pathlib import Path\n"
            "import sys\n"
            "args = sys.argv[1:]\n"
            "operation = args[2] if len(args) > 2 else ''\n"
            "record = {\n"
            "    'args': args,\n"
            "    'authorization_inherited': bool(os.environ.get('GITSYNC_TEST_AUTHORIZATION')),\n"
            "    'parent_pid': os.getppid(),\n"
            "    'session_id': os.getsid(0),\n"
            "}\n"
            "calls_path = Path(os.environ['FAKE_SUPERVISOR_CALLS'])\n"
            "if operation == 'update':\n"
            "    previous = [json.loads(line) for line in calls_path.read_text().splitlines()]\n"
            "    hook_pid = next(call['parent_pid'] for call in previous if call['args'][2] == 'reread')\n"
            "    try:\n"
            "        os.kill(hook_pid, 0)\n"
            "    except ProcessLookupError:\n"
            "        record['hook_still_running'] = False\n"
            "    except PermissionError:\n"
            "        record['hook_still_running'] = True\n"
            "    else:\n"
            "        record['hook_still_running'] = True\n"
            "with calls_path.open('a', encoding='utf-8') as stream:\n"
            "    stream.write(json.dumps(record) + '\\n')\n"
            "prefix = 'FAKE_SUPERVISOR_' + operation.upper()\n"
            "output = os.environ.get(prefix + '_OUTPUT', '')\n"
            "error = os.environ.get(prefix + '_ERROR', '')\n"
            "if output:\n"
            "    print(output)\n"
            "if error:\n"
            "    print(error, file=sys.stderr)\n"
            "sys.exit(int(os.environ.get(prefix + '_EXIT', '0')))\n",
            encoding="utf-8",
        )
        supervisorctl.chmod(0o755)

    def invoke(
        self,
        *,
        platform: str = "linux",
        extra_env: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        env = os.environ.copy()
        env.update(
            {
                "HOME": str(self.home),
                "PATH": str(self.bin) + os.pathsep + env.get("PATH", ""),
                "XDG_STATE_HOME": str(self.state),
                "FAKE_SUPERVISOR_CALLS": str(self.calls),
                "GITSYNC_TEST_AUTHORIZATION": self.authorization,
            }
        )
        if extra_env:
            env.update(extra_env)
        wrapper = (
            "import runpy,sys; "
            "sys.platform=sys.argv[1]; "
            "script=sys.argv[2]; "
            "sys.argv=[script]; "
            "runpy.run_path(script,run_name='__main__')"
        )
        return subprocess.run(
            [sys.executable, "-c", wrapper, platform, str(HOOK)],
            env=env,
            capture_output=True,
            text=True,
            check=False,
            timeout=3,
        )

    def recorded_calls(self) -> list[dict[str, object]]:
        if not self.calls.exists():
            return []
        return [json.loads(line) for line in self.calls.read_text(encoding="utf-8").splitlines()]

    def wait_for_calls(self, count: int) -> list[dict[str, object]]:
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            calls = self.recorded_calls()
            if len(calls) >= count:
                return calls
            time.sleep(0.02)
        self.fail(f"timed out waiting for {count} supervisor calls: {self.recorded_calls()!r}")

    def test_non_linux_does_not_touch_supervisor(self) -> None:
        result = self.invoke(platform="darwin")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.recorded_calls(), [])

    def test_unchanged_configuration_only_rereads(self) -> None:
        result = self.invoke(
            extra_env={"FAKE_SUPERVISOR_REREAD_OUTPUT": "No config updates to processes"}
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            [call["args"] for call in self.recorded_calls()],
            [["-c", str(self.config), "reread"]],
        )

    def test_unrelated_changes_and_similar_program_names_never_update(self) -> None:
        result = self.invoke(
            extra_env={
                "FAKE_SUPERVISOR_REREAD_OUTPUT": (
                    "unrelated-service: changed\n"
                    "kevinlin-gitsync-backup: changed\n"
                    "kevinlin-gitsync: removed"
                )
            }
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            [call["args"] for call in self.recorded_calls()],
            [["-c", str(self.config), "reread"]],
        )

    def test_changed_program_updates_only_exact_group_after_hook_exits(self) -> None:
        result = self.invoke(
            extra_env={
                "FAKE_SUPERVISOR_REREAD_OUTPUT": (
                    "unrelated-service: changed\nkevinlin-gitsync: changed\nother: available"
                )
            }
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        calls = self.wait_for_calls(2)
        self.assertEqual(
            [call["args"] for call in calls],
            [
                ["-c", str(self.config), "reread"],
                ["-c", str(self.config), "update", PROGRAM],
            ],
        )
        self.assertFalse(calls[1]["hook_still_running"])
        self.assertNotEqual(calls[0]["session_id"], calls[1]["session_id"])
        self.assertTrue(all(call["authorization_inherited"] for call in calls))
        self.assertNotIn(self.authorization, result.stdout + result.stderr)

    def test_reread_failures_surface_without_updating_any_group(self) -> None:
        result = self.invoke(
            extra_env={
                "FAKE_SUPERVISOR_REREAD_ERROR": "fixture supervisor socket unavailable",
                "FAKE_SUPERVISOR_REREAD_EXIT": "23",
            }
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("fixture supervisor socket unavailable", result.stderr)
        self.assertEqual(
            [call["args"] for call in self.recorded_calls()],
            [["-c", str(self.config), "reread"]],
        )
        self.assertNotIn(self.authorization, result.stdout + result.stderr)

    def test_detached_update_failures_are_recorded_without_exposing_authorization(self) -> None:
        result = self.invoke(
            extra_env={
                "FAKE_SUPERVISOR_REREAD_OUTPUT": "kevinlin-gitsync: changed",
                "FAKE_SUPERVISOR_UPDATE_ERROR": "fixture targeted update rejected",
                "FAKE_SUPERVISOR_UPDATE_EXIT": "29",
            }
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.wait_for_calls(2)
        log_path = self.state / "gitsync" / "supervisor-sync.log"
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            if log_path.exists():
                contents = log_path.read_text(encoding="utf-8")
                if "fixture targeted update rejected" in contents:
                    self.assertNotIn(self.authorization, contents)
                    break
            time.sleep(0.02)
        else:
            contents = log_path.read_text(encoding="utf-8") if log_path.exists() else ""
            self.fail(f"detached update failure was not recorded in {log_path}: {contents!r}")


if __name__ == "__main__":
    unittest.main()
