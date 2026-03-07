from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "bin" / "convo"


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row))
            handle.write("\n")


class ConvoCliTest(unittest.TestCase):
    def run_cli(
        self, args: list[str], *, sessions_root: Path, archived_root: Path
    ) -> subprocess.CompletedProcess[str]:
        env = os.environ.copy()
        return subprocess.run(
            [
                sys.executable,
                str(CLI),
                *args,
                "--sessions-root",
                str(sessions_root),
                "--archived-root",
                str(archived_root),
            ],
            cwd=ROOT,
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )

    def test_search_markdown_output_includes_session_metadata_and_context(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            sessions_root = tmp_path / "sessions"
            archived_root = tmp_path / "archived"

            session_file = sessions_root / "2026/03/05/rollout-1.jsonl"
            _write_jsonl(
                session_file,
                [
                    {
                        "timestamp": "2026-03-05T09:00:00Z",
                        "type": "session_meta",
                        "payload": {
                            "id": "session-1",
                            "title": "session one",
                            "cwd": "/repo/alpha",
                        },
                    },
                    {
                        "timestamp": "2026-03-05T09:01:00Z",
                        "type": "event_msg",
                        "payload": {"message": "before match"},
                    },
                    {
                        "timestamp": "2026-03-05T09:02:00Z",
                        "type": "event_msg",
                        "payload": {"message": "contains needle term"},
                    },
                    {
                        "timestamp": "2026-03-05T09:03:00Z",
                        "type": "event_msg",
                        "payload": {"message": "after match"},
                    },
                ],
            )

            result = self.run_cli(
                ["search", "needle"],
                sessions_root=sessions_root,
                archived_root=archived_root,
            )

            self.assertEqual(result.returncode, 0, msg=result.stderr)
            self.assertIn("### session one", result.stdout)
            self.assertIn(f"- absolute path: {session_file.resolve()}", result.stdout)
            self.assertIn("- sessionid: session-1", result.stdout)
            self.assertIn("- created: 2026-03-05T09:00:00Z", result.stdout)
            self.assertIn("- updated: 2026-03-05T09:03:00Z", result.stdout)
            self.assertIn("contains needle term", result.stdout)
            self.assertIn("```text", result.stdout)

    def test_search_json_format_respects_date_window(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            sessions_root = tmp_path / "sessions"
            archived_root = tmp_path / "archived"

            _write_jsonl(
                sessions_root / "2026/03/01/rollout-old.jsonl",
                [
                    {
                        "timestamp": "2026-03-01T08:00:00Z",
                        "type": "session_meta",
                        "payload": {"id": "session-old", "cwd": "/repo/old"},
                    },
                    {
                        "timestamp": "2026-03-01T08:02:00Z",
                        "type": "event_msg",
                        "payload": {"message": "target appears here"},
                    },
                ],
            )

            new_file = sessions_root / "2026/03/06/rollout-new.jsonl"
            _write_jsonl(
                new_file,
                [
                    {
                        "timestamp": "2026-03-06T10:00:00Z",
                        "type": "session_meta",
                        "payload": {"id": "session-new", "cwd": "/repo/new"},
                    },
                    {
                        "timestamp": "2026-03-06T10:03:00Z",
                        "type": "event_msg",
                        "payload": {"message": "target appears in new session"},
                    },
                ],
            )

            result = self.run_cli(
                [
                    "search",
                    "target",
                    "--from",
                    "2026-03-05",
                    "--to",
                    "2026-03-06",
                    "--format",
                    "json",
                ],
                sessions_root=sessions_root,
                archived_root=archived_root,
            )

            self.assertEqual(result.returncode, 0, msg=result.stderr)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["query"], "target")
            self.assertEqual(payload["from"], "2026-03-05")
            self.assertEqual(payload["to"], "2026-03-06")
            self.assertEqual(payload["count"], 1)
            self.assertEqual(payload["results"][0]["sessionid"], "session-new")
            self.assertEqual(
                payload["results"][0]["absolute_path"], str(new_file.resolve())
            )

    def test_search_invalid_regex_returns_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            sessions_root = tmp_path / "sessions"
            archived_root = tmp_path / "archived"

            result = self.run_cli(
                ["search", "["],
                sessions_root=sessions_root,
                archived_root=archived_root,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("invalid regex", result.stderr.lower())


if __name__ == "__main__":
    unittest.main()
