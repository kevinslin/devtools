from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import unittest
import uuid

ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "bin" / "mdpaste"

WRITE_PASTEBOARD_SCRIPT = r"""
ObjC.import('AppKit')
ObjC.import('Foundation')

function run(argv) {
  var pasteboard = $.NSPasteboard.pasteboardWithName($(argv[0]))
  pasteboard.clearContents

  if (argv.length < 2) {
    return
  }

  var data = $.NSData.dataWithContentsOfFile($(argv[1]))
  var text = $.NSString.alloc.initWithDataEncoding(data, $.NSUTF8StringEncoding)
  if (!pasteboard.setStringForType(text, $.NSPasteboardTypeString)) {
    throw new Error('Failed to seed test pasteboard.')
  }
}
"""

READ_PASTEBOARD_SCRIPT = r"""
ObjC.import('AppKit')
ObjC.import('Foundation')

function maybeDecodeUtf8(data) {
  if (!data) {
    return null
  }
  var text = $.NSString.alloc.initWithDataEncoding(data, $.NSUTF8StringEncoding)
  if (!text) {
    return null
  }
  return ObjC.unwrap(text)
}

function maybeDecodeAscii(data) {
  if (!data) {
    return null
  }
  var text = $.NSString.alloc.initWithDataEncoding(data, $.NSASCIIStringEncoding)
  if (!text) {
    return null
  }
  return ObjC.unwrap(text)
}

function run(argv) {
  var pasteboard = $.NSPasteboard.pasteboardWithName($(argv[0]))
  var payload = {
    plain_text: null,
    html_text: null,
    rtf_text: null
  }

  var plainText = pasteboard.stringForType($.NSPasteboardTypeString)
  if (plainText) {
    payload.plain_text = ObjC.unwrap(plainText)
  }

  payload.html_text = maybeDecodeUtf8(pasteboard.dataForType($.NSPasteboardTypeHTML))
  payload.rtf_text = maybeDecodeAscii(pasteboard.dataForType($.NSPasteboardTypeRTF))

  console.log(JSON.stringify(payload))
}
"""


class MdPasteCliTest(unittest.TestCase):
    def run_cli(self, pasteboard_name: str) -> subprocess.CompletedProcess[str]:
        env = os.environ.copy()
        env["MDPASTE_PASTEBOARD_NAME"] = pasteboard_name
        return subprocess.run(
            [sys.executable, str(CLI)],
            cwd=ROOT,
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )

    def test_converts_clipboard_markdown_to_html_and_rtf(self) -> None:
        pasteboard_name = self._pasteboard_name()
        markdown_text = (
            "# Title\n\n"
            "- first item\n"
            "- second item\n\n"
            "Use **bold**, *italics*, `code`, and a [link](https://example.com).\n"
        )
        self._write_pasteboard(pasteboard_name, markdown_text)

        result = self.run_cli(pasteboard_name)

        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertIn("Converted clipboard Markdown to rich text.", result.stdout)

        payload = self._read_pasteboard(pasteboard_name)
        self.assertEqual(payload["plain_text"], markdown_text)
        self.assertIn("<h1>Title</h1>", payload["html_text"])
        self.assertIn("<li>first item</li>", payload["html_text"])
        self.assertIn("<strong>bold</strong>", payload["html_text"])
        self.assertIn('<a href="https://example.com">link</a>', payload["html_text"])
        self.assertIn(r"{\rtf1", payload["rtf_text"])
        self.assertIn(r"\b", payload["rtf_text"])

    def test_rejects_empty_clipboard(self) -> None:
        pasteboard_name = self._pasteboard_name()
        self._write_pasteboard(pasteboard_name, None)

        result = self.run_cli(pasteboard_name)

        self.assertEqual(result.returncode, 1)
        self.assertIn("Clipboard Markdown is empty.", result.stderr)

    def _pasteboard_name(self) -> str:
        return f"com.codex.mdpaste.tests.{uuid.uuid4()}"

    def _run_jxa(self, script: str, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["osascript", "-l", "JavaScript", "-e", script, *args],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )

    def _write_pasteboard(self, pasteboard_name: str, text: str | None) -> None:
        text_path: Path | None = None
        args = [pasteboard_name]
        if text is not None:
            text_path = ROOT / ".pytest_cache" / f"{uuid.uuid4()}.txt"
            text_path.parent.mkdir(parents=True, exist_ok=True)
            text_path.write_text(text, encoding="utf-8")
            self.addCleanup(text_path.unlink, missing_ok=True)
            args.append(str(text_path))

        result = self._run_jxa(WRITE_PASTEBOARD_SCRIPT, *args)
        self.assertEqual(result.returncode, 0, msg=result.stderr)

    def _read_pasteboard(self, pasteboard_name: str) -> dict[str, str | None]:
        result = self._run_jxa(READ_PASTEBOARD_SCRIPT, pasteboard_name)
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        payload = result.stdout.strip() or result.stderr.strip()
        return json.loads(payload)


if __name__ == "__main__":
    unittest.main()
