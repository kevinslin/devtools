from __future__ import annotations

from calendar import monthrange
import csv
from datetime import datetime, timedelta
import importlib.machinery
import importlib.util
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "bin" / "tokemon"


def _shift_months(when: datetime, months: int) -> datetime:
    raw_month = when.month - 1 + months
    year = when.year + (raw_month // 12)
    month = (raw_month % 12) + 1
    day = min(when.day, monthrange(year, month)[1])
    return when.replace(year=year, month=month, day=day)


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row))
            handle.write("\n")


def _load_tokemon_module():
    module_name = f"tokemon_cli_test_{os.getpid()}_{len(sys.modules)}"
    loader = importlib.machinery.SourceFileLoader(module_name, str(CLI))
    spec = importlib.util.spec_from_loader(module_name, loader)
    if spec is None:
        raise AssertionError("failed to load tokemon module spec")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    try:
        loader.exec_module(module)
    finally:
        sys.modules.pop(module_name, None)
    return module


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

    def test_codex_report_csv_pretty_formats_token_counts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            sessions_root = tmp_path / "codex-sessions"
            archived_root = tmp_path / "codex-archived"
            claude_root = tmp_path / "claude-projects"

            _write_jsonl(
                sessions_root / "2026/02/03/session.jsonl",
                [
                    {
                        "timestamp": "2026-02-03T09:00:00-08:00",
                        "type": "session_meta",
                        "payload": {"cwd": "/repo/demo"},
                    },
                    {
                        "timestamp": "2026-02-03T09:05:00-08:00",
                        "type": "event_msg",
                        "payload": {
                            "type": "token_count",
                            "info": {
                                "total_token_usage": {
                                    "input_tokens": 5330000000,
                                    "total_tokens": 5330000000,
                                }
                            },
                        },
                    },
                ],
            )

            result = self.run_cli(
                [
                    "2026-02-03",
                    "2026-02-03",
                    "--provider",
                    "codex",
                    "--format",
                    "csv",
                    "--pretty",
                ],
                {
                    "TOKEMON_CODEX_SESSIONS_ROOT": str(sessions_root),
                    "TOKEMON_CODEX_ARCHIVED_ROOT": str(archived_root),
                    "TOKEMON_CLAUDE_PROJECTS_ROOT": str(claude_root),
                },
            )

            self.assertEqual(result.returncode, 0, msg=result.stderr)
            rows = list(csv.DictReader(result.stdout.splitlines()))
            self.assertEqual(len(rows), 1, msg=result.stdout)
            row = rows[0]
            self.assertEqual(row["input_tokens"], "5.33e9")
            self.assertEqual(row["cached_input_tokens"], "0.00e0")
            self.assertEqual(row["output_tokens"], "0.00e0")
            self.assertEqual(row["reasoning_output_tokens"], "0.00e0")
            self.assertEqual(row["total_tokens"], "5.33e9")

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
            self.assertEqual(payload["sum_by"], "30")
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

    def test_codex_report_json_pretty_formats_token_counts_as_strings(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            sessions_root = tmp_path / "codex-sessions"
            archived_root = tmp_path / "codex-archived"
            claude_root = tmp_path / "claude-projects"

            _write_jsonl(
                sessions_root / "2026/02/03/session.jsonl",
                [
                    {
                        "timestamp": "2026-02-03T09:00:00-08:00",
                        "type": "session_meta",
                        "payload": {"cwd": "/repo/demo"},
                    },
                    {
                        "timestamp": "2026-02-03T09:05:00-08:00",
                        "type": "event_msg",
                        "payload": {
                            "type": "token_count",
                            "info": {
                                "total_token_usage": {
                                    "input_tokens": 5330000000,
                                    "total_tokens": 5330000000,
                                }
                            },
                        },
                    },
                ],
            )

            result = self.run_cli(
                [
                    "2026-02-03",
                    "2026-02-03",
                    "--provider",
                    "codex",
                    "--format",
                    "json",
                    "--pretty",
                ],
                {
                    "TOKEMON_CODEX_SESSIONS_ROOT": str(sessions_root),
                    "TOKEMON_CODEX_ARCHIVED_ROOT": str(archived_root),
                    "TOKEMON_CLAUDE_PROJECTS_ROOT": str(claude_root),
                },
            )

            self.assertEqual(result.returncode, 0, msg=result.stderr)
            payload = json.loads(result.stdout)
            rows = payload["rows"]
            self.assertEqual(len(rows), 1, msg=result.stdout)
            row = rows[0]
            self.assertIsInstance(row["total_tokens"], str)
            self.assertEqual(row["input_tokens"], "5.33e9")
            self.assertEqual(row["cached_input_tokens"], "0.00e0")
            self.assertEqual(row["output_tokens"], "0.00e0")
            self.assertEqual(row["reasoning_output_tokens"], "0.00e0")
            self.assertEqual(row["total_tokens"], "5.33e9")

    def test_provider_all_combines_codex_and_claude(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            sessions_root = tmp_path / "codex-sessions"
            archived_root = tmp_path / "codex-archived"
            claude_root = tmp_path / "claude-projects"
            env = {
                "TOKEMON_CODEX_SESSIONS_ROOT": str(sessions_root),
                "TOKEMON_CODEX_ARCHIVED_ROOT": str(archived_root),
                "TOKEMON_CLAUDE_PROJECTS_ROOT": str(claude_root),
            }

            _write_jsonl(
                sessions_root / "2026/02/03/session.jsonl",
                [
                    {
                        "timestamp": "2026-02-03T09:00:00-08:00",
                        "type": "session_meta",
                        "payload": {"cwd": "/repo/codex"},
                    },
                    {
                        "timestamp": "2026-02-03T09:10:00-08:00",
                        "type": "event_msg",
                        "payload": {
                            "type": "token_count",
                            "info": {"total_token_usage": {"input_tokens": 10, "total_tokens": 10}},
                        },
                    },
                ],
            )

            _write_jsonl(
                claude_root / "project-a/session.jsonl",
                [
                    {
                        "type": "assistant",
                        "sessionId": "session-1",
                        "cwd": "/repo/claude",
                        "timestamp": "2026-02-03T09:20:00-08:00",
                        "message": {
                            "id": "msg-1",
                            "usage": {
                                "input_tokens": 2,
                                "cache_creation_input_tokens": 0,
                                "cache_read_input_tokens": 0,
                                "output_tokens": 3,
                            },
                        },
                    }
                ],
            )

            result = self.run_cli(
                [
                    "2026-02-03",
                    "2026-02-03",
                    "--provider",
                    "all",
                    "--sum-by",
                    "60",
                    "--format",
                    "json",
                ],
                env,
            )

            self.assertEqual(result.returncode, 0, msg=result.stderr)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["provider"], "all")

            rows = payload["rows"]
            self.assertEqual(len(rows), 1, msg=result.stdout)
            row = rows[0]
            self.assertEqual(row["input_tokens"], 12)
            self.assertEqual(row["cached_input_tokens"], 0)
            self.assertEqual(row["output_tokens"], 3)
            self.assertEqual(row["reasoning_output_tokens"], 0)
            self.assertEqual(row["total_tokens"], 15)

    def test_group_by_provider_splits_all_provider_usage(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            sessions_root = tmp_path / "codex-sessions"
            archived_root = tmp_path / "codex-archived"
            claude_root = tmp_path / "claude-projects"
            env = {
                "TOKEMON_CODEX_SESSIONS_ROOT": str(sessions_root),
                "TOKEMON_CODEX_ARCHIVED_ROOT": str(archived_root),
                "TOKEMON_CLAUDE_PROJECTS_ROOT": str(claude_root),
            }

            _write_jsonl(
                sessions_root / "2026/02/03/session.jsonl",
                [
                    {
                        "timestamp": "2026-02-03T09:00:00-08:00",
                        "type": "session_meta",
                        "payload": {"cwd": "/repo/codex"},
                    },
                    {
                        "timestamp": "2026-02-03T09:10:00-08:00",
                        "type": "event_msg",
                        "payload": {
                            "type": "token_count",
                            "info": {"total_token_usage": {"input_tokens": 10, "total_tokens": 10}},
                        },
                    },
                ],
            )

            _write_jsonl(
                claude_root / "project-a/session.jsonl",
                [
                    {
                        "type": "assistant",
                        "sessionId": "session-1",
                        "cwd": "/repo/claude",
                        "timestamp": "2026-02-03T09:20:00-08:00",
                        "message": {
                            "id": "msg-1",
                            "usage": {
                                "input_tokens": 2,
                                "cache_creation_input_tokens": 0,
                                "cache_read_input_tokens": 0,
                                "output_tokens": 3,
                            },
                        },
                    }
                ],
            )

            result = self.run_cli(
                [
                    "2026-02-03",
                    "2026-02-03",
                    "--provider",
                    "all",
                    "--group-by",
                    "provider",
                    "--sum-by",
                    "60",
                    "--format",
                    "csv",
                ],
                env,
            )

            self.assertEqual(result.returncode, 0, msg=result.stderr)
            rows = list(csv.DictReader(result.stdout.splitlines()))
            self.assertEqual(len(rows), 2, msg=result.stdout)
            by_provider = {row["provider"]: int(row["total_tokens"]) for row in rows}
            self.assertEqual(by_provider, {"codex": 10, "claude": 5})

    def test_group_by_session_splits_all_provider_usage(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            sessions_root = tmp_path / "codex-sessions"
            archived_root = tmp_path / "codex-archived"
            claude_root = tmp_path / "claude-projects"
            env = {
                "TOKEMON_CODEX_SESSIONS_ROOT": str(sessions_root),
                "TOKEMON_CODEX_ARCHIVED_ROOT": str(archived_root),
                "TOKEMON_CLAUDE_PROJECTS_ROOT": str(claude_root),
            }

            _write_jsonl(
                sessions_root / "2026/02/03/rollout-file-name.jsonl",
                [
                    {
                        "timestamp": "2026-02-03T09:00:00-08:00",
                        "type": "session_meta",
                        "payload": {"id": "codex-session-1", "cwd": "/repo/codex"},
                    },
                    {
                        "timestamp": "2026-02-03T09:10:00-08:00",
                        "type": "event_msg",
                        "payload": {
                            "type": "token_count",
                            "info": {"total_token_usage": {"input_tokens": 10, "total_tokens": 10}},
                        },
                    },
                ],
            )

            _write_jsonl(
                claude_root / "project-a/session.jsonl",
                [
                    {
                        "type": "assistant",
                        "sessionId": "claude-session-1",
                        "cwd": "/repo/claude",
                        "timestamp": "2026-02-03T09:20:00-08:00",
                        "message": {
                            "id": "msg-1",
                            "usage": {
                                "input_tokens": 2,
                                "cache_creation_input_tokens": 0,
                                "cache_read_input_tokens": 0,
                                "output_tokens": 3,
                            },
                        },
                    },
                    {
                        "type": "assistant",
                        "sessionId": "claude-session-2",
                        "cwd": "/repo/claude",
                        "timestamp": "2026-02-03T09:40:00-08:00",
                        "message": {
                            "id": "msg-2",
                            "usage": {
                                "input_tokens": 1,
                                "cache_creation_input_tokens": 1,
                                "cache_read_input_tokens": 0,
                                "output_tokens": 5,
                            },
                        },
                    },
                ],
            )

            result = self.run_cli(
                [
                    "2026-02-03",
                    "2026-02-03",
                    "--provider",
                    "all",
                    "--group-by",
                    "session",
                    "--sum-by",
                    "60",
                    "--format",
                    "csv",
                ],
                env,
            )

            self.assertEqual(result.returncode, 0, msg=result.stderr)
            rows = list(csv.DictReader(result.stdout.splitlines()))
            self.assertEqual(len(rows), 3, msg=result.stdout)
            by_session = {row["session"]: int(row["total_tokens"]) for row in rows}
            self.assertEqual(
                by_session,
                {"codex-session-1": 10, "claude-session-1": 5, "claude-session-2": 7},
            )

    def test_invalid_range_exits_non_zero(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            result = self.run_cli(
                ["invalid_range", "--provider", "codex"],
                {
                    "TOKEMON_CODEX_SESSIONS_ROOT": str(tmp_path / "codex-sessions"),
                    "TOKEMON_CODEX_ARCHIVED_ROOT": str(tmp_path / "codex-archived"),
                    "TOKEMON_CLAUDE_PROJECTS_ROOT": str(tmp_path / "claude-projects"),
                },
            )
            self.assertEqual(result.returncode, 2)
            self.assertIn("range must be one of", result.stderr)

    def test_sum_by_presets_daily_weekly_monthly(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            sessions_root = tmp_path / "codex-sessions"
            archived_root = tmp_path / "codex-archived"
            claude_root = tmp_path / "claude-projects"
            env = {
                "TOKEMON_CODEX_SESSIONS_ROOT": str(sessions_root),
                "TOKEMON_CODEX_ARCHIVED_ROOT": str(archived_root),
                "TOKEMON_CLAUDE_PROJECTS_ROOT": str(claude_root),
            }

            _write_jsonl(
                sessions_root / "2026/02/03/session.jsonl",
                [
                    {
                        "timestamp": "2026-01-31T12:00:00-08:00",
                        "type": "session_meta",
                        "payload": {"cwd": "/repo/demo"},
                    },
                    {
                        "timestamp": "2026-01-31T12:00:00-08:00",
                        "type": "event_msg",
                        "payload": {
                            "type": "token_count",
                            "info": {"total_token_usage": {"input_tokens": 10, "total_tokens": 10}},
                        },
                    },
                    {
                        "timestamp": "2026-02-01T12:00:00-08:00",
                        "type": "event_msg",
                        "payload": {
                            "type": "token_count",
                            "info": {"total_token_usage": {"input_tokens": 30, "total_tokens": 30}},
                        },
                    },
                    {
                        "timestamp": "2026-02-07T12:00:00-08:00",
                        "type": "event_msg",
                        "payload": {
                            "type": "token_count",
                            "info": {"total_token_usage": {"input_tokens": 60, "total_tokens": 60}},
                        },
                    },
                    {
                        "timestamp": "2026-02-08T12:00:00-08:00",
                        "type": "event_msg",
                        "payload": {
                            "type": "token_count",
                            "info": {"total_token_usage": {"input_tokens": 100, "total_tokens": 100}},
                        },
                    },
                ],
            )

            expected_by_preset = {
                "daily": [10, 20, 30, 40],
                "weekly": [10, 50, 40],
                "monthly": [10, 90],
            }

            for preset, expected_totals in expected_by_preset.items():
                result = self.run_cli(
                    [
                        "2026-01-31",
                        "2026-02-08",
                        "--provider",
                        "codex",
                        "--sum-by",
                        preset,
                        "--format",
                        "csv",
                    ],
                    env,
                )
                self.assertEqual(result.returncode, 0, msg=f"{preset}: {result.stderr}\n{result.stdout}")
                rows = list(csv.DictReader(result.stdout.splitlines()))
                totals = [int(row["total_tokens"]) for row in rows]
                self.assertEqual(totals, expected_totals, msg=f"{preset}: {result.stdout}")

    def test_codex_explicit_day_keeps_previous_day_spillover_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            sessions_root = tmp_path / "codex-sessions"
            archived_root = tmp_path / "codex-archived"
            claude_root = tmp_path / "claude-projects"

            _write_jsonl(
                sessions_root / "2026/02/02/session.jsonl",
                [
                    {
                        "timestamp": "2026-02-02T23:55:00-08:00",
                        "type": "session_meta",
                        "payload": {"cwd": "/repo/spillover"},
                    },
                    {
                        "timestamp": "2026-02-02T23:58:00-08:00",
                        "type": "event_msg",
                        "payload": {
                            "type": "token_count",
                            "info": {
                                "total_token_usage": {
                                    "input_tokens": 40,
                                    "cached_input_tokens": 5,
                                    "output_tokens": 5,
                                    "reasoning_output_tokens": 0,
                                    "total_tokens": 50,
                                }
                            },
                        },
                    },
                    {
                        "timestamp": "2026-02-03T00:05:00-08:00",
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
                        "timestamp": "2026-02-03T00:20:00-08:00",
                        "type": "event_msg",
                        "payload": {
                            "type": "token_count",
                            "info": {
                                "total_token_usage": {
                                    "input_tokens": 104,
                                    "cached_input_tokens": 13,
                                    "output_tokens": 13,
                                    "reasoning_output_tokens": 0,
                                    "total_tokens": 130,
                                }
                            },
                        },
                    },
                ],
            )

            result = self.run_cli(
                [
                    "2026-02-03",
                    "2026-02-03",
                    "--provider",
                    "codex",
                    "--sum-by",
                    "60",
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
            self.assertEqual(len(rows), 1, msg=result.stdout)
            row = rows[0]
            self.assertEqual(row["bucket"], "2026-02-03T00:00-08:00")
            self.assertEqual(row["input_tokens"], "64")
            self.assertEqual(row["cached_input_tokens"], "8")
            self.assertEqual(row["output_tokens"], "8")
            self.assertEqual(row["reasoning_output_tokens"], "0")
            self.assertEqual(row["total_tokens"], "80")

    def test_codex_date_layout_short_range_avoids_recursive_tree_scan(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            sessions_root = tmp_path / "codex-sessions"
            archived_root = tmp_path / "codex-archived"

            in_range_session = sessions_root / "2026/02/02/spillover.jsonl"
            current_day_session = sessions_root / "2026/02/03/current.jsonl"
            ignored_session = sessions_root / "2025/12/31/ignored.jsonl"
            in_range_archived = archived_root / "rollout-2026-02-03T09-15-00.jsonl"
            ignored_archived = archived_root / "rollout-2025-12-31T22-45-00.jsonl"

            for path in [
                in_range_session,
                current_day_session,
                ignored_session,
                in_range_archived,
                ignored_archived,
            ]:
                _write_jsonl(path, [{"type": "session_meta", "payload": {"cwd": "/repo/demo"}}])

            tokemon = _load_tokemon_module()
            start, end, _ = tokemon._resolve_range(["2026-02-03", "2026-02-03"])

            with (
                mock.patch.dict(
                    os.environ,
                    {
                        "TOKEMON_CODEX_SESSIONS_ROOT": str(sessions_root),
                        "TOKEMON_CODEX_ARCHIVED_ROOT": str(archived_root),
                    },
                    clear=False,
                ),
                mock.patch.object(Path, "rglob", side_effect=AssertionError("unexpected recursive scan")),
            ):
                files = list(tokemon._codex_files(start, end))

            self.assertEqual(
                files,
                [
                    in_range_session,
                    current_day_session,
                    in_range_archived,
                ],
            )

    def test_codex_cli_reuses_index_for_unchanged_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            sessions_root = tmp_path / "codex-sessions"
            archived_root = tmp_path / "codex-archived"
            claude_root = tmp_path / "claude-projects"
            index_path = tmp_path / "tokemon-index.sqlite3"
            session_path = sessions_root / "2026/02/03/session.jsonl"

            _write_jsonl(
                session_path,
                [
                    {
                        "timestamp": "2026-02-03T09:00:00-08:00",
                        "type": "session_meta",
                        "payload": {"cwd": "/repo/demo", "id": "codex-session-1"},
                    },
                    {
                        "timestamp": "2026-02-03T09:10:00-08:00",
                        "type": "event_msg",
                        "payload": {
                            "type": "token_count",
                            "info": {"total_token_usage": {"input_tokens": 80, "total_tokens": 80}},
                        },
                    },
                ],
            )

            env = {
                "TOKEMON_CODEX_SESSIONS_ROOT": str(sessions_root),
                "TOKEMON_CODEX_ARCHIVED_ROOT": str(archived_root),
                "TOKEMON_CLAUDE_PROJECTS_ROOT": str(claude_root),
                "TOKEMON_INDEX_PATH": str(index_path),
            }

            first = self.run_cli(
                [
                    "2026-02-03",
                    "2026-02-03",
                    "--provider",
                    "codex",
                    "--sum-by",
                    "60",
                    "--format",
                    "csv",
                ],
                env,
            )
            self.assertEqual(first.returncode, 0, msg=first.stderr)
            self.assertTrue(index_path.exists())
            first_rows = list(csv.DictReader(first.stdout.splitlines()))
            self.assertEqual(first_rows[0]["total_tokens"], "80")

            original_mode = session_path.stat().st_mode
            try:
                session_path.chmod(0)
                second = self.run_cli(
                    [
                        "2026-02-03",
                        "2026-02-03",
                        "--provider",
                        "codex",
                        "--sum-by",
                        "60",
                        "--format",
                        "csv",
                    ],
                    env,
                )
            finally:
                session_path.chmod(original_mode)

            self.assertEqual(second.returncode, 0, msg=second.stderr)
            second_rows = list(csv.DictReader(second.stdout.splitlines()))
            self.assertEqual(second_rows, first_rows)

    def test_codex_cli_rescans_changed_and_new_files_while_reusing_unchanged_indexed_data(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            sessions_root = tmp_path / "codex-sessions"
            archived_root = tmp_path / "codex-archived"
            claude_root = tmp_path / "claude-projects"
            index_path = tmp_path / "tokemon-index.sqlite3"
            unchanged_path = sessions_root / "2026/02/03/unchanged.jsonl"
            changed_path = sessions_root / "2026/02/03/changed.jsonl"
            new_path = sessions_root / "2026/02/03/new.jsonl"

            _write_jsonl(
                unchanged_path,
                [
                    {
                        "timestamp": "2026-02-03T09:00:00-08:00",
                        "type": "session_meta",
                        "payload": {"cwd": "/repo/unchanged", "id": "codex-session-unchanged"},
                    },
                    {
                        "timestamp": "2026-02-03T09:05:00-08:00",
                        "type": "event_msg",
                        "payload": {
                            "type": "token_count",
                            "info": {"total_token_usage": {"input_tokens": 10, "total_tokens": 10}},
                        },
                    },
                ],
            )
            _write_jsonl(
                changed_path,
                [
                    {
                        "timestamp": "2026-02-03T09:00:00-08:00",
                        "type": "session_meta",
                        "payload": {"cwd": "/repo/changed", "id": "codex-session-changed"},
                    },
                    {
                        "timestamp": "2026-02-03T09:10:00-08:00",
                        "type": "event_msg",
                        "payload": {
                            "type": "token_count",
                            "info": {"total_token_usage": {"input_tokens": 20, "total_tokens": 20}},
                        },
                    },
                ],
            )

            env = {
                "TOKEMON_CODEX_SESSIONS_ROOT": str(sessions_root),
                "TOKEMON_CODEX_ARCHIVED_ROOT": str(archived_root),
                "TOKEMON_CLAUDE_PROJECTS_ROOT": str(claude_root),
                "TOKEMON_INDEX_PATH": str(index_path),
            }

            first = self.run_cli(
                [
                    "2026-02-03",
                    "2026-02-03",
                    "--provider",
                    "codex",
                    "--sum-by",
                    "60",
                    "--format",
                    "csv",
                ],
                env,
            )
            self.assertEqual(first.returncode, 0, msg=first.stderr)
            first_rows = list(csv.DictReader(first.stdout.splitlines()))
            self.assertEqual(first_rows[0]["total_tokens"], "30")

            _write_jsonl(
                changed_path,
                [
                    {
                        "timestamp": "2026-02-03T09:00:00-08:00",
                        "type": "session_meta",
                        "payload": {"cwd": "/repo/changed", "id": "codex-session-changed"},
                    },
                    {
                        "timestamp": "2026-02-03T09:10:00-08:00",
                        "type": "event_msg",
                        "payload": {
                            "type": "token_count",
                            "info": {"total_token_usage": {"input_tokens": 20, "total_tokens": 20}},
                        },
                    },
                    {
                        "timestamp": "2026-02-03T09:20:00-08:00",
                        "type": "event_msg",
                        "payload": {
                            "type": "token_count",
                            "info": {"total_token_usage": {"input_tokens": 50, "total_tokens": 50}},
                        },
                    },
                ],
            )
            _write_jsonl(
                new_path,
                [
                    {
                        "timestamp": "2026-02-03T09:00:00-08:00",
                        "type": "session_meta",
                        "payload": {"cwd": "/repo/new", "id": "codex-session-new"},
                    },
                    {
                        "timestamp": "2026-02-03T09:25:00-08:00",
                        "type": "event_msg",
                        "payload": {
                            "type": "token_count",
                            "info": {"total_token_usage": {"input_tokens": 15, "total_tokens": 15}},
                        },
                    },
                ],
            )

            original_mode = unchanged_path.stat().st_mode
            try:
                unchanged_path.chmod(0)
                second = self.run_cli(
                    [
                        "2026-02-03",
                        "2026-02-03",
                        "--provider",
                        "codex",
                        "--sum-by",
                        "60",
                        "--format",
                        "csv",
                    ],
                    env,
                )
            finally:
                unchanged_path.chmod(original_mode)

            self.assertEqual(second.returncode, 0, msg=second.stderr)
            second_rows = list(csv.DictReader(second.stdout.splitlines()))
            self.assertEqual(second_rows[0]["total_tokens"], "75")

    def test_codex_cli_dedupes_replayed_session_snapshots_across_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            sessions_root = tmp_path / "codex-sessions"
            archived_root = tmp_path / "codex-archived"
            claude_root = tmp_path / "claude-projects"
            session_id = "codex-session-replayed"

            _write_jsonl(
                sessions_root / "2026/02/03/first.jsonl",
                [
                    {
                        "timestamp": "2026-02-03T09:00:00-08:00",
                        "type": "session_meta",
                        "payload": {"cwd": "/repo/demo", "id": session_id},
                    },
                    {
                        "timestamp": "2026-02-03T09:05:00-08:00",
                        "type": "event_msg",
                        "payload": {
                            "type": "token_count",
                            "info": {"total_token_usage": {"input_tokens": 10, "total_tokens": 10}},
                        },
                    },
                    {
                        "timestamp": "2026-02-03T09:10:00-08:00",
                        "type": "event_msg",
                        "payload": {
                            "type": "token_count",
                            "info": {"total_token_usage": {"input_tokens": 20, "total_tokens": 20}},
                        },
                    },
                ],
            )
            _write_jsonl(
                sessions_root / "2026/02/03/replay.jsonl",
                [
                    {
                        "timestamp": "2026-02-03T10:00:00-08:00",
                        "type": "session_meta",
                        "payload": {"cwd": "/repo/demo", "id": session_id},
                    },
                    {
                        "timestamp": "2026-02-03T10:00:01-08:00",
                        "type": "event_msg",
                        "payload": {
                            "type": "token_count",
                            "info": {"total_token_usage": {"input_tokens": 10, "total_tokens": 10}},
                        },
                    },
                    {
                        "timestamp": "2026-02-03T10:00:02-08:00",
                        "type": "event_msg",
                        "payload": {
                            "type": "token_count",
                            "info": {"total_token_usage": {"input_tokens": 20, "total_tokens": 20}},
                        },
                    },
                    {
                        "timestamp": "2026-02-03T10:00:03-08:00",
                        "type": "event_msg",
                        "payload": {
                            "type": "token_count",
                            "info": {"total_token_usage": {"input_tokens": 35, "total_tokens": 35}},
                        },
                    },
                ],
            )

            result = self.run_cli(
                [
                    "2026-02-03",
                    "2026-02-03",
                    "--provider",
                    "codex",
                    "--sum-by",
                    "60",
                    "--format",
                    "csv",
                ],
                {
                    "TOKEMON_CODEX_SESSIONS_ROOT": str(sessions_root),
                    "TOKEMON_CODEX_ARCHIVED_ROOT": str(archived_root),
                    "TOKEMON_CLAUDE_PROJECTS_ROOT": str(claude_root),
                    "TOKEMON_DISABLE_INDEX": "1",
                },
            )

            self.assertEqual(result.returncode, 0, msg=result.stderr)
            rows = list(csv.DictReader(result.stdout.splitlines()))
            self.assertEqual(len(rows), 2, msg=result.stdout)
            self.assertEqual([row["total_tokens"] for row in rows], ["20", "15"])

    def test_codex_cli_rebuilds_old_index_before_reusing_cumulative_snapshots(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            sessions_root = tmp_path / "codex-sessions"
            archived_root = tmp_path / "codex-archived"
            claude_root = tmp_path / "claude-projects"
            index_path = tmp_path / "tokemon-index.sqlite3"
            session_path = sessions_root / "2026/02/03/session.jsonl"

            _write_jsonl(
                session_path,
                [
                    {
                        "timestamp": "2026-02-03T09:00:00-08:00",
                        "type": "session_meta",
                        "payload": {"cwd": "/repo/demo", "id": "codex-session-1"},
                    },
                    {
                        "timestamp": "2026-02-03T09:10:00-08:00",
                        "type": "event_msg",
                        "payload": {
                            "type": "token_count",
                            "info": {"total_token_usage": {"input_tokens": 80, "total_tokens": 80}},
                        },
                    },
                ],
            )

            with sqlite3.connect(index_path) as conn:
                conn.execute(
                    """
                    CREATE TABLE indexed_files (
                        provider TEXT NOT NULL,
                        source_path TEXT NOT NULL,
                        size INTEGER NOT NULL,
                        mtime_ns INTEGER NOT NULL,
                        PRIMARY KEY (provider, source_path)
                    )
                    """
                )
                conn.execute(
                    """
                    CREATE TABLE usage_records (
                        provider TEXT NOT NULL,
                        source_path TEXT NOT NULL,
                        timestamp_us INTEGER NOT NULL,
                        timestamp_iso TEXT NOT NULL,
                        workspace TEXT NOT NULL,
                        session TEXT NOT NULL,
                        input_tokens INTEGER NOT NULL,
                        cached_input_tokens INTEGER NOT NULL,
                        output_tokens INTEGER NOT NULL,
                        reasoning_output_tokens INTEGER NOT NULL,
                        total_tokens INTEGER NOT NULL
                    )
                    """
                )
                conn.execute(
                    """
                    INSERT INTO usage_records (
                        provider,
                        source_path,
                        timestamp_us,
                        timestamp_iso,
                        workspace,
                        session,
                        input_tokens,
                        cached_input_tokens,
                        output_tokens,
                        reasoning_output_tokens,
                        total_tokens
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        "codex",
                        "/tmp/stale.jsonl",
                        1,
                        "2026-02-03T09:00:00-08:00",
                        "/repo/stale",
                        "stale-session",
                        999999999,
                        0,
                        0,
                        0,
                        999999999,
                    ),
                )

            env = {
                "TOKEMON_CODEX_SESSIONS_ROOT": str(sessions_root),
                "TOKEMON_CODEX_ARCHIVED_ROOT": str(archived_root),
                "TOKEMON_CLAUDE_PROJECTS_ROOT": str(claude_root),
                "TOKEMON_INDEX_PATH": str(index_path),
            }

            result = self.run_cli(
                [
                    "2026-02-03",
                    "2026-02-03",
                    "--provider",
                    "codex",
                    "--sum-by",
                    "60",
                    "--format",
                    "csv",
                ],
                env,
            )

            self.assertEqual(result.returncode, 0, msg=result.stderr)
            rows = list(csv.DictReader(result.stdout.splitlines()))
            self.assertEqual(rows[0]["total_tokens"], "80")

            with sqlite3.connect(index_path) as conn:
                user_version = conn.execute("PRAGMA user_version").fetchone()[0]
                indexed_rows = conn.execute("SELECT total_tokens FROM usage_records ORDER BY total_tokens").fetchall()

            self.assertEqual(user_version, 1)
            self.assertEqual(indexed_rows, [(80,)])

    def test_invalid_sum_by_exits_non_zero(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            result = self.run_cli(
                ["2026-02-03", "2026-02-03", "--provider", "codex", "--sum-by", "hourlyish"],
                {
                    "TOKEMON_CODEX_SESSIONS_ROOT": str(tmp_path / "codex-sessions"),
                    "TOKEMON_CODEX_ARCHIVED_ROOT": str(tmp_path / "codex-archived"),
                    "TOKEMON_CLAUDE_PROJECTS_ROOT": str(tmp_path / "claude-projects"),
                },
            )
            self.assertEqual(result.returncode, 2)
            self.assertIn("daily|weekly|monthly", result.stderr)

    def test_range_presets_relative_and_trailing_windows(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            env = {
                "TOKEMON_CODEX_SESSIONS_ROOT": str(tmp_path / "codex-sessions"),
                "TOKEMON_CODEX_ARCHIVED_ROOT": str(tmp_path / "codex-archived"),
                "TOKEMON_CLAUDE_PROJECTS_ROOT": str(tmp_path / "claude-projects"),
            }

            def read_range(preset: str) -> tuple[datetime, datetime]:
                result = self.run_cli([preset, "--provider", "codex", "--format", "json"], env)
                self.assertEqual(result.returncode, 0, msg=f"{preset}: {result.stderr}\n{result.stdout}")
                payload = json.loads(result.stdout)
                return datetime.fromisoformat(payload["start"]), datetime.fromisoformat(payload["end_exclusive"])

            week_start, week_end = read_range("week")
            self.assertEqual(week_end - week_start, timedelta(days=7))

            month_start, month_end = read_range("month")
            self.assertEqual(month_start, _shift_months(month_end, -1))

            year_start, year_end = read_range("year")
            self.assertEqual(year_start, _shift_months(year_end, -12))

            current_week_start, current_week_end = read_range("current_week")
            self.assertEqual(current_week_end - current_week_start, timedelta(days=7))
            # Python weekday(): Monday=0 ... Sunday=6
            self.assertEqual(current_week_start.weekday(), 6)
            self.assertEqual(current_week_start.hour, 0)
            self.assertEqual(current_week_start.minute, 0)
            self.assertEqual(current_week_start.second, 0)


if __name__ == "__main__":
    unittest.main()
