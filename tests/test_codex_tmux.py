from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import textwrap
import unittest


ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "bin" / "codex-tmux"


def _write_executable(path: Path, text: str) -> None:
    path.write_text(textwrap.dedent(text).lstrip(), encoding="utf-8")
    path.chmod(0o755)


class CodexTmuxCliTest(unittest.TestCase):
    def run_cli(self, *args: str) -> subprocess.CompletedProcess[str]:
        with tempfile.TemporaryDirectory() as tmp:
            fake_bin = Path(tmp)
            _write_executable(
                fake_bin / "tmux",
                """\
                #!/usr/bin/env python3
                import sys

                args = sys.argv[1:]
                if args[:1] == ["list-panes"]:
                    print("work\\t0\\tcodex\\t0\\t%1\\t100\\tzsh\\t/repo/one\\t1")
                    print("work\\t1\\tshell\\t0\\t%2\\t300\\tzsh\\t/repo/two\\t0")
                    print("work\\t2\\treview\\t1\\t%3\\t400\\tzsh\\t/repo/three\\t0")
                    print("work\\t3\\tidle\\t0\\t%4\\t600\\tzsh\\t/repo/four\\t0")
                    print("work\\t4\\tdirect\\t0\\t%5\\t800\\tcodex\\t/repo/five\\t0")
                    raise SystemExit(0)
                if args[:1] == ["capture-pane"]:
                    target = args[args.index("-t") + 1]
                    if target == "%1":
                        print("Running command: python tests.py")
                    elif target == "%3":
                        print("Do you want to allow this command?")
                    elif target == "%4":
                        print("Ask Codex to do something")
                    elif target == "%5":
                        print("Press enter to continue")
                    raise SystemExit(0)
                raise SystemExit(2)
                """,
            )
            _write_executable(
                fake_bin / "ps",
                """\
                #!/usr/bin/env python3
                print("100 1 Ss /bin/zsh zsh")
                print("200 100 S /opt/homebrew/bin/codex codex")
                print("210 200 S /bin/zsh zsh -lc python tests.py")
                print("211 210 S /usr/bin/python python tests.py")
                print("300 1 Ss /bin/zsh zsh")
                print("400 1 Ss /bin/zsh zsh")
                print("500 400 S /usr/local/bin/node node /tmp/node_modules/@openai/codex/bin/codex.js")
                print("510 500 S python python /repo/mcp_identity_proxy.py mcp=https://example.test/mcp")
                print("600 1 Ss /bin/zsh zsh")
                print("700 600 S /opt/homebrew/bin/codex codex")
                print("710 700 S python python /repo/js_mcp.py")
                print("800 1 S /Users/me/.cache/codex/codex codex --profile xxhigh")
                """,
            )

            env = os.environ.copy()
            env["PATH"] = f"{fake_bin}{os.pathsep}{env['PATH']}"
            return subprocess.run(
                [sys.executable, str(CLI), *args],
                cwd=ROOT,
                env=env,
                capture_output=True,
                text=True,
                check=False,
            )

    def test_json_inventory_reports_only_codex_panes_by_default(self) -> None:
        result = self.run_cli("--format", "json")

        self.assertEqual(result.returncode, 0, msg=result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["pane_count"], 5)
        self.assertEqual(payload["codex_pane_count"], 4)

        panes = {pane["pane_id"]: pane for pane in payload["panes"]}
        self.assertEqual(set(panes), {"%1", "%3", "%4", "%5"})
        self.assertEqual(panes["%1"]["state"], "running-tool")
        self.assertIn("python", panes["%1"]["state_evidence"])
        self.assertEqual(panes["%3"]["state"], "needs-approval")
        self.assertEqual(panes["%3"]["codex_pid"], 500)
        self.assertEqual(panes["%3"]["codex_helper_count"], 1)
        self.assertEqual(panes["%4"]["state"], "idle")
        self.assertEqual(panes["%5"]["codex_pid"], 800)
        self.assertEqual(panes["%5"]["pane_display_id"], "5")
        self.assertEqual(panes["%5"]["state"], "idle")

    def test_all_includes_non_codex_panes(self) -> None:
        result = self.run_cli("--all", "--format", "json")

        self.assertEqual(result.returncode, 0, msg=result.stderr)
        payload = json.loads(result.stdout)
        panes = {pane["pane_id"]: pane for pane in payload["panes"]}
        self.assertEqual(panes["%2"]["codex"], False)
        self.assertEqual(panes["%2"]["state"], "not-codex")

    def test_table_output_is_human_readable(self) -> None:
        result = self.run_cli()

        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertIn("LOCATION", result.stdout)
        self.assertIn("running-tool", result.stdout)
        self.assertIn("needs-approval", result.stdout)
        self.assertIn("idle", result.stdout)
        self.assertNotIn("%2", result.stdout)
        self.assertNotIn("%1", result.stdout)
        self.assertIn("1     codex", result.stdout)


if __name__ == "__main__":
    unittest.main()
