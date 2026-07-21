from __future__ import annotations

import json
import os
from pathlib import Path
import socket
import stat
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "bin" / "sshx"


def _write_file(path: Path, content: str = "") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _write_fake_exec(path: Path, *, log_path: Path, exit_code: int = 0) -> None:
    path.write_text(
        (
            "#!/usr/bin/env python3\n"
            "import json\n"
            "import os\n"
            "from pathlib import Path\n"
            "import sys\n"
            f"Path({str(log_path)!r}).write_text("
            "json.dumps({'argv': sys.argv[1:], 'cwd': os.getcwd()}),"
            " encoding='utf-8')\n"
            f"raise SystemExit({exit_code})\n"
        ),
        encoding="utf-8",
    )
    path.chmod(0o755)


def _write_retrying_fake_exec(
    path: Path,
    *,
    log_path: Path,
    state_path: Path,
    initial_exit_code: int,
    subsequent_exit_code: int = 0,
) -> None:
    path.write_text(
        (
            "#!/usr/bin/env python3\n"
            "import json\n"
            "import os\n"
            "from pathlib import Path\n"
            "import sys\n"
            f"log_path = Path({str(log_path)!r})\n"
            f"state_path = Path({str(state_path)!r})\n"
            "if state_path.exists():\n"
            "    count = int(state_path.read_text(encoding='utf-8'))\n"
            "else:\n"
            "    count = 0\n"
            "state_path.write_text(str(count + 1), encoding='utf-8')\n"
            "log_path.write_text(\n"
            "    json.dumps({'argv': sys.argv[1:], 'cwd': os.getcwd(), 'count': count + 1}),\n"
            "    encoding='utf-8',\n"
            ")\n"
            f"raise SystemExit({initial_exit_code} if count == 0 else {subsequent_exit_code})\n"
        ),
        encoding="utf-8",
    )
    path.chmod(0o755)


def _write_fake_tar(path: Path, *, log_path: Path, payload: bytes = b"archive") -> None:
    path.write_text(
        (
            "#!/usr/bin/env python3\n"
            "import json\n"
            "import os\n"
            "from pathlib import Path\n"
            "import sys\n"
            f"Path({str(log_path)!r}).write_text("
            "json.dumps({'argv': sys.argv[1:], 'cwd': os.getcwd()}),"
            " encoding='utf-8')\n"
            f"sys.stdout.buffer.write({payload!r})\n"
        ),
        encoding="utf-8",
    )
    path.chmod(0o755)


def _write_fake_ssh_append(
    path: Path,
    *,
    log_path: Path,
    rsync_available: bool = True,
) -> None:
    path.write_text(
        (
            "#!/usr/bin/env python3\n"
            "import json\n"
            "import os\n"
            "from pathlib import Path\n"
            "import sys\n"
            "argv = sys.argv[1:]\n"
            "stdin_len = 0\n"
            "if argv and ('tar -xzf' in argv[-1] or '.zshrc.local.sshx.' in argv[-1]):\n"
            "    stdin_len = len(sys.stdin.buffer.read())\n"
            "payload = {'argv': argv, 'cwd': os.getcwd(), 'stdin_len': stdin_len}\n"
            f"log_path = Path({str(log_path)!r})\n"
            "calls = json.loads(log_path.read_text(encoding='utf-8')) if log_path.exists() else []\n"
            "calls.append(payload)\n"
            "log_path.write_text(json.dumps(calls), encoding='utf-8')\n"
            "if argv and argv[-1] == 'command -v rsync >/dev/null 2>&1':\n"
            f"    raise SystemExit({0 if rsync_available else 1})\n"
        ),
        encoding="utf-8",
    )
    path.chmod(0o755)


