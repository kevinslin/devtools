from __future__ import annotations

from datetime import datetime, timedelta
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "bin" / "ag-man"


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row))
            handle.write("\n")


class AgManCliTest(unittest.TestCase):
    def run_cli(self, env_updates: dict[str, str], args: list[str] | None = None) -> subprocess.CompletedProcess[str]:
        env = os.environ.copy()
        env.update(env_updates)
        return subprocess.run(
            [sys.executable, str(CLI), *(args or [])],
            cwd=ROOT,
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )

    def test_reports_today_started_sessions_with_active_and_inactive_status(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            ledger_root = tmp_path / "ag-ledger"
            today = datetime.now()
            yesterday = today - timedelta(days=1)

            today_path = ledger_root / "data" / f"ledger-{today.strftime('%Y-%m-%d')}.md"
            yesterday_path = ledger_root / "data" / f"ledger-{yesterday.strftime('%Y-%m-%d')}.md"

            _write_jsonl(
                yesterday_path,
                [
                    {
                        "time": yesterday.replace(hour=9, minute=0).strftime("%Y-%m-%d %H:%M"),
                        "workspace": "/repo/old",
                        "session": "old-session",
                        "msg": "session start: old work",
                    }
                ],
            )
            _write_jsonl(
                today_path,
                [
                    {
                        "time": today.replace(hour=9, minute=0).strftime("%Y-%m-%d %H:%M"),
                        "workspace": "/repo/a",
                        "session": "session-a",
                        "msg": "session start: first task",
                    },
                    {
                        "time": today.replace(hour=9, minute=10).strftime("%Y-%m-%d %H:%M"),
                        "workspace": "/repo/a",
                        "session": "session-a",
                        "msg": "notable change: implemented something",
                    },
                    {
                        "time": today.replace(hour=9, minute=20).strftime("%Y-%m-%d %H:%M"),
                        "workspace": "/repo/b",
                        "session": "session-b",
                        "msg": "SESSION START: second task",
                    },
                    {
                        "time": today.replace(hour=9, minute=25).strftime("%Y-%m-%d %H:%M"),
                        "workspace": "/repo/b",
                        "session": "session-b",
                        "msg": "session start: duplicate start should dedupe",
                    },
                ],
            )

            ps_fixture = tmp_path / "ps.txt"
            ps_fixture.write_text(
                "\n".join(
                    [
                        "200 100 ttys010 /bin/zsh",
                        "300 200 ?? codex --resume session-a",
                        "400 1 ?? python unrelated.py",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            tmux_fixture = tmp_path / "tmux.txt"
            tmux_fixture.write_text("dev\t1:agents\t0\t%60\t999\t/dev/ttys010\n", encoding="utf-8")

            result = self.run_cli(
                {
                    "META_LEDGER_ROOT": str(ledger_root),
                    "AG_MAN_PS_OUTPUT_FILE": str(ps_fixture),
                    "AG_MAN_TMUX_OUTPUT_FILE": str(tmux_fixture),
                }
            )

            self.assertEqual(result.returncode, 0, msg=result.stderr)
            rows = [json.loads(line) for line in result.stdout.splitlines() if line.strip()]
            self.assertEqual([row["agent_session"] for row in rows], ["session-a", "session-b"])

            first = rows[0]
            self.assertEqual(first["workspace"], "/repo/a")
            self.assertEqual(first["status"], "active")
            self.assertEqual(first["pid"], 300)
            self.assertEqual(first["tmux_session"], "dev")
            self.assertEqual(first["tmux_window"], "1:agents")
            self.assertEqual(first["tmux_pane"], 0)
            self.assertEqual(first["tmux_pane_id"], 60)

            second = rows[1]
            self.assertEqual(second["workspace"], "/repo/b")
            self.assertEqual(second["status"], "inactive")
            self.assertIsNone(second["pid"])
            self.assertIsNone(second["tmux_session"])
            self.assertIsNone(second["tmux_window"])
            self.assertIsNone(second["tmux_pane"])
            self.assertIsNone(second["tmux_pane_id"])

    def test_missing_today_ledger_returns_no_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result = self.run_cli({"META_LEDGER_ROOT": tmp})
            self.assertEqual(result.returncode, 0, msg=result.stderr)
            self.assertEqual(result.stdout.strip(), "")

    def test_filter_by_status_and_pid(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            ledger_root = tmp_path / "ag-ledger"
            today = datetime.now()
            today_path = ledger_root / "data" / f"ledger-{today.strftime('%Y-%m-%d')}.md"

            _write_jsonl(
                today_path,
                [
                    {
                        "time": today.replace(hour=9, minute=0).strftime("%Y-%m-%d %H:%M"),
                        "workspace": "/repo/a",
                        "session": "session-a",
                        "msg": "session start: first task",
                    },
                    {
                        "time": today.replace(hour=9, minute=1).strftime("%Y-%m-%d %H:%M"),
                        "workspace": "/repo/b",
                        "session": "session-b",
                        "msg": "session start: second task",
                    },
                ],
            )

            ps_fixture = tmp_path / "ps.txt"
            ps_fixture.write_text("300 1 ttys010 codex --resume session-a\n", encoding="utf-8")
            tmux_fixture = tmp_path / "tmux.txt"
            tmux_fixture.write_text("dev\t1:agents\t0\t%60\t999\t/dev/ttys010\n", encoding="utf-8")

            base_env = {
                "META_LEDGER_ROOT": str(ledger_root),
                "AG_MAN_PS_OUTPUT_FILE": str(ps_fixture),
                "AG_MAN_TMUX_OUTPUT_FILE": str(tmux_fixture),
            }

            result = self.run_cli(base_env, args=["--filter", "status=active"])
            self.assertEqual(result.returncode, 0, msg=result.stderr)
            rows = [json.loads(line) for line in result.stdout.splitlines() if line.strip()]
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["agent_session"], "session-a")

            result = self.run_cli(base_env, args=["--filter", "status=active", "--filter", "pid=300"])
            self.assertEqual(result.returncode, 0, msg=result.stderr)
            rows = [json.loads(line) for line in result.stdout.splitlines() if line.strip()]
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["pid"], 300)

            result = self.run_cli(base_env, args=["--filter", "tmux_pane_id=60"])
            self.assertEqual(result.returncode, 0, msg=result.stderr)
            rows = [json.loads(line) for line in result.stdout.splitlines() if line.strip()]
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["agent_session"], "session-a")

            result = self.run_cli(base_env, args=["--filter", "pid=null"])
            self.assertEqual(result.returncode, 0, msg=result.stderr)
            rows = [json.loads(line) for line in result.stdout.splitlines() if line.strip()]
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["agent_session"], "session-b")

    def test_filter_rejects_invalid_key(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result = self.run_cli({"META_LEDGER_ROOT": tmp}, args=["--filter", "badkey=value"])
            self.assertEqual(result.returncode, 2)
            self.assertIn("invalid --filter key", result.stderr)

    def test_group_by_workspace_outputs_workspace_buckets(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            ledger_root = tmp_path / "ag-ledger"
            today = datetime.now()
            today_path = ledger_root / "data" / f"ledger-{today.strftime('%Y-%m-%d')}.md"

            _write_jsonl(
                today_path,
                [
                    {
                        "time": today.replace(hour=9, minute=0).strftime("%Y-%m-%d %H:%M"),
                        "workspace": "/repo/a",
                        "session": "session-a1",
                        "msg": "session start: a1",
                    },
                    {
                        "time": today.replace(hour=9, minute=1).strftime("%Y-%m-%d %H:%M"),
                        "workspace": "/repo/b",
                        "session": "session-b1",
                        "msg": "session start: b1",
                    },
                    {
                        "time": today.replace(hour=9, minute=2).strftime("%Y-%m-%d %H:%M"),
                        "workspace": "/repo/a",
                        "session": "session-a2",
                        "msg": "session start: a2",
                    },
                ],
            )

            ps_fixture = tmp_path / "ps.txt"
            ps_fixture.write_text(
                "\n".join(
                    [
                        "300 1 ttys010 codex --resume session-a1",
                        "301 1 ttys011 codex --resume session-b1",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            tmux_fixture = tmp_path / "tmux.txt"
            tmux_fixture.write_text(
                "\n".join(
                    [
                        "dev\t1:agents\t0\t%60\t999\t/dev/ttys010",
                        "dev\t2:agents\t1\t%61\t998\t/dev/ttys011",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            result = self.run_cli(
                {
                    "META_LEDGER_ROOT": str(ledger_root),
                    "AG_MAN_PS_OUTPUT_FILE": str(ps_fixture),
                    "AG_MAN_TMUX_OUTPUT_FILE": str(tmux_fixture),
                },
                args=["--group-by", "workspace"],
            )

            self.assertEqual(result.returncode, 0, msg=result.stderr)
            rows = [json.loads(line) for line in result.stdout.splitlines() if line.strip()]
            self.assertEqual([row["workspace"] for row in rows], ["/repo/a", "/repo/b"])
            self.assertEqual(len(rows[0]["sessions"]), 2)
            self.assertEqual([s["agent_session"] for s in rows[0]["sessions"]], ["session-a1", "session-a2"])
            self.assertEqual(rows[0]["sessions"][0]["status"], "active")
            self.assertEqual(rows[0]["sessions"][1]["status"], "inactive")
            self.assertEqual(len(rows[1]["sessions"]), 1)
            self.assertEqual(rows[1]["sessions"][0]["agent_session"], "session-b1")

    def test_group_by_applies_after_filters(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            ledger_root = tmp_path / "ag-ledger"
            today = datetime.now()
            today_path = ledger_root / "data" / f"ledger-{today.strftime('%Y-%m-%d')}.md"

            _write_jsonl(
                today_path,
                [
                    {
                        "time": today.replace(hour=9, minute=0).strftime("%Y-%m-%d %H:%M"),
                        "workspace": "/repo/a",
                        "session": "session-a",
                        "msg": "session start: a",
                    },
                    {
                        "time": today.replace(hour=9, minute=1).strftime("%Y-%m-%d %H:%M"),
                        "workspace": "/repo/b",
                        "session": "session-b",
                        "msg": "session start: b",
                    },
                ],
            )

            ps_fixture = tmp_path / "ps.txt"
            ps_fixture.write_text("300 1 ttys010 codex --resume session-a\n", encoding="utf-8")
            tmux_fixture = tmp_path / "tmux.txt"
            tmux_fixture.write_text("dev\t1:agents\t0\t%60\t999\t/dev/ttys010\n", encoding="utf-8")

            result = self.run_cli(
                {
                    "META_LEDGER_ROOT": str(ledger_root),
                    "AG_MAN_PS_OUTPUT_FILE": str(ps_fixture),
                    "AG_MAN_TMUX_OUTPUT_FILE": str(tmux_fixture),
                },
                args=["--filter", "status=active", "--group-by", "workspace"],
            )

            self.assertEqual(result.returncode, 0, msg=result.stderr)
            rows = [json.loads(line) for line in result.stdout.splitlines() if line.strip()]
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["workspace"], "/repo/a")
            self.assertEqual(len(rows[0]["sessions"]), 1)
            self.assertEqual(rows[0]["sessions"][0]["agent_session"], "session-a")

    def test_uses_codex_sqlite_logs_to_map_uuid_session_to_active_pid(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            ledger_root = tmp_path / "ag-ledger"
            today = datetime.now()
            today_path = ledger_root / "data" / f"ledger-{today.strftime('%Y-%m-%d')}.md"
            session_id = "019c87a8-1007-7141-a708-7963077d9383"

            _write_jsonl(
                today_path,
                [
                    {
                        "time": today.replace(hour=10, minute=0).strftime("%Y-%m-%d %H:%M"),
                        "workspace": "/Users/kevinlin",
                        "session": session_id,
                        "msg": "session start - active codex thread",
                    }
                ],
            )

            db_path = tmp_path / "state_5.sqlite"
            conn = sqlite3.connect(db_path)
            try:
                conn.execute(
                    """
                    CREATE TABLE logs (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        ts INTEGER NOT NULL,
                        ts_nanos INTEGER NOT NULL,
                        level TEXT NOT NULL,
                        target TEXT NOT NULL,
                        message TEXT,
                        module_path TEXT,
                        file TEXT,
                        line INTEGER,
                        thread_id TEXT,
                        process_uuid TEXT,
                        estimated_bytes INTEGER NOT NULL DEFAULT 0
                    )
                    """
                )
                conn.execute(
                    """
                    INSERT INTO logs (ts, ts_nanos, level, target, thread_id, process_uuid, estimated_bytes)
                    VALUES (?, 0, 'INFO', 'test', ?, ?, 0)
                    """,
                    (int(today.timestamp()), session_id, "pid:37860:worker-uuid"),
                )
                conn.commit()
            finally:
                conn.close()

            ps_fixture = tmp_path / "ps.txt"
            ps_fixture.write_text(
                "\n".join(
                    [
                        "111 1 ttys028 /bin/zsh",
                        "37860 111 ttys028 /Users/kevinlin/.cache/codex/codex --profile xxhigh",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            tmux_fixture = tmp_path / "tmux.txt"
            tmux_fixture.write_text("0\t3:workshop\t0\t%32\t73569\t/dev/ttys028\n", encoding="utf-8")

            result = self.run_cli(
                {
                    "META_LEDGER_ROOT": str(ledger_root),
                    "AG_MAN_CODEX_STATE_DB": str(db_path),
                    "AG_MAN_PS_OUTPUT_FILE": str(ps_fixture),
                    "AG_MAN_TMUX_OUTPUT_FILE": str(tmux_fixture),
                }
            )

            self.assertEqual(result.returncode, 0, msg=result.stderr)
            rows = [json.loads(line) for line in result.stdout.splitlines() if line.strip()]
            self.assertEqual(len(rows), 1)
            row = rows[0]
            self.assertEqual(row["agent_session"], session_id)
            self.assertEqual(row["status"], "active")
            self.assertEqual(row["pid"], 37860)
            self.assertEqual(row["tmux_session"], "0")
            self.assertEqual(row["tmux_window"], "3:workshop")
            self.assertEqual(row["tmux_pane"], 0)
            self.assertEqual(row["tmux_pane_id"], 32)

    def test_resolves_ag_ledger_alias_to_codex_thread_uuid(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            ledger_root = tmp_path / "ag-ledger"
            today = datetime.now()
            today_path = ledger_root / "data" / f"ledger-{today.strftime('%Y-%m-%d')}.md"
            alias_session = "codex-20260223-sc-opt-confirm-policy"
            thread_uuid = "019c87a8-1007-7141-a708-7963077d9383"

            _write_jsonl(
                today_path,
                [
                    {
                        "time": today.replace(hour=11, minute=0).strftime("%Y-%m-%d %H:%M"),
                        "workspace": "/Users/kevinlin",
                        "session": alias_session,
                        "msg": "session start: alias-based ledger session",
                    }
                ],
            )

            db_path = tmp_path / "state_5.sqlite"
            conn = sqlite3.connect(db_path)
            try:
                conn.execute(
                    """
                    CREATE TABLE logs (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        ts INTEGER NOT NULL,
                        ts_nanos INTEGER NOT NULL,
                        level TEXT NOT NULL,
                        target TEXT NOT NULL,
                        message TEXT,
                        module_path TEXT,
                        file TEXT,
                        line INTEGER,
                        thread_id TEXT,
                        process_uuid TEXT,
                        estimated_bytes INTEGER NOT NULL DEFAULT 0
                    )
                    """
                )
                now_ts = int(today.timestamp())
                conn.execute(
                    """
                    INSERT INTO logs (ts, ts_nanos, level, target, message, thread_id, estimated_bytes)
                    VALUES (?, 0, 'INFO', 'test', ?, ?, 0)
                    """,
                    (
                        now_ts,
                        f'ToolCall: exec_command {{"cmd":"ag-ledger append {alias_session} \\"session start: alias-based ledger session\\""}}',
                        thread_uuid,
                    ),
                )
                conn.execute(
                    """
                    INSERT INTO logs (ts, ts_nanos, level, target, thread_id, process_uuid, estimated_bytes)
                    VALUES (?, 0, 'INFO', 'test', ?, ?, 0)
                    """,
                    (now_ts + 1, thread_uuid, "pid:12345:worker-uuid"),
                )
                conn.commit()
            finally:
                conn.close()

            ps_fixture = tmp_path / "ps.txt"
            ps_fixture.write_text("12345 1 ttys099 /Users/kevinlin/.cache/codex/codex --profile xxhigh\n", encoding="utf-8")
            tmux_fixture = tmp_path / "tmux.txt"
            tmux_fixture.write_text("2\t1:codex\t0\t%88\t999\t/dev/ttys099\n", encoding="utf-8")

            result = self.run_cli(
                {
                    "META_LEDGER_ROOT": str(ledger_root),
                    "AG_MAN_CODEX_STATE_DB": str(db_path),
                    "AG_MAN_PS_OUTPUT_FILE": str(ps_fixture),
                    "AG_MAN_TMUX_OUTPUT_FILE": str(tmux_fixture),
                }
            )

            self.assertEqual(result.returncode, 0, msg=result.stderr)
            rows = [json.loads(line) for line in result.stdout.splitlines() if line.strip()]
            self.assertEqual(len(rows), 1)
            row = rows[0]
            self.assertEqual(row["agent_session"], thread_uuid)
            self.assertEqual(row["status"], "active")
            self.assertEqual(row["pid"], 12345)


if __name__ == "__main__":
    unittest.main()
