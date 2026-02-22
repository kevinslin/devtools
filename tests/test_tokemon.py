from __future__ import annotations

import csv
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "bin" / "tokemon"


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row))
            handle.write("\n")


class TokemonCliTest(unittest.TestCase):
    def run_cli(self, args: list[str], env_updates: dict[str, str]) -> subprocess.CompletedProcess[str]:
        env = os.environ.copy()
        env.update(env_updates)
        return subprocess.run(
            [sys.executable, str(CLI), *args],
            cwd=ROOT,
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )

    def test_codex_report_csv_with_workspace_grouping(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            sessions_root = tmp_path / "codex-sessions"
            archived_root = tmp_path / "codex-archived"
            claude_root = tmp_path / "claude-projects"

            _write_jsonl(
                sessions_root / "2026/02/03/session.jsonl",
                [
                    {
                        "timestamp": "2026-02-03T08:59:00Z",
                        "type": "session_meta",
                        "payload": {"cwd": "/repo/demo"},
                    },
                    {
                        "timestamp": "2026-02-03T09:05:00Z",
                        "type": "event_msg",
                        "payload": {
                            "type": "token_count",
                            "info": {
                                "total_token_usage": {
                                    "input_tokens": 80,
                                    "cached_input_tokens": 10,
                                    "output_tokens": 10,
                                    "reasoning_output_tokens": 0,
                                    "total_tokens": 100,
                                }
                            },
                        },
                    },
                    {
                        "timestamp": "2026-02-03T09:10:00Z",
                        "type": "event_msg",
                        "payload": {
                            "type": "token_count",
                            "info": {
                                "total_token_usage": {
                                    "input_tokens": 80,
                                    "cached_input_tokens": 10,
                                    "output_tokens": 10,
                                    "reasoning_output_tokens": 0,
                                    "total_tokens": 100,
                                }
                            },
                        },
                    },
                    {
                        "timestamp": "2026-02-03T09:20:00Z",
                        "type": "event_msg",
                        "payload": {
                            "type": "token_count",
                            "info": {
                                "total_token_usage": {
                                    "input_tokens": 130,
                                    "cached_input_tokens": 20,
                                    "output_tokens": 20,
                                    "reasoning_output_tokens": 0,
                                    "total_tokens": 170,
                                }
                            },
                        },
                    },
                    {
                        "timestamp": "2026-02-03T10:05:00Z",
                        "type": "event_msg",
                        "payload": {
                            "type": "token_count",
                            "info": {
                                "total_token_usage": {
                                    "input_tokens": 150,
                                    "cached_input_tokens": 25,
                                    "output_tokens": 25,
                                    "reasoning_output_tokens": 0,
                                    "total_tokens": 200,
                                }
                            },
                        },
                    },
                ],
            )

            result = self.run_cli(
                [
                    "report",
                    "2026-02-03",
                    "2026-02-03",
                    "--provider",
                    "codex",
                    "--group-by",
                    "workspace",
                    "--format",
                    "csv",
                ],
                {
                    "TOKEMON_CODEX_SESSIONS_ROOT": str(sessions_root),
                    "TOKEMON_CODEX_ARCHIVED_ROOT": str(archived_root),
                    "TOKEMON_CLAUDE_PROJECTS_ROOT": str(claude_root),
                },
            )

            self.assertEqual(result.returncode, 0, msg=result.stderr)
            rows = list(csv.DictReader(result.stdout.splitlines()))
            self.assertEqual(len(rows), 2, msg=result.stdout)

            first = rows[0]
            self.assertEqual(first["workspace"], "/repo/demo")
            self.assertEqual(first["input_tokens"], "130")
            self.assertEqual(first["cached_input_tokens"], "20")
            self.assertEqual(first["output_tokens"], "20")
            self.assertEqual(first["reasoning_output_tokens"], "0")
            self.assertEqual(first["total_tokens"], "170")

            second = rows[1]
            self.assertEqual(second["workspace"], "/repo/demo")
            self.assertEqual(second["input_tokens"], "20")
            self.assertEqual(second["cached_input_tokens"], "5")
            self.assertEqual(second["output_tokens"], "5")
            self.assertEqual(second["reasoning_output_tokens"], "0")
            self.assertEqual(second["total_tokens"], "30")

    def test_claude_report_json_dedupes_message_updates(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            sessions_root = tmp_path / "codex-sessions"
            archived_root = tmp_path / "codex-archived"
            claude_root = tmp_path / "claude-projects"

            _write_jsonl(
                claude_root / "project-a/session.jsonl",
                [
                    {
                        "type": "assistant",
                        "sessionId": "session-1",
                        "cwd": "/repo/claude",
                        "timestamp": "2026-02-03T09:05:00Z",
                        "message": {
                            "id": "msg-1",
                            "usage": {
                                "input_tokens": 1,
                                "cache_creation_input_tokens": 3,
                                "cache_read_input_tokens": 4,
                                "output_tokens": 2,
                            },
                        },
                    },
                    {
                        "type": "assistant",
                        "sessionId": "session-1",
                        "cwd": "/repo/claude",
                        "timestamp": "2026-02-03T09:06:00Z",
                        "message": {
                            "id": "msg-1",
                            "usage": {
                                "input_tokens": 1,
                                "cache_creation_input_tokens": 3,
                                "cache_read_input_tokens": 4,
                                "output_tokens": 5,
                            },
                        },
                    },
                    {
                        "type": "assistant",
                        "sessionId": "session-1",
                        "cwd": "/repo/claude",
                        "timestamp": "2026-02-03T09:20:00Z",
                        "message": {
                            "id": "msg-2",
                            "usage": {
                                "input_tokens": 2,
                                "cache_creation_input_tokens": 0,
                                "cache_read_input_tokens": 1,
                                "output_tokens": 3,
                            },
                        },
                    },
                    {
                        "type": "assistant",
                        "sessionId": "session-1",
                        "cwd": "/repo/claude",
                        "timestamp": "2026-02-03T10:05:00Z",
                        "message": {
                            "id": "msg-3",
                            "usage": {
                                "input_tokens": 1,
                                "cache_creation_input_tokens": 1,
                                "cache_read_input_tokens": 1,
                                "output_tokens": 1,
                            },
                        },
                    },
                ],
            )

            result = self.run_cli(
                [
                    "report",
                    "2026-02-03",
                    "2026-02-03",
                    "--provider",
                    "claude",
                    "--sum-by",
                    "30",
                    "--format",
                    "json",
                ],
                {
                    "TOKEMON_CODEX_SESSIONS_ROOT": str(sessions_root),
                    "TOKEMON_CODEX_ARCHIVED_ROOT": str(archived_root),
                    "TOKEMON_CLAUDE_PROJECTS_ROOT": str(claude_root),
                },
            )

            self.assertEqual(result.returncode, 0, msg=result.stderr)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["provider"], "claude")
            self.assertEqual(payload["sum_by_minutes"], 30)
            self.assertEqual(payload["group_by"], "none")

            rows = payload["rows"]
            self.assertEqual(len(rows), 2, msg=result.stdout)

            first = rows[0]
            self.assertEqual(first["input_tokens"], 3)
            self.assertEqual(first["cached_input_tokens"], 8)
            self.assertEqual(first["output_tokens"], 8)
            self.assertEqual(first["reasoning_output_tokens"], 0)
            self.assertEqual(first["total_tokens"], 19)

            second = rows[1]
            self.assertEqual(second["input_tokens"], 1)
            self.assertEqual(second["cached_input_tokens"], 2)
            self.assertEqual(second["output_tokens"], 1)
            self.assertEqual(second["reasoning_output_tokens"], 0)
            self.assertEqual(second["total_tokens"], 4)

    def test_invalid_range_exits_non_zero(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            result = self.run_cli(
                ["report", "invalid_range", "--provider", "codex"],
                {
                    "TOKEMON_CODEX_SESSIONS_ROOT": str(tmp_path / "codex-sessions"),
                    "TOKEMON_CODEX_ARCHIVED_ROOT": str(tmp_path / "codex-archived"),
                    "TOKEMON_CLAUDE_PROJECTS_ROOT": str(tmp_path / "claude-projects"),
                },
            )
            self.assertEqual(result.returncode, 2)
            self.assertIn("range must be one of", result.stderr)


if __name__ == "__main__":
    unittest.main()
