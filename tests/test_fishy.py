from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import tempfile
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
        self.assertIn("note-hover-tooltip", body)
        self.assertIn("installNoteHoverTooltips", body)
        self.assertIn("diagram-fit-button", body)
        self.assertIn("diagram-zoom-in-button", body)
        self.assertIn("diagram-viewport", body)
        self.assertIn("Fit width", body)
        self.assertIn("installDiagramPointerControls", body)
        self.assertIn("pointerdown", body)
        self.assertIn("dblclick", body)

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

    def test_source_file_extracts_mermaid_blocks_with_section_titles_and_refresh_version(self) -> None:
        markdown_source = (
            "# System Overview\n"
            "\n"
            "```mermaid\n"
            "graph TD\n"
            "    A[Start] --> B[Done]\n"
            "```\n"
            "\n"
            "```python\n"
            "print('not mermaid')\n"
            "```\n"
            "\n"
            "## Retry Flow\n"
            "\n"
            "```mermaid\n"
            "sequenceDiagram\n"
            "    participant C as Client\n"
            "    participant S as Server\n"
            "    C->>S: retry\n"
            "```\n"
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            source_file = Path(temp_dir) / "design.md"
            source_file.write_text(markdown_source, encoding="utf-8")
            proc = self._start_cli_for_source_file(source_file)
            self.addCleanup(self._stop_process, proc)

            _, url = self._wait_for_url(proc)
            with urlopen(url, timeout=5) as response:
                body = response.read().decode("utf-8")
            with urlopen(f"{url}/source.mmd", timeout=5) as response:
                source_body = response.read().decode("utf-8")
            with urlopen(f"{url}/version", timeout=5) as response:
                first_version = response.read().decode("utf-8")

            self.assertIn("Rendering 2 Mermaid blocks", body)
            self.assertIn('data-diagram-index="1"', body)
            self.assertIn('data-diagram-index="2"', body)
            self.assertIn("System Overview", body)
            self.assertIn("Retry Flow", body)
            self.assertIn("graph TD", body)
            self.assertIn("sequenceDiagram", body)
            self.assertNotIn("print(&#x27;not mermaid&#x27;)", body)
            self.assertIn("installSourceFileRefresh", body)
            self.assertIn("/version?ts=", body)
            self.assertEqual(source_body, markdown_source)

            time.sleep(0.01)
            source_file.write_text(markdown_source + "\n<!-- changed -->\n", encoding="utf-8")
            with urlopen(f"{url}/version", timeout=5) as response:
                second_version = response.read().decode("utf-8")

            self.assertNotEqual(first_version, second_version)

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

    def _start_cli_for_source_file(self, source_file: Path) -> subprocess.Popen[str]:
        env = os.environ.copy()
        return subprocess.Popen(
            [
                sys.executable,
                str(CLI),
                "--source-file",
                str(source_file),
                "--no-open",
                "--port",
                "0",
            ],
            cwd=ROOT,
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

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
