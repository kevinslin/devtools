from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "bin" / "claw-debug"


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


class ClawDebugCliTest(unittest.TestCase):
    def run_cli(self, args: list[str], *, openclaw_home: Path) -> subprocess.CompletedProcess[str]:
        env = os.environ.copy()
        env["OPENCLAW_HOME"] = str(openclaw_home)
        return subprocess.run(
            [str(CLI), *args],
            cwd=ROOT,
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )

    def test_dump_defaults_to_main_session_and_filters_summary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / ".openclaw"
            sessions_dir = home / "agents/main/sessions"
            codex_sessions_dir = home / "agents/main/agent/codex-home/sessions/2026/05/10"

            session_id = "711ddc35-29e3-4144-bdd5-bd81a1fcae3c"
            session_file = sessions_dir / f"{session_id}.jsonl"
            thread_id = "019e143c-3da8-7222-9183-b54eb089b4b9"

            _write_json(
                sessions_dir / "sessions.json",
                {
                    "agent:main:main": {
                        "sessionId": session_id,
                        "sessionFile": str(session_file),
                        "model": "gpt-5.5",
                    },
                    "agent:main:other": {"sessionId": "other-session"},
                },
            )
            _write_text(session_file, '{"type":"message","text":"session log"}\n')
            _write_json(
                sessions_dir / f"{session_id}.trajectory-path.json",
                {
                    "traceSchema": "openclaw-trajectory-pointer",
                    "runtimeFile": str(sessions_dir / f"{session_id}.trajectory.jsonl"),
                },
            )
            _write_text(
                sessions_dir / f"{session_id}.trajectory.jsonl",
                '{"type":"session.started"}\n',
            )
            _write_json(
                Path(f"{session_file}.codex-app-server.json"),
                {"threadId": thread_id, "model": "gpt-5.5"},
            )
            _write_text(
                codex_sessions_dir
                / f"rollout-2026-05-10T16-32-32-{thread_id}.jsonl",
                '{"type":"session_meta"}\n',
            )

            result = self.run_cli(["dump"], openclaw_home=home)

            self.assertEqual(result.returncode, 0, msg=result.stderr)
            self.assertIn("# session summary", result.stdout)
            self.assertIn('"agent:main:main"', result.stdout)
            self.assertNotIn('"agent:main:other"', result.stdout)
            self.assertIn("# session logs", result.stdout)
            self.assertIn("session log", result.stdout)
            self.assertIn("# session trajectory summary", result.stdout)
            self.assertIn("# session trajectory", result.stdout)
            self.assertIn("# codex app server", result.stdout)
            self.assertIn("# codex session", result.stdout)
            self.assertIn("session_meta", result.stdout)

    def test_dump_unknown_session_returns_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / ".openclaw"
            _write_json(home / "agents/main/sessions/sessions.json", {})

            result = self.run_cli(["dump", "agent:main:missing"], openclaw_home=home)

            self.assertEqual(result.returncode, 1)
            self.assertIn("session key not found", result.stderr)


if __name__ == "__main__":
    unittest.main()