def _write_fake_ssh_remote(path: Path, *, remote_home: Path) -> None:
    path.write_text(
        (
            "#!/usr/bin/env python3\n"
            "import os\n"
            "from pathlib import Path\n"
            "import subprocess\n"
            "import sys\n"
            f"remote_home = Path({str(remote_home)!r})\n"
            "argv = sys.argv[1:]\n"
            "if not argv or len(argv) == 1:\n"
            "    raise SystemExit(0)\n"
            "command = argv[-1]\n"
            "if command == 'command -v rsync >/dev/null 2>&1':\n"
            "    raise SystemExit(1)\n"
            "env = os.environ.copy()\n"
            "env['HOME'] = str(remote_home)\n"
            "result = subprocess.run(\n"
            "    ['zsh', '-c', command],\n"
            "    stdin=sys.stdin.buffer,\n"
            "    env=env,\n"
            "    check=False,\n"
            ")\n"
            "raise SystemExit(result.returncode)\n"
        ),
        encoding="utf-8",
    )
    path.chmod(0o755)


def _read_log(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_calls(path: Path) -> list[dict[str, object]]:
    return json.loads(path.read_text(encoding="utf-8"))


def _expected_tar_args(*paths: str, excludes: tuple[str, ...] = ()) -> list[str]:
    metadata_flags = (
        ["--no-xattrs", "--no-mac-metadata"] if sys.platform == "darwin" else []
    )
    return [
        "-czhf",
        "-",
        *metadata_flags,
        "--exclude=*.sock",
        "--exclude=*.socket",
        *[f"--exclude={path}" for path in excludes],
        "--",
        *paths,
    ]


class SshxCliTest(unittest.TestCase):
    def run_cli(
        self,
        args: list[str],
        *,
        home: Path,
        ssh_bin: Path,
        rsync_bin: Path,
        tar_bin: Path | None = None,
        extra_env: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        env = os.environ.copy()
        env["HOME"] = str(home)
        env["SSHX_SSH_BIN"] = str(ssh_bin)
        env["SSHX_RSYNC_BIN"] = str(rsync_bin)
        if tar_bin is not None:
            env["SSHX_TAR_BIN"] = str(tar_bin)
        if extra_env is not None:
            env.update(extra_env)
        return subprocess.run(
            [sys.executable, str(CLI), *args],
            cwd=ROOT,
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )

    def test_syncs_existing_default_paths_then_opens_ssh(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            home = tmp_path / "home"
            home.mkdir()
            _write_file(home / ".codex" / "agents" / "assistant.md", "# assistant\n")
            _write_file(home / ".codex" / "config.toml", "model = \"gpt-5\"\n")
            _write_file(home / ".codex" / "hooks" / "gh_action_check.py", "#!/usr/bin/env python3\n")
            _write_file(home / ".codex" / "hooks.json", "{\n  \"hooks\": []\n}\n")
            _write_file(home / ".codex" / "rules" / "default.md", "# rules\n")
            _write_file(home / ".codex" / "skills" / "demo" / "SKILL.md", "# demo\n")
            _write_file(home / ".zshrc", "export PATH=/usr/local/bin:$PATH\n")
            _write_file(home / ".gitconfig", "[user]\nname = Test User\n")
            _write_file(
                home / ".config" / "git" / "config",
                "[init]\ndefaultBranch = main\n",
            )
            _write_file(home / ".config" / "nvim" / "init.lua", "vim.o.number = true\n")

            rsync_log = tmp_path / "rsync.json"
            ssh_log = tmp_path / "ssh.json"
            rsync_bin = tmp_path / "fake-rsync"
            ssh_bin = tmp_path / "fake-ssh"
            _write_fake_exec(rsync_bin, log_path=rsync_log)
            _write_fake_ssh_append(ssh_bin, log_path=ssh_log)

            result = self.run_cli(
                ["-i", "/tmp/custom-key", "devbox"],
                home=home,
                ssh_bin=ssh_bin,
                rsync_bin=rsync_bin,
            )

            self.assertEqual(result.returncode, 0, msg=result.stderr)

            rsync_payload = _read_log(rsync_log)
            self.assertEqual(Path(str(rsync_payload["cwd"])).resolve(), home.resolve())
            self.assertEqual(
                rsync_payload["argv"][:4],
                ["-az", "--relative", "-e", f"{ssh_bin} -i /tmp/custom-key"],
            )
            self.assertNotIn("./.zshrc", rsync_payload["argv"])
            self.assertIn("./.codex/agents", rsync_payload["argv"])
            self.assertIn("./.codex/config.toml", rsync_payload["argv"])
            self.assertIn("./.codex/hooks", rsync_payload["argv"])
            self.assertIn("./.codex/hooks.json", rsync_payload["argv"])
            self.assertIn("./.codex/rules", rsync_payload["argv"])
            self.assertIn("./.codex/skills", rsync_payload["argv"])
            self.assertNotIn("./.gitconfig", rsync_payload["argv"])
            self.assertIn("./.config/git", rsync_payload["argv"])
            self.assertIn("./.config/nvim", rsync_payload["argv"])
            self.assertEqual(rsync_payload["argv"][-1], "devbox:~/")

            ssh_calls = _read_calls(ssh_log)
            self.assertEqual(
                ssh_calls[0]["argv"],
                [
                    "-n",
                    "-i",
                    "/tmp/custom-key",
                    "devbox",
                    "command -v rsync >/dev/null 2>&1",
                ],
            )
            self.assertIn(".zshrc.local.sshx.", ssh_calls[1]["argv"][-1])
            self.assertEqual(
                ssh_calls[1]["stdin_len"],
                len((ROOT / "config" / "sshx" / "zshrc.remote.local").read_bytes()),
            )
            self.assertEqual(
                ssh_calls[2]["argv"],
                ["-i", "/tmp/custom-key", "devbox"],
            )

    def test_supports_extra_paths_and_remote_command(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            home = tmp_path / "home"
            home.mkdir()
            _write_file(home / ".tmux.conf", "set -g mouse on\n")
            _write_file(home / ".config" / "custom-tool" / "config.toml", "enabled = true\n")

            rsync_log = tmp_path / "rsync.json"
            ssh_log = tmp_path / "ssh.json"
            rsync_bin = tmp_path / "fake-rsync"
            ssh_bin = tmp_path / "fake-ssh"
            _write_fake_exec(rsync_bin, log_path=rsync_log)
            _write_fake_exec(ssh_bin, log_path=ssh_log)

            result = self.run_cli(
                [
                    "--no-defaults",
                    "--path",
                    ".tmux.conf",
                    "--path",
                    ".config/custom-tool",
                    "devbox",
                    "uname",
                    "-a",
                ],
                home=home,
                ssh_bin=ssh_bin,
                rsync_bin=rsync_bin,
            )

            self.assertEqual(result.returncode, 0, msg=result.stderr)

            rsync_payload = _read_log(rsync_log)
            self.assertEqual(
                rsync_payload["argv"],
                [
                    "-az",
                    "--relative",
                    "-e",
                    str(ssh_bin),
                    "./.tmux.conf",
                    "./.config/custom-tool",
                    "devbox:~/",
                ],
            )

            ssh_payload = _read_log(ssh_log)
            self.assertEqual(
                ssh_payload["argv"],
                ["devbox", "uname", "-a"],
            )

    def test_work_profile_uses_safe_overlay_instead_of_local_zshrc(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            home = tmp_path / "home"
            home.mkdir()
            _write_file(home / ".zshrc", "export PATH=/usr/local/bin:$PATH\n")
            _write_file(home / ".gitconfig", "[user]\nname = Work User\n")
            _write_file(
                home / ".config" / "git" / "config",
                "[init]\ndefaultBranch = main\n",
            )
            _write_file(home / ".codex" / "config.toml", "model = \"gpt-5\"\n")

            rsync_log = tmp_path / "rsync.json"
            ssh_log = tmp_path / "ssh.json"
            rsync_bin = tmp_path / "fake-rsync"
            ssh_bin = tmp_path / "fake-ssh"
            _write_fake_exec(rsync_bin, log_path=rsync_log)
            _write_fake_ssh_append(ssh_bin, log_path=ssh_log)

            result = self.run_cli(
                ["--profile", "work", "devbox"],
                home=home,
                ssh_bin=ssh_bin,
                rsync_bin=rsync_bin,
            )

            self.assertEqual(result.returncode, 0, msg=result.stderr)

            rsync_payload = _read_log(rsync_log)
            self.assertNotIn("./.zshrc", rsync_payload["argv"])
            self.assertNotIn("./.gitconfig", rsync_payload["argv"])
            self.assertIn("./.config/git", rsync_payload["argv"])
            self.assertIn("./.codex/config.toml", rsync_payload["argv"])
            ssh_calls = _read_calls(ssh_log)
            self.assertIn(".zshrc.local.sshx.", ssh_calls[-2]["argv"][-1])
            self.assertGreater(ssh_calls[-2]["stdin_len"], 0)

    def test_profile_paths_can_be_loaded_from_yaml_config(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            home = tmp_path / "home"
            home.mkdir()
            _write_file(home / ".custom-default", "default\n")
            _write_file(home / ".custom-work", "work\n")
            config_path = tmp_path / "config.yaml"
            _write_file(
                config_path,
                (
                    "profiles:\n"
                    "  default:\n"
                    "    - .custom-default\n"
                    "  work:\n"
                    "    - .custom-work\n"
                ),
            )

            rsync_bin = tmp_path / "fake-rsync"
            ssh_bin = tmp_path / "fake-ssh"

            default_result = self.run_cli(
                ["--dry-run", "--sync-method", "rsync", "devbox"],
                home=home,
                ssh_bin=ssh_bin,
                rsync_bin=rsync_bin,
                extra_env={"SSHX_CONFIG_PATH": str(config_path)},
            )

            self.assertEqual(default_result.returncode, 0, msg=default_result.stderr)
            self.assertIn("./.custom-default", default_result.stdout)
            self.assertNotIn("./.custom-work", default_result.stdout)

            work_result = self.run_cli(
                [
                    "--dry-run",
                    "--sync-method",
                    "rsync",
                    "--profile",
                    "work",
                    "devbox",
                ],
                home=home,
                ssh_bin=ssh_bin,
                rsync_bin=rsync_bin,
                extra_env={"SSHX_CONFIG_PATH": str(config_path)},
            )

            self.assertEqual(work_result.returncode, 0, msg=work_result.stderr)
            self.assertIn("./.custom-work", work_result.stdout)
            self.assertNotIn("./.custom-default", work_result.stdout)

    def test_missing_explicit_path_returns_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            home = tmp_path / "home"
            home.mkdir()

            rsync_log = tmp_path / "rsync.json"
            ssh_log = tmp_path / "ssh.json"
            rsync_bin = tmp_path / "fake-rsync"
            ssh_bin = tmp_path / "fake-ssh"
            _write_fake_exec(rsync_bin, log_path=rsync_log)
            _write_fake_exec(ssh_bin, log_path=ssh_log)

            result = self.run_cli(
                ["--no-defaults", "--path", ".missing", "devbox"],
                home=home,
                ssh_bin=ssh_bin,
                rsync_bin=rsync_bin,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("missing local path", result.stderr)
            self.assertFalse(rsync_log.exists())
            self.assertFalse(ssh_log.exists())

    def test_direct_zshrc_sync_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            home = tmp_path / "home"
            home.mkdir()
            _write_file(home / ".zshrc", "alias unsafe='true'\n")

            result = self.run_cli(
                ["--no-defaults", "--path", ".zshrc", "devbox"],
                home=home,
                ssh_bin=tmp_path / "fake-ssh",
                rsync_bin=tmp_path / "fake-rsync",
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("direct .zshrc sync is disabled", result.stderr)

    def test_zsh_overlay_validation_rejects_unsafe_content(self) -> None:
        unsafe_lines = (
            'export OPENAI_API_KEY="not-a-real-key"',
            'typeset -g OPENAI_API_KEY="not-a-real-key"',
            'export openai_api_key="not-a-real-key"',
            'export SSH_AUTH_SOCK="$HOME/local-agent.sock"',
            'source "/Users/test/.zshrc.local"',
        )
        for unsafe_line in unsafe_lines:
            with self.subTest(unsafe_line=unsafe_line), tempfile.TemporaryDirectory() as tmp:
                tmp_path = Path(tmp)
                home = tmp_path / "home"
                home.mkdir()
                config_path = tmp_path / "config.yaml"
                overlay_path = tmp_path / "zshrc.remote.local"
                _write_file(
                    config_path,
                    "profiles:\n  default:\n    - '@zsh-overlay'\n",
                )
                _write_file(
                    overlay_path,
                    f"typeset -g SSHX_ZSHRC_LOCAL_LOADED=1\n{unsafe_line}\n",
                )

                result = self.run_cli(
                    ["devbox"],
                    home=home,
                    ssh_bin=tmp_path / "fake-ssh",
                    rsync_bin=tmp_path / "fake-rsync",
                    extra_env={
                        "SSHX_CONFIG_PATH": str(config_path),
                        "SSHX_ZSH_OVERLAY_PATH": str(overlay_path),
                    },
                )

                self.assertNotEqual(result.returncode, 0)
                self.assertIn("invalid zsh overlay", result.stderr)

    def test_zsh_overlay_requires_uncommented_sentinel(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            home = tmp_path / "home"
            home.mkdir()
            config_path = tmp_path / "config.yaml"
            overlay_path = tmp_path / "zshrc.remote.local"
            _write_file(
                config_path,
                "profiles:\n  default:\n    - '@zsh-overlay'\n",
            )
            _write_file(overlay_path, "# typeset -g SSHX_ZSHRC_LOCAL_LOADED=1\n")

            result = self.run_cli(
                ["devbox"],
                home=home,
                ssh_bin=tmp_path / "fake-ssh",
                rsync_bin=tmp_path / "fake-rsync",
                extra_env={
                    "SSHX_CONFIG_PATH": str(config_path),
                    "SSHX_ZSH_OVERLAY_PATH": str(overlay_path),
                },
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn(
                "missing 'typeset -g SSHX_ZSHRC_LOCAL_LOADED=1'",
                result.stderr,
            )

    def test_zsh_overlay_merges_files_and_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            home = tmp_path / "home"
            remote_home = tmp_path / "remote-home"
            home.mkdir()
            remote_home.mkdir()
            base_zshrc = (
                "alias before='true'\n"
                '[[ -r "$HOME/.zshrc.local" ]] && source "$HOME/.zshrc.local"\n'
                "alias after='true'\n"
            )
            remote_local = "typeset -g REMOTE_ONLY=1\n"
            _write_file(remote_home / ".zshrc", base_zshrc)
            _write_file(remote_home / ".zshrc.local", remote_local)
            config_path = tmp_path / "config.yaml"
            overlay_path = tmp_path / "zshrc.remote.local"
            _write_file(
                config_path,
                "profiles:\n  default:\n    - '@zsh-overlay'\n",
            )
            _write_file(
                overlay_path,
                (
                    "typeset -g SSHX_ZSHRC_LOCAL_LOADED=1\n"
                    "[[ -o interactive ]] || return 0\n"
                    "alias dex='codex --profile gen'\n"
                ),
            )

            ssh_bin = tmp_path / "fake-ssh"
            _write_fake_ssh_remote(ssh_bin, remote_home=remote_home)
            environment = {
                "SSHX_CONFIG_PATH": str(config_path),
                "SSHX_ZSH_OVERLAY_PATH": str(overlay_path),
            }

            first_result: tuple[bytes, bytes] | None = None
            for attempt in range(2):
                result = self.run_cli(
                    ["--sync-method", "tar", "devbox", "true"],
                    home=home,
                    ssh_bin=ssh_bin,
                    rsync_bin=tmp_path / "fake-rsync",
                    extra_env=environment,
                )
                self.assertEqual(result.returncode, 0, msg=result.stderr)
                current_result = (
                    (remote_home / ".zshrc").read_bytes(),
                    (remote_home / ".zshrc.local").read_bytes(),
                )
                if attempt == 0:
                    first_result = current_result
                else:
                    self.assertEqual(current_result, first_result)

            remote_zshrc = (remote_home / ".zshrc").read_text(encoding="utf-8")
            self.assertIn("alias before", remote_zshrc)
            self.assertIn("alias after", remote_zshrc)
            self.assertEqual(remote_zshrc.count("# >>> sshx zshrc.local >>>"), 1)
            self.assertEqual(remote_zshrc.count("source \"$HOME/.zshrc.local\""), 1)
            self.assertTrue(
                remote_zshrc.rstrip().endswith("# <<< sshx zshrc.local <<<")
            )
            merged_overlay = (remote_home / ".zshrc.local").read_text(
                encoding="utf-8"
            )
            self.assertIn("typeset -g REMOTE_ONLY=1", merged_overlay)
            self.assertIn("# >>> sshx managed overlay >>>", merged_overlay)
            self.assertIn("alias dex='codex --profile gen'", merged_overlay)
            self.assertEqual(
                (remote_home / ".zshrc.sshx-base").read_text(encoding="utf-8"),
                base_zshrc,
            )
            self.assertEqual(
                (remote_home / ".zshrc.local.sshx-base").read_text(
                    encoding="utf-8"
                ),
                remote_local,
            )
            self.assertEqual(
                stat.S_IMODE((remote_home / ".zshrc.local").stat().st_mode),
                0o600,
            )
            self.assertEqual(
                stat.S_IMODE((remote_home / ".zshrc.sshx-base").stat().st_mode),
                0o600,
            )
            self.assertFalse((remote_home / ".zshrc.sshx-replaced").exists())

            shell_env = os.environ.copy()
            shell_env["HOME"] = str(remote_home)
            sourced = subprocess.run(
                [
                    "zsh",
                    "-fc",
                    'source "$HOME/.zshrc"; [[ "$SSHX_ZSHRC_LOCAL_LOADED" == 1 ]]',
                ],
                env=shell_env,
                check=False,
            )
            self.assertEqual(sourced.returncode, 0)

    def test_zsh_overlay_rejects_reversed_markers_and_symlinks(self) -> None:
        scenarios = ("reversed-markers", "symlink")
        for scenario in scenarios:
            with self.subTest(scenario=scenario), tempfile.TemporaryDirectory() as tmp:
                tmp_path = Path(tmp)
                home = tmp_path / "home"
                remote_home = tmp_path / "remote-home"
                home.mkdir()
                remote_home.mkdir()
                _write_file(remote_home / ".zshrc", "alias base='true'\n")
                config_path = tmp_path / "config.yaml"
                overlay_path = tmp_path / "zshrc.remote.local"
                _write_file(
                    config_path,
                    "profiles:\n  default:\n    - '@zsh-overlay'\n",
                )
                _write_file(
                    overlay_path,
                    "typeset -g SSHX_ZSHRC_LOCAL_LOADED=1\n",
                )

                if scenario == "reversed-markers":
                    original = (
                        "typeset -g REMOTE_ONLY=1\n"
                        "# <<< sshx managed overlay <<<\n"
                        "keep=this\n"
                        "# >>> sshx managed overlay >>>\n"
                    )
                    _write_file(remote_home / ".zshrc.local", original)
                else:
                    target = remote_home / "managed-elsewhere.zsh"
                    _write_file(target, "typeset -g REMOTE_ONLY=1\n")
                    (remote_home / ".zshrc.local").symlink_to(target.name)

                ssh_bin = tmp_path / "fake-ssh"
                _write_fake_ssh_remote(ssh_bin, remote_home=remote_home)
                result = self.run_cli(
                    ["--sync-method", "tar", "devbox", "true"],
                    home=home,
                    ssh_bin=ssh_bin,
                    rsync_bin=tmp_path / "fake-rsync",
                    extra_env={
                        "SSHX_CONFIG_PATH": str(config_path),
                        "SSHX_ZSH_OVERLAY_PATH": str(overlay_path),
                    },
                )

                self.assertNotEqual(result.returncode, 0)
                if scenario == "reversed-markers":
                    self.assertIn("malformed sshx managed block", result.stderr)
                    self.assertEqual(
                        (remote_home / ".zshrc.local").read_text(encoding="utf-8"),
                        original,
                    )
                else:
                    self.assertIn("refusing to replace a symlinked", result.stderr)
                    self.assertTrue((remote_home / ".zshrc.local").is_symlink())

    def test_rsync_failure_stops_before_ssh(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            home = tmp_path / "home"
            home.mkdir()
            _write_file(
                home / ".config" / "git" / "config",
                "[init]\ndefaultBranch = main\n",
            )

            rsync_log = tmp_path / "rsync.json"
            ssh_log = tmp_path / "ssh.json"
            rsync_bin = tmp_path / "fake-rsync"
            ssh_bin = tmp_path / "fake-ssh"
            _write_fake_exec(rsync_bin, log_path=rsync_log, exit_code=23)
            _write_fake_exec(ssh_bin, log_path=ssh_log)

            result = self.run_cli(
                ["--sync-method", "rsync", "devbox"],
                home=home,
                ssh_bin=ssh_bin,
                rsync_bin=rsync_bin,
            )

            self.assertEqual(result.returncode, 23)
            self.assertIn("rsync failed with exit code 23", result.stderr)
            self.assertTrue(rsync_log.exists())
            self.assertFalse(ssh_log.exists())

    def test_rsync_transport_error_retries_once_before_connecting(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            home = tmp_path / "home"
            home.mkdir()
            _write_file(
                home / ".config" / "git" / "config",
                "[init]\ndefaultBranch = main\n",
            )

            rsync_log = tmp_path / "rsync.json"
            rsync_state = tmp_path / "rsync-count.txt"
            ssh_log = tmp_path / "ssh.json"
            rsync_bin = tmp_path / "fake-rsync"
            ssh_bin = tmp_path / "fake-ssh"
            _write_retrying_fake_exec(
                rsync_bin,
                log_path=rsync_log,
                state_path=rsync_state,
                initial_exit_code=255,
            )
            _write_fake_ssh_append(ssh_bin, log_path=ssh_log)

            result = self.run_cli(
                ["--sync-method", "rsync", "devbox"],
                home=home,
                ssh_bin=ssh_bin,
                rsync_bin=rsync_bin,
            )

            self.assertEqual(result.returncode, 0, msg=result.stderr)
            self.assertIn("retrying once", result.stderr)
            self.assertEqual(rsync_state.read_text(encoding="utf-8"), "2")
            self.assertTrue(ssh_log.exists())

    def test_auto_falls_back_to_tar_when_remote_rsync_is_unavailable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            home = tmp_path / "home"
            home.mkdir()
            _write_file(
                home / ".config" / "git" / "config",
                "[init]\ndefaultBranch = main\n",
            )

            rsync_log = tmp_path / "rsync.json"
            tar_log = tmp_path / "tar.json"
            ssh_log = tmp_path / "ssh.json"
            rsync_bin = tmp_path / "fake-rsync"
            tar_bin = tmp_path / "fake-tar"
            ssh_bin = tmp_path / "fake-ssh"
            _write_fake_exec(rsync_bin, log_path=rsync_log, exit_code=127)
            _write_fake_tar(tar_bin, log_path=tar_log, payload=b"tar-data")
            _write_fake_ssh_append(
                ssh_bin,
                log_path=ssh_log,
                rsync_available=False,
            )

            result = self.run_cli(
                ["devbox"],
                home=home,
                ssh_bin=ssh_bin,
                rsync_bin=rsync_bin,
                tar_bin=tar_bin,
            )

            self.assertEqual(result.returncode, 0, msg=result.stderr)
            self.assertIn("falling back to tar-over-ssh sync", result.stderr)
            self.assertFalse(rsync_log.exists())

            tar_payload = _read_log(tar_log)
            self.assertEqual(Path(str(tar_payload["cwd"])).resolve(), home.resolve())
            self.assertEqual(
                tar_payload["argv"],
                _expected_tar_args(".config/git"),
            )

            ssh_calls = _read_calls(ssh_log)
            self.assertEqual(len(ssh_calls), 4)
            self.assertEqual(
                ssh_calls[0]["argv"],
                ["-n", "devbox", "command -v rsync >/dev/null 2>&1"],
            )
            self.assertEqual(
                ssh_calls[1]["argv"],
                ["devbox", 'mkdir -p "$HOME" && tar -xzf - -C "$HOME"'],
            )
            self.assertIn(".zshrc.local.sshx.", ssh_calls[2]["argv"][-1])
            self.assertEqual(
                ssh_calls[2]["stdin_len"],
                len((ROOT / "config" / "sshx" / "zshrc.remote.local").read_bytes()),
            )
            self.assertEqual(ssh_calls[3]["argv"], ["devbox"])

    def test_tar_sync_method_skips_rsync(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            home = tmp_path / "home"
            home.mkdir()
            _write_file(
                home / ".config" / "git" / "config",
                "[init]\ndefaultBranch = main\n",
            )

            rsync_log = tmp_path / "rsync.json"
            tar_log = tmp_path / "tar.json"
            ssh_log = tmp_path / "ssh.json"
            rsync_bin = tmp_path / "fake-rsync"
            tar_bin = tmp_path / "fake-tar"
            ssh_bin = tmp_path / "fake-ssh"
            _write_fake_exec(rsync_bin, log_path=rsync_log, exit_code=23)
            _write_fake_tar(tar_bin, log_path=tar_log)
            _write_fake_ssh_append(ssh_bin, log_path=ssh_log)

            result = self.run_cli(
                ["--sync-method", "tar", "devbox", "uname", "-a"],
                home=home,
                ssh_bin=ssh_bin,
                rsync_bin=rsync_bin,
                tar_bin=tar_bin,
            )

            self.assertEqual(result.returncode, 0, msg=result.stderr)
            self.assertFalse(rsync_log.exists())
            tar_payload = _read_log(tar_log)
            self.assertEqual(tar_payload["argv"], _expected_tar_args(".config/git"))
            ssh_calls = _read_calls(ssh_log)
            self.assertEqual(
                ssh_calls[-1]["argv"],
                ["devbox", "uname", "-a"],
            )

    def test_tar_sync_dereferences_symlinks_and_excludes_sockets(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            home = tmp_path / "home"
            home.mkdir()
            _write_file(home / ".config" / "tool" / "settings.json", "{}\n")
            socket_path = home / ".config" / "tool" / "runtime.sock"

            rsync_bin = tmp_path / "fake-rsync"
            tar_log = tmp_path / "tar.json"
            tar_bin = tmp_path / "fake-tar"
            ssh_log = tmp_path / "ssh.json"
            ssh_bin = tmp_path / "fake-ssh"
            _write_fake_exec(rsync_bin, log_path=tmp_path / "rsync.json")
            _write_fake_tar(tar_bin, log_path=tar_log)
            _write_fake_ssh_append(ssh_bin, log_path=ssh_log)

            with socket.socket(socket.AF_UNIX) as unix_socket:
                unix_socket.bind(str(socket_path))
                result = self.run_cli(
                    [
                        "--sync-method",
                        "tar",
                        "--no-defaults",
                        "--path",
                        ".config/tool",
                        "devbox",
                    ],
                    home=home,
                    ssh_bin=ssh_bin,
                    rsync_bin=rsync_bin,
                    tar_bin=tar_bin,
                )

            self.assertEqual(result.returncode, 0, msg=result.stderr)
            tar_payload = _read_log(tar_log)
            self.assertEqual(
                tar_payload["argv"],
                _expected_tar_args(
                    ".config/tool",
                    excludes=(".config/tool/runtime.sock",),
                ),
            )


if __name__ == "__main__":
    unittest.main()
