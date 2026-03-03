from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "bin" / "arbor"


class ArborCliTest(unittest.TestCase):
    def run_cli(self, repo: Path, args: list[str]) -> subprocess.CompletedProcess[str]:
        env = os.environ.copy()
        return subprocess.run(
            [sys.executable, str(CLI), *args],
            cwd=repo,
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )

    def run_git(self, repo: Path, args: list[str]) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["git", *args],
            cwd=repo,
            capture_output=True,
            text=True,
            check=False,
        )

    def setup_repo(self, root: Path) -> Path:
        repo = root / "repo"
        repo.mkdir(parents=True, exist_ok=True)
        init = self.run_git(repo, ["init", "--initial-branch", "main"])
        self.assertEqual(init.returncode, 0, msg=init.stderr)

        email = self.run_git(repo, ["config", "user.email", "test@example.com"])
        self.assertEqual(email.returncode, 0, msg=email.stderr)
        name = self.run_git(repo, ["config", "user.name", "Test User"])
        self.assertEqual(name.returncode, 0, msg=name.stderr)

        file_path = repo / "README.md"
        file_path.write_text("initial\n", encoding="utf-8")
        add = self.run_git(repo, ["add", "README.md"])
        self.assertEqual(add.returncode, 0, msg=add.stderr)
        commit = self.run_git(repo, ["commit", "-m", "initial commit"])
        self.assertEqual(commit.returncode, 0, msg=commit.stderr)
        return repo

    def test_clean_removes_merged_worktree_and_branch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            repo = self.setup_repo(tmp_path)
            worktree_dir = tmp_path / "wt-feature-merged"

            checkout = self.run_git(repo, ["checkout", "-b", "feature/merged"])
            self.assertEqual(checkout.returncode, 0, msg=checkout.stderr)
            (repo / "feature.txt").write_text("feature work\n", encoding="utf-8")
            add = self.run_git(repo, ["add", "feature.txt"])
            self.assertEqual(add.returncode, 0, msg=add.stderr)
            commit = self.run_git(repo, ["commit", "-m", "add feature work"])
            self.assertEqual(commit.returncode, 0, msg=commit.stderr)

            back_to_main = self.run_git(repo, ["checkout", "main"])
            self.assertEqual(back_to_main.returncode, 0, msg=back_to_main.stderr)
            merge = self.run_git(
                repo, ["merge", "--no-ff", "-m", "merge feature", "feature/merged"]
            )
            self.assertEqual(merge.returncode, 0, msg=merge.stderr)

            add_worktree = self.run_git(
                repo, ["worktree", "add", str(worktree_dir), "feature/merged"]
            )
            self.assertEqual(add_worktree.returncode, 0, msg=add_worktree.stderr)

            result = self.run_cli(repo, ["clean", "--base", "main"])
            self.assertEqual(result.returncode, 0, msg=result.stderr)
            self.assertIn("deleted branch: feature/merged", result.stdout)
            self.assertIn("removed worktree:", result.stdout)

            branch_exists = self.run_git(repo, ["branch", "--list", "feature/merged"])
            self.assertEqual(branch_exists.returncode, 0, msg=branch_exists.stderr)
            self.assertEqual(branch_exists.stdout.strip(), "")
            self.assertFalse(worktree_dir.exists())

    def test_clean_keeps_unmerged_worktree_and_branch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            repo = self.setup_repo(tmp_path)
            worktree_dir = tmp_path / "wt-feature-open"

            checkout = self.run_git(repo, ["checkout", "-b", "feature/open"])
            self.assertEqual(checkout.returncode, 0, msg=checkout.stderr)
            (repo / "open.txt").write_text("open work\n", encoding="utf-8")
            add = self.run_git(repo, ["add", "open.txt"])
            self.assertEqual(add.returncode, 0, msg=add.stderr)
            commit = self.run_git(repo, ["commit", "-m", "open feature work"])
            self.assertEqual(commit.returncode, 0, msg=commit.stderr)

            back_to_main = self.run_git(repo, ["checkout", "main"])
            self.assertEqual(back_to_main.returncode, 0, msg=back_to_main.stderr)
            add_worktree = self.run_git(
                repo, ["worktree", "add", str(worktree_dir), "feature/open"]
            )
            self.assertEqual(add_worktree.returncode, 0, msg=add_worktree.stderr)

            result = self.run_cli(repo, ["clean", "--base", "main"])
            self.assertEqual(result.returncode, 0, msg=result.stderr)
            self.assertNotIn("deleted branch: feature/open", result.stdout)

            branch_exists = self.run_git(repo, ["branch", "--list", "feature/open"])
            self.assertEqual(branch_exists.returncode, 0, msg=branch_exists.stderr)
            self.assertIn("feature/open", branch_exists.stdout)
            self.assertTrue(worktree_dir.exists())

    def test_clean_dry_run_previews_without_changes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            repo = self.setup_repo(tmp_path)
            worktree_dir = tmp_path / "wt-feature-preview"

            checkout = self.run_git(repo, ["checkout", "-b", "feature/preview"])
            self.assertEqual(checkout.returncode, 0, msg=checkout.stderr)
            (repo / "preview.txt").write_text("preview work\n", encoding="utf-8")
            add = self.run_git(repo, ["add", "preview.txt"])
            self.assertEqual(add.returncode, 0, msg=add.stderr)
            commit = self.run_git(repo, ["commit", "-m", "add preview work"])
            self.assertEqual(commit.returncode, 0, msg=commit.stderr)

            back_to_main = self.run_git(repo, ["checkout", "main"])
            self.assertEqual(back_to_main.returncode, 0, msg=back_to_main.stderr)
            merge = self.run_git(
                repo, ["merge", "--no-ff", "-m", "merge preview", "feature/preview"]
            )
            self.assertEqual(merge.returncode, 0, msg=merge.stderr)
            add_worktree = self.run_git(
                repo, ["worktree", "add", str(worktree_dir), "feature/preview"]
            )
            self.assertEqual(add_worktree.returncode, 0, msg=add_worktree.stderr)

            result = self.run_cli(repo, ["clean", "--base", "main", "--dry-run"])
            self.assertEqual(result.returncode, 0, msg=result.stderr)
            self.assertIn("would remove worktree:", result.stdout)
            self.assertIn("would delete branch: feature/preview", result.stdout)
            self.assertIn("dry-run mode: no changes made", result.stdout)

            branch_exists = self.run_git(repo, ["branch", "--list", "feature/preview"])
            self.assertEqual(branch_exists.returncode, 0, msg=branch_exists.stderr)
            self.assertIn("feature/preview", branch_exists.stdout)
            self.assertTrue(worktree_dir.exists())

    def test_clean_force_removes_dirty_merged_worktree(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            repo = self.setup_repo(tmp_path)
            worktree_dir = tmp_path / "wt-feature-dirty"

            checkout = self.run_git(repo, ["checkout", "-b", "feature/dirty"])
            self.assertEqual(checkout.returncode, 0, msg=checkout.stderr)
            (repo / "dirty.txt").write_text("dirty base\n", encoding="utf-8")
            add = self.run_git(repo, ["add", "dirty.txt"])
            self.assertEqual(add.returncode, 0, msg=add.stderr)
            commit = self.run_git(repo, ["commit", "-m", "add dirty feature"])
            self.assertEqual(commit.returncode, 0, msg=commit.stderr)

            back_to_main = self.run_git(repo, ["checkout", "main"])
            self.assertEqual(back_to_main.returncode, 0, msg=back_to_main.stderr)
            merge = self.run_git(
                repo, ["merge", "--no-ff", "-m", "merge dirty feature", "feature/dirty"]
            )
            self.assertEqual(merge.returncode, 0, msg=merge.stderr)
            add_worktree = self.run_git(
                repo, ["worktree", "add", str(worktree_dir), "feature/dirty"]
            )
            self.assertEqual(add_worktree.returncode, 0, msg=add_worktree.stderr)

            (worktree_dir / "dirty.txt").write_text(
                "modified in worktree\n", encoding="utf-8"
            )

            non_force = self.run_cli(repo, ["clean", "--base", "main"])
            self.assertEqual(non_force.returncode, 1, msg=non_force.stderr)
            self.assertTrue(worktree_dir.exists())
            self.assertIn("contains modified or untracked files", non_force.stderr)

            force = self.run_cli(repo, ["clean", "--base", "main", "--force"])
            self.assertEqual(force.returncode, 0, msg=force.stderr)
            self.assertIn("force removed worktree:", force.stdout)
            self.assertIn("deleted branch: feature/dirty", force.stdout)
            self.assertFalse(worktree_dir.exists())

            branch_exists = self.run_git(repo, ["branch", "--list", "feature/dirty"])
            self.assertEqual(branch_exists.returncode, 0, msg=branch_exists.stderr)
            self.assertEqual(branch_exists.stdout.strip(), "")

    def test_delete_branch_removes_linked_worktree_and_branch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            repo = self.setup_repo(tmp_path)
            worktree_dir = tmp_path / "wt-feature-delete-branch"

            checkout = self.run_git(repo, ["checkout", "-b", "feature/delete-branch"])
            self.assertEqual(checkout.returncode, 0, msg=checkout.stderr)
            (repo / "delete_branch.txt").write_text("delete branch\n", encoding="utf-8")
            add = self.run_git(repo, ["add", "delete_branch.txt"])
            self.assertEqual(add.returncode, 0, msg=add.stderr)
            commit = self.run_git(repo, ["commit", "-m", "add delete branch"])
            self.assertEqual(commit.returncode, 0, msg=commit.stderr)

            back_to_main = self.run_git(repo, ["checkout", "main"])
            self.assertEqual(back_to_main.returncode, 0, msg=back_to_main.stderr)
            add_worktree = self.run_git(
                repo,
                ["worktree", "add", str(worktree_dir), "feature/delete-branch"],
            )
            self.assertEqual(add_worktree.returncode, 0, msg=add_worktree.stderr)

            result = self.run_cli(repo, ["delete", "feature/delete-branch"])
            self.assertEqual(result.returncode, 0, msg=result.stderr)
            self.assertIn("removed worktree:", result.stdout)
            self.assertIn("deleted branch: feature/delete-branch", result.stdout)
            self.assertFalse(worktree_dir.exists())

            branch_exists = self.run_git(
                repo, ["branch", "--list", "feature/delete-branch"]
            )
            self.assertEqual(branch_exists.returncode, 0, msg=branch_exists.stderr)
            self.assertEqual(branch_exists.stdout.strip(), "")

    def test_delete_worktree_by_name_keeps_branch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            repo = self.setup_repo(tmp_path)
            worktree_dir = tmp_path / "wt-branch-delete-worktree"

            checkout = self.run_git(repo, ["checkout", "-b", "feature/delete-worktree"])
            self.assertEqual(checkout.returncode, 0, msg=checkout.stderr)
            (repo / "delete_worktree.txt").write_text(
                "delete worktree\n", encoding="utf-8"
            )
            add = self.run_git(repo, ["add", "delete_worktree.txt"])
            self.assertEqual(add.returncode, 0, msg=add.stderr)
            commit = self.run_git(repo, ["commit", "-m", "add delete worktree"])
            self.assertEqual(commit.returncode, 0, msg=commit.stderr)

            back_to_main = self.run_git(repo, ["checkout", "main"])
            self.assertEqual(back_to_main.returncode, 0, msg=back_to_main.stderr)
            add_worktree = self.run_git(
                repo,
                ["worktree", "add", str(worktree_dir), "feature/delete-worktree"],
            )
            self.assertEqual(add_worktree.returncode, 0, msg=add_worktree.stderr)

            result = self.run_cli(repo, ["delete", worktree_dir.name])
            self.assertEqual(result.returncode, 0, msg=result.stderr)
            self.assertIn(f"removed worktree: {worktree_dir.resolve()}", result.stdout)
            self.assertNotIn("deleted branch:", result.stdout)
            self.assertFalse(worktree_dir.exists())

            branch_exists = self.run_git(
                repo, ["branch", "--list", "feature/delete-worktree"]
            )
            self.assertEqual(branch_exists.returncode, 0, msg=branch_exists.stderr)
            self.assertIn("feature/delete-worktree", branch_exists.stdout)

    def test_delete_branch_force_removes_dirty_linked_worktree(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            repo = self.setup_repo(tmp_path)
            worktree_dir = tmp_path / "wt-feature-delete-dirty"

            checkout = self.run_git(repo, ["checkout", "-b", "feature/delete-dirty"])
            self.assertEqual(checkout.returncode, 0, msg=checkout.stderr)
            (repo / "delete_dirty.txt").write_text("delete dirty\n", encoding="utf-8")
            add = self.run_git(repo, ["add", "delete_dirty.txt"])
            self.assertEqual(add.returncode, 0, msg=add.stderr)
            commit = self.run_git(repo, ["commit", "-m", "add delete dirty"])
            self.assertEqual(commit.returncode, 0, msg=commit.stderr)

            back_to_main = self.run_git(repo, ["checkout", "main"])
            self.assertEqual(back_to_main.returncode, 0, msg=back_to_main.stderr)
            add_worktree = self.run_git(
                repo, ["worktree", "add", str(worktree_dir), "feature/delete-dirty"]
            )
            self.assertEqual(add_worktree.returncode, 0, msg=add_worktree.stderr)

            (worktree_dir / "delete_dirty.txt").write_text(
                "dirty worktree\n", encoding="utf-8"
            )

            non_force = self.run_cli(repo, ["delete", "feature/delete-dirty"])
            self.assertEqual(non_force.returncode, 1, msg=non_force.stderr)
            self.assertTrue(worktree_dir.exists())
            self.assertIn("contains modified or untracked files", non_force.stderr)

            force = self.run_cli(repo, ["delete", "feature/delete-dirty", "--force"])
            self.assertEqual(force.returncode, 0, msg=force.stderr)
            self.assertIn("force removed worktree:", force.stdout)
            self.assertIn("deleted branch: feature/delete-dirty", force.stdout)
            self.assertFalse(worktree_dir.exists())

            branch_exists = self.run_git(
                repo, ["branch", "--list", "feature/delete-dirty"]
            )
            self.assertEqual(branch_exists.returncode, 0, msg=branch_exists.stderr)
            self.assertEqual(branch_exists.stdout.strip(), "")

    def test_checkout_worktree_moves_branch_back_to_main_repo(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            repo = self.setup_repo(tmp_path)
            worktree_dir = tmp_path / "wt-feature-checkout"

            checkout = self.run_git(repo, ["checkout", "-b", "feature/checkout"])
            self.assertEqual(checkout.returncode, 0, msg=checkout.stderr)
            (repo / "checkout.txt").write_text("checkout branch\n", encoding="utf-8")
            add = self.run_git(repo, ["add", "checkout.txt"])
            self.assertEqual(add.returncode, 0, msg=add.stderr)
            commit = self.run_git(repo, ["commit", "-m", "add checkout branch"])
            self.assertEqual(commit.returncode, 0, msg=commit.stderr)

            back_to_main = self.run_git(repo, ["checkout", "main"])
            self.assertEqual(back_to_main.returncode, 0, msg=back_to_main.stderr)
            add_worktree = self.run_git(
                repo, ["worktree", "add", str(worktree_dir), "feature/checkout"]
            )
            self.assertEqual(add_worktree.returncode, 0, msg=add_worktree.stderr)

            result = self.run_cli(repo, ["checkout", str(worktree_dir)])
            self.assertEqual(result.returncode, 0, msg=result.stderr)
            self.assertIn(f"main checkout: {repo.resolve()}", result.stdout)
            self.assertIn("branch: feature/checkout", result.stdout)
            self.assertIn("worktree removed: yes", result.stdout)
            self.assertFalse(worktree_dir.exists())

            current_branch = self.run_git(repo, ["branch", "--show-current"])
            self.assertEqual(current_branch.returncode, 0, msg=current_branch.stderr)
            self.assertEqual(current_branch.stdout.strip(), "feature/checkout")

            worktree_list = self.run_git(repo, ["worktree", "list", "--porcelain"])
            self.assertEqual(worktree_list.returncode, 0, msg=worktree_list.stderr)
            self.assertNotIn(str(worktree_dir.resolve()), worktree_list.stdout)

    def test_checkout_without_target_uses_current_worktree(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            repo = self.setup_repo(tmp_path)
            worktree_dir = tmp_path / "wt-feature-current"

            checkout = self.run_git(
                repo, ["checkout", "-b", "feature/current-worktree"]
            )
            self.assertEqual(checkout.returncode, 0, msg=checkout.stderr)
            (repo / "current.txt").write_text("current worktree\n", encoding="utf-8")
            add = self.run_git(repo, ["add", "current.txt"])
            self.assertEqual(add.returncode, 0, msg=add.stderr)
            commit = self.run_git(repo, ["commit", "-m", "add current worktree"])
            self.assertEqual(commit.returncode, 0, msg=commit.stderr)

            back_to_main = self.run_git(repo, ["checkout", "main"])
            self.assertEqual(back_to_main.returncode, 0, msg=back_to_main.stderr)
            add_worktree = self.run_git(
                repo, ["worktree", "add", str(worktree_dir), "feature/current-worktree"]
            )
            self.assertEqual(add_worktree.returncode, 0, msg=add_worktree.stderr)

            result = self.run_cli(worktree_dir, ["checkout"])
            self.assertEqual(result.returncode, 0, msg=result.stderr)
            self.assertIn("branch: feature/current-worktree", result.stdout)
            self.assertFalse(worktree_dir.exists())

            current_branch = self.run_git(repo, ["branch", "--show-current"])
            self.assertEqual(current_branch.returncode, 0, msg=current_branch.stderr)
            self.assertEqual(current_branch.stdout.strip(), "feature/current-worktree")

    def test_checkout_refuses_dirty_worktree_or_main_repo(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            repo = self.setup_repo(tmp_path)
            worktree_dir = tmp_path / "wt-feature-dirty-checkout"

            checkout = self.run_git(repo, ["checkout", "-b", "feature/dirty-checkout"])
            self.assertEqual(checkout.returncode, 0, msg=checkout.stderr)
            (repo / "dirty_checkout.txt").write_text(
                "dirty checkout\n", encoding="utf-8"
            )
            add = self.run_git(repo, ["add", "dirty_checkout.txt"])
            self.assertEqual(add.returncode, 0, msg=add.stderr)
            commit = self.run_git(repo, ["commit", "-m", "add dirty checkout"])
            self.assertEqual(commit.returncode, 0, msg=commit.stderr)

            back_to_main = self.run_git(repo, ["checkout", "main"])
            self.assertEqual(back_to_main.returncode, 0, msg=back_to_main.stderr)
            add_worktree = self.run_git(
                repo, ["worktree", "add", str(worktree_dir), "feature/dirty-checkout"]
            )
            self.assertEqual(add_worktree.returncode, 0, msg=add_worktree.stderr)

            (worktree_dir / "dirty_checkout.txt").write_text(
                "dirty worktree\n", encoding="utf-8"
            )
            dirty_worktree = self.run_cli(repo, ["checkout", str(worktree_dir)])
            self.assertEqual(dirty_worktree.returncode, 1, msg=dirty_worktree.stderr)
            self.assertIn(
                "worktree checkout has uncommitted changes", dirty_worktree.stderr
            )
            self.assertTrue(worktree_dir.exists())

            self.run_git(worktree_dir, ["checkout", "--", "dirty_checkout.txt"])
            (repo / "README.md").write_text("main dirty\n", encoding="utf-8")
            dirty_main = self.run_cli(repo, ["checkout", str(worktree_dir)])
            self.assertEqual(dirty_main.returncode, 1, msg=dirty_main.stderr)
            self.assertIn(
                "main repo checkout has uncommitted changes", dirty_main.stderr
            )
            self.assertTrue(worktree_dir.exists())

            current_branch = self.run_git(repo, ["branch", "--show-current"])
            self.assertEqual(current_branch.returncode, 0, msg=current_branch.stderr)
            self.assertEqual(current_branch.stdout.strip(), "main")


if __name__ == "__main__":
    unittest.main()
