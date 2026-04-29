from __future__ import annotations

from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import unittest

ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "bin" / "slack-post"


class _SlackHandler(BaseHTTPRequestHandler):
    def do_POST(self) -> None:
        content_length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(content_length)
        self.server.requests.append(  # type: ignore[attr-defined]
            {
                "path": self.path,
                "headers": dict(self.headers),
                "body": body.decode("utf-8"),
            }
        )

        status = self.server.response_status  # type: ignore[attr-defined]
        response = json.dumps(self.server.response_payload).encode("utf-8")  # type: ignore[attr-defined]
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(response)))
        self.end_headers()
        self.wfile.write(response)

    def log_message(self, format: str, *args: object) -> None:
        return


class SlackPostCliTest(unittest.TestCase):
    def run_cli(
        self,
        args: list[str],
        *,
        input_text: str | None = None,
        env: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        cli_env = os.environ.copy()
        cli_env.pop("SLACK_TOKEN", None)
        cli_env.pop("SLACK_BOT_TOKEN", None)
        if env is not None:
            cli_env.update(env)
        return subprocess.run(
            [sys.executable, str(CLI), *args],
            cwd=ROOT,
            env=cli_env,
            input=input_text,
            capture_output=True,
            text=True,
            check=False,
        )

    def test_posts_message_argument(self) -> None:
        server, api_url = self._start_slack_server(
            {"ok": True, "channel": "C123", "ts": "1712345678.123456"}
        )

        result = self.run_cli(
            [
                "--api-url",
                api_url,
                "--channel",
                "C123",
                "--token",
                "xoxb-test-token",
                "hello",
                "there",
            ]
        )

        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertIn("posted message to C123 at 1712345678.123456", result.stdout)
        self.assertEqual(len(server.requests), 1)
        request_payload = server.requests[0]
        self.assertEqual(request_payload["path"], "/api/chat.postMessage")
        self.assertEqual(request_payload["headers"]["Authorization"], "Bearer xoxb-test-token")
        self.assertEqual(
            json.loads(request_payload["body"]),
            {"channel": "C123", "text": "hello there"},
        )

    def test_reads_message_from_stdin_and_token_from_environment(self) -> None:
        server, api_url = self._start_slack_server({"ok": True, "ts": "1712345678.999999"})

        result = self.run_cli(
            [
                "--api-url",
                api_url,
                "--channel",
                "C999",
                "--thread-ts",
                "1712340000.000001",
            ],
            input_text="line one\nline two\n",
            env={"SLACK_TOKEN": "xoxb-env-token"},
        )

        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertEqual(len(server.requests), 1)
        request_payload = server.requests[0]
        self.assertEqual(request_payload["headers"]["Authorization"], "Bearer xoxb-env-token")
        self.assertEqual(
            json.loads(request_payload["body"]),
            {
                "channel": "C999",
                "text": "line one\nline two",
                "thread_ts": "1712340000.000001",
            },
        )

    def test_rejects_missing_token(self) -> None:
        result = self.run_cli(["--channel", "C123", "hello"])

        self.assertEqual(result.returncode, 1)
        self.assertIn("provide a token", result.stderr)

    def test_reports_slack_api_error(self) -> None:
        _server, api_url = self._start_slack_server(
            {"ok": False, "error": "channel_not_found"}
        )

        result = self.run_cli(
            [
                "--api-url",
                api_url,
                "--channel",
                "C404",
                "--token",
                "xoxb-test-token",
                "hello",
            ]
        )

        self.assertEqual(result.returncode, 1)
        self.assertIn("Slack API error: channel_not_found", result.stderr)
        self.assertNotIn("xoxb-test-token", result.stderr)

    def _start_slack_server(
        self,
        response_payload: dict[str, object],
        *,
        response_status: int = 200,
    ) -> tuple[HTTPServer, str]:
        server = HTTPServer(("127.0.0.1", 0), _SlackHandler)
        server.requests = []  # type: ignore[attr-defined]
        server.response_payload = response_payload  # type: ignore[attr-defined]
        server.response_status = response_status  # type: ignore[attr-defined]
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(thread.join, 1)
        self.addCleanup(server.shutdown)
        host, port = server.server_address
        return server, f"http://{host}:{port}/api/chat.postMessage"


if __name__ == "__main__":
    unittest.main()
