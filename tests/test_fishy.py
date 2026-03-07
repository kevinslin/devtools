from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import time
import unittest
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "bin" / "fishy"


class FishyCliTest(unittest.TestCase):
    def test_serves_mermaid_from_stdin(self) -> None:
        diagram = "graph TD\\n    A[Start] --> B{Decide}\\n    B -->|Yes| C[Ship]\\n"
        proc = self._start_cli(diagram)
        self.addCleanup(self._stop_process, proc)

        startup_line, url = self._wait_for_url(proc)
        with urlopen(url, timeout=5) as response:
            body = response.read().decode("utf-8")

        self.assertIn("fishy serving Mermaid preview", startup_line)
        self.assertIn("Fishy Mermaid Preview", body)
        self.assertIn("graph TD", body)
        self.assertIn("A[Start]", body)
        self.assertIn("/source.mmd", body)
        self.assertIn("cdn.jsdelivr.net/npm/mermaid", body)

        with urlopen(f"{url}/source.mmd", timeout=5) as response:
            source_body = response.read().decode("utf-8")
        self.assertEqual(source_body, diagram)

    def test_strips_markdown_fence_from_stdin(self) -> None:
        fenced_diagram = (
            "```mermaid\n"
            "sequenceDiagram\n"
            "    participant A as Alpha\n"
            "    participant B as Beta\n"
            "    A->>B: hello\n"
            "```\n"
        )
        proc = self._start_cli(fenced_diagram)
        self.addCleanup(self._stop_process, proc)

        _, url = self._wait_for_url(proc)
        with urlopen(url, timeout=5) as response:
            body = response.read().decode("utf-8")
        with urlopen(f"{url}/source.mmd", timeout=5) as response:
            source_body = response.read().decode("utf-8")

        self.assertIn("sequenceDiagram", body)
        self.assertNotIn("```mermaid", body)
        self.assertEqual(
            source_body,
            "sequenceDiagram\n    participant A as Alpha\n    participant B as Beta\n    A->>B: hello",
        )

    def test_rejects_empty_input(self) -> None:
        env = os.environ.copy()
        result = subprocess.run(
            [sys.executable, str(CLI), "--no-open"],
            cwd=ROOT,
            env=env,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(result.returncode, 1)
        self.assertIn("Mermaid definition is empty", result.stderr)

    def _start_cli(self, diagram: str) -> subprocess.Popen[str]:
        env = os.environ.copy()
        proc = subprocess.Popen(
            [sys.executable, str(CLI), "--no-open", "--port", "0"],
            cwd=ROOT,
            env=env,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        assert proc.stdin is not None
        proc.stdin.write(diagram)
        proc.stdin.close()
        return proc

    def _wait_for_url(self, proc: subprocess.Popen[str]) -> tuple[str, str]:
        assert proc.stdout is not None

        deadline = time.time() + 10
        while time.time() < deadline:
            line = proc.stdout.readline()
            if not line:
                if proc.poll() is not None:
                    stderr = proc.stderr.read() if proc.stderr is not None else ""
                    self.fail(f"fishy exited early: {stderr}")
                continue
            if "http://" in line:
                parts = line.strip().split()
                return line, parts[-1]

        self.fail("timed out waiting for fishy URL")

    def _stop_process(self, proc: subprocess.Popen[str]) -> None:
        try:
            if proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait(timeout=5)
        finally:
            if proc.stdin is not None and not proc.stdin.closed:
                proc.stdin.close()
            if proc.stdout is not None and not proc.stdout.closed:
                proc.stdout.close()
            if proc.stderr is not None and not proc.stderr.closed:
                proc.stderr.close()


if __name__ == "__main__":
    unittest.main()
