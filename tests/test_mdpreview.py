from __future__ import annotations

from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from urllib.request import urlopen


ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "bin" / "mdpreview"


class MdPreviewCliTest(unittest.TestCase):
    def test_serves_markdown_from_stdin_with_plugins(self) -> None:
        markdown = (
            "# Project Plan\n\n"
            "- [x] Ship `mdpreview`\n"
            "- [ ] Write docs\n\n"
            "Visit [example](https://example.com).\n"
        )
        proc = self._start_cli(["--no-open", "--port", "0"], stdin_text=markdown)
        self.addCleanup(self._stop_process, proc)

        startup_line, url = self._wait_for_url(proc)
        with urlopen(url, timeout=5) as response:
            body = response.read().decode("utf-8")
        with urlopen(f"{url}/source.md", timeout=5) as response:
            source_body = response.read().decode("utf-8")

        self.assertIn("mdpreview serving Markdown preview", startup_line)
        self.assertIn('id="project-plan"', body)
        self.assertIn('class="header-anchor" href="#project-plan"', body)
        self.assertIn('class="task-list-item"', body)
        self.assertIn('class="task-list-item-checkbox" type="checkbox" disabled checked', body)
        self.assertIn('class="task-list-item-checkbox" type="checkbox" disabled>', body)
        self.assertIn('target="_blank"', body)
        self.assertIn('rel="noreferrer noopener"', body)
        self.assertEqual(source_body, markdown)

    def test_reads_markdown_from_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source_path = Path(tmp) / "notes.md"
            source_path.write_text("## Local File\n\nParagraph.\n", encoding="utf-8")

            proc = self._start_cli(
                ["--no-open", "--port", "0", str(source_path)],
                stdin_text=None,
            )
            self.addCleanup(self._stop_process, proc)

            _, url = self._wait_for_url(proc)
            with urlopen(url, timeout=5) as response:
                body = response.read().decode("utf-8")

            self.assertIn("<title>notes.md</title>", body)
            self.assertIn('id="local-file"', body)
            self.assertIn("<p>Paragraph.</p>", body)

    def test_rejects_empty_input(self) -> None:
        result = subprocess.run(
            [sys.executable, str(CLI), "--no-open"],
            cwd=ROOT,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(result.returncode, 1)
        self.assertIn("Markdown input is empty", result.stderr)

    def _start_cli(
        self,
        args: list[str],
        *,
        stdin_text: str | None,
    ) -> subprocess.Popen[str]:
        proc = subprocess.Popen(
            [sys.executable, str(CLI), *args],
            cwd=ROOT,
            stdin=subprocess.PIPE if stdin_text is not None else subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        if stdin_text is not None:
            assert proc.stdin is not None
            proc.stdin.write(stdin_text)
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
                    self.fail(f"mdpreview exited early: {stderr}")
                continue
            if "http://" in line:
                parts = line.strip().split()
                return line, parts[-1]

        self.fail("timed out waiting for mdpreview URL")

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
