from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[1]
EXTENSION_ROOT = ROOT / "apps" / "ctrl-tab-chrome"


class CtrlTabChromeExtensionTest(unittest.TestCase):
    def test_manifest_declares_local_extension(self) -> None:
        manifest = json.loads((EXTENSION_ROOT / "manifest.json").read_text())

        self.assertEqual(manifest["manifest_version"], 3)
        self.assertEqual(manifest["name"], "ctrl-tab-chrome")
        self.assertEqual(manifest["background"]["service_worker"], "background.js")
        self.assertIn("tabs", manifest["permissions"])
        self.assertIn("storage", manifest["permissions"])
        self.assertIn("<all_urls>", manifest["host_permissions"])
        self.assertEqual(manifest["content_scripts"][0]["js"], ["content-script.js"])
        self.assertEqual(manifest["content_scripts"][0]["matches"], ["<all_urls>"])
        self.assertTrue(manifest["content_scripts"][0]["all_frames"])

    def test_ctrl_tab_content_script_wiring(self) -> None:
        content_script = (EXTENSION_ROOT / "content-script.js").read_text()

        self.assertIn('event.key === "Tab"', content_script)
        self.assertIn("event.ctrlKey", content_script)
        self.assertIn("event.preventDefault()", content_script)
        self.assertIn("event.stopImmediatePropagation()", content_script)
        self.assertIn("ctrl-tab-chrome.switchToLastUsedTab", content_script)
        self.assertIn("{ capture: true }", content_script)

    def test_background_tracks_window_scoped_mru_history(self) -> None:
        background = (EXTENSION_ROOT / "background.js").read_text()

        self.assertIn("const historyByWindowId = new Map()", background)
        self.assertIn("chrome.storage.session", background)
        self.assertIn("chrome.tabs.onActivated.addListener", background)
        self.assertIn("chrome.tabs.update(tabId, { active: true })", background)
        self.assertIn("tab.windowId !== windowId", background)
        self.assertIn("chrome.windows.update(windowId, { focused: true })", background)

    def test_javascript_syntax(self) -> None:
        node = shutil.which("node")
        if node is None:
            self.skipTest("node is not installed")

        for path in ["background.js", "content-script.js"]:
            result = subprocess.run(
                [node, "--check", str(EXTENSION_ROOT / path)],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, msg=result.stderr)


if __name__ == "__main__":
    unittest.main()
