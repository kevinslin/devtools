from __future__ import annotations

import base64
import json
from pathlib import Path
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "bin" / "jwtio"


def _base64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _make_jwt(
    *, header: dict[str, object], payload: dict[str, object], signature: bytes = b"signature"
) -> str:
    return ".".join(
        [
            _base64url(json.dumps(header, separators=(",", ":")).encode("utf-8")),
            _base64url(json.dumps(payload, separators=(",", ":")).encode("utf-8")),
            _base64url(signature),
        ]
    )


class JwtioCliTest(unittest.TestCase):
    def run_cli(
        self, stdin_text: str | None, *args: str
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(CLI), *args],
            cwd=ROOT,
            input=stdin_text,
            capture_output=True,
            text=True,
            check=False,
        )

    def test_decodes_jwt_from_stdin(self) -> None:
        token = _make_jwt(
            header={"alg": "HS256", "typ": "JWT"},
            payload={"sub": "123", "name": "Jane Doe", "admin": True},
        )

        result = self.run_cli(f"{token}\n")

        self.assertEqual(result.returncode, 0, msg=result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["header"], {"alg": "HS256", "typ": "JWT"})
        self.assertEqual(
            payload["payload"],
            {"sub": "123", "name": "Jane Doe", "admin": True},
        )
        self.assertEqual(payload["signature"], _base64url(b"signature"))

    def test_accepts_bearer_prefix(self) -> None:
        token = _make_jwt(
            header={"alg": "none", "typ": "JWT"},
            payload={"scope": ["read", "write"]},
            signature=b"",
        )

        result = self.run_cli(f"Bearer\n{token}\n")

        self.assertEqual(result.returncode, 0, msg=result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["header"]["alg"], "none")
        self.assertEqual(payload["payload"]["scope"], ["read", "write"])
        self.assertEqual(payload["signature"], "")

    def test_accepts_explicit_stdin_marker(self) -> None:
        token = _make_jwt(
            header={"alg": "HS256", "typ": "JWT"},
            payload={"sub": "stdin-marker"},
        )

        result = self.run_cli(f"{token}\n", "-")

        self.assertEqual(result.returncode, 0, msg=result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["payload"]["sub"], "stdin-marker")

    def test_rejects_empty_input(self) -> None:
        result = self.run_cli("")

        self.assertEqual(result.returncode, 1)
        self.assertIn("JWT input is empty", result.stderr)

    def test_rejects_invalid_segment_count(self) -> None:
        result = self.run_cli("abc.def\n")

        self.assertEqual(result.returncode, 1)
        self.assertIn("3 dot-separated segments", result.stderr)

    def test_rejects_non_json_payload(self) -> None:
        token = ".".join(
            [
                _base64url(b'{"alg":"HS256","typ":"JWT"}'),
                _base64url(b"not json"),
                _base64url(b"sig"),
            ]
        )

        result = self.run_cli(f"{token}\n")

        self.assertEqual(result.returncode, 1)
        self.assertIn("payload segment is not valid JSON", result.stderr)


if __name__ == "__main__":
    unittest.main()
