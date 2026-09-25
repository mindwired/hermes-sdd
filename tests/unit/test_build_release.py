from __future__ import annotations

import subprocess
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from scripts import build_release


class ReleaseBuildTest(unittest.TestCase):
    @staticmethod
    def _create_clean_repo(root: Path) -> None:
        root.mkdir(parents=True)
        (root / "scripts").mkdir()
        (root / "README.md").write_text("release source\n", encoding="utf-8")
        (root / "hermes_sdd").mkdir()
        (root / "hermes_sdd" / "version.py").write_text('__version__ = "1.2.3"\n', encoding="utf-8")
        (root / "scripts" / "verify.py").write_text(
            "# disposable verification stub\n", encoding="utf-8"
        )
        subprocess.run(["git", "init", "-q", str(root)], check=True)
        subprocess.run(["git", "-C", str(root), "add", "."], check=True)
        subprocess.run(
            [
                "git",
                "-C",
                str(root),
                "-c",
                "user.name=Test",
                "-c",
                "user.email=test@example.invalid",
                "commit",
                "-m",
                "initial",
                "-q",
            ],
            check=True,
        )

    def _run_main(self, root: Path, output: Path) -> None:
        real_run = subprocess.run

        def run(command, **kwargs):
            if len(command) > 1 and str(command[1]).endswith("scripts/verify.py"):
                return subprocess.CompletedProcess(command, 0)
            return real_run(command, **kwargs)

        with (
            patch.object(build_release, "ROOT", root),
            patch("sys.argv", ["build_release.py", "--version", "1.2.3", "--output", str(output)]),
            patch.object(build_release.subprocess, "run", side_effect=run),
        ):
            build_release.main()

    def test_release_file_list_excludes_untracked_workspace_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            subprocess.run(["git", "init", "-q", str(root)], check=True)
            tracked = root / "README.md"
            tracked.write_text("tracked source\n", encoding="utf-8")
            (root / "review-notes.md").write_text("local working note\n", encoding="utf-8")
            subprocess.run(["git", "-C", str(root), "add", "README.md"], check=True)
            subprocess.run(
                [
                    "git",
                    "-C",
                    str(root),
                    "-c",
                    "user.name=Test",
                    "-c",
                    "user.email=test@example.invalid",
                    "commit",
                    "-m",
                    "initial",
                    "-q",
                ],
                check=True,
            )

            with patch.object(build_release, "ROOT", root):
                selected = build_release.files()
                archive = root / "release.zip"
                build_release.add_zip(archive, "hermes-sdd-test")

            self.assertEqual(
                [path.relative_to(root).as_posix() for path in selected], ["README.md"]
            )
            with zipfile.ZipFile(archive) as bundle:
                self.assertEqual(bundle.namelist(), ["hermes-sdd-test/README.md"])

    def test_release_file_list_rejects_modified_tracked_files(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            subprocess.run(["git", "init", "-q", str(root)], check=True)
            tracked = root / "README.md"
            tracked.write_text("original content\n", encoding="utf-8")
            subprocess.run(["git", "-C", str(root), "add", "README.md"], check=True)
            subprocess.run(
                [
                    "git",
                    "-C",
                    str(root),
                    "-c",
                    "user.name=Test",
                    "-c",
                    "user.email=test@example.invalid",
                    "commit",
                    "-m",
                    "initial",
                    "-q",
                ],
                check=True,
            )
            tracked.write_text("modified content\n", encoding="utf-8")

            with patch.object(build_release, "ROOT", root):
                with self.assertRaisesRegex(RuntimeError, "tracked working tree changes"):
                    build_release.files()

    def test_release_file_list_rejects_staged_tracked_changes(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            subprocess.run(["git", "init", "-q", str(root)], check=True)
            tracked = root / "README.md"
            tracked.write_text("original content\n", encoding="utf-8")
            subprocess.run(["git", "-C", str(root), "add", "README.md"], check=True)
            subprocess.run(
                [
                    "git",
                    "-C",
                    str(root),
                    "-c",
                    "user.name=Test",
                    "-c",
                    "user.email=test@example.invalid",
                    "commit",
                    "-m",
                    "initial",
                    "-q",
                ],
                check=True,
            )
            tracked.write_text("staged changed content\n", encoding="utf-8")
            subprocess.run(["git", "-C", str(root), "add", "README.md"], check=True)

            with patch.object(build_release, "ROOT", root):
                with self.assertRaisesRegex(RuntimeError, "tracked working tree changes"):
                    build_release.files()

    def test_release_file_list_rejects_deletions_and_renames(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            subprocess.run(["git", "init", "-q", str(root)], check=True)
            (root / "README.md").write_text("tracked source\n", encoding="utf-8")
            (root / "notes.md").write_text("tracked notes\n", encoding="utf-8")
            subprocess.run(["git", "-C", str(root), "add", "."], check=True)
            subprocess.run(
                [
                    "git",
                    "-C",
                    str(root),
                    "-c",
                    "user.name=Test",
                    "-c",
                    "user.email=test@example.invalid",
                    "commit",
                    "-m",
                    "initial",
                    "-q",
                ],
                check=True,
            )
            (root / "README.md").unlink()
            (root / "notes.md").rename(root / "renamed.md")

            with patch.object(build_release, "ROOT", root):
                with self.assertRaisesRegex(RuntimeError, "tracked working tree changes"):
                    build_release.files()

    def test_release_file_list_rejects_tracked_symlinks(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            root = base / "repo"
            root.mkdir()
            outside = base / "outside.txt"
            outside.write_text("external content\n", encoding="utf-8")
            (root / "README.md").write_text("source\n", encoding="utf-8")
            (root / "external.txt").symlink_to(outside)
            subprocess.run(["git", "init", "-q", str(root)], check=True)
            subprocess.run(["git", "-C", str(root), "add", "README.md", "external.txt"], check=True)
            subprocess.run(
                [
                    "git",
                    "-C",
                    str(root),
                    "-c",
                    "user.name=Test",
                    "-c",
                    "user.email=test@example.invalid",
                    "commit",
                    "-m",
                    "initial",
                    "-q",
                ],
                check=True,
            )

            with patch.object(build_release, "ROOT", root):
                with self.assertRaisesRegex(RuntimeError, "symlinked files"):
                    build_release.files()

    def test_release_output_preserves_unrelated_existing_files(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "repo"
            self._create_clean_repo(root)
            output = Path(temp) / "release-output"
            output.mkdir()
            marker = output / "keep.txt"
            marker.write_text("owned by the caller\n", encoding="utf-8")

            self._run_main(root, output)

            self.assertEqual(marker.read_text(encoding="utf-8"), "owned by the caller\n")
            self.assertTrue((output / "hermes-sdd-1.2.3.zip").is_file())
            self.assertTrue((output / "hermes-sdd-1.2.3.tar.gz").is_file())

    def test_release_output_cannot_be_repository_root(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "repo"
            self._create_clean_repo(root)
            marker = root / "README.md"
            original = marker.read_text(encoding="utf-8")

            with self.assertRaisesRegex(RuntimeError, "repository root or its parent"):
                self._run_main(root, root)

            self.assertEqual(marker.read_text(encoding="utf-8"), original)

    def test_release_output_cannot_contain_the_repository(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "repo"
            self._create_clean_repo(root)
            marker = root / "README.md"
            original = marker.read_text(encoding="utf-8")

            with self.assertRaisesRegex(RuntimeError, "repository root or its parent"):
                self._run_main(root, root.parent)

            self.assertEqual(marker.read_text(encoding="utf-8"), original)

    def test_release_output_allows_managed_release_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "repo"
            self._create_clean_repo(root)
            output = root / "release"
            output.mkdir()
            marker = output / "keep.txt"
            marker.write_text("preserve unrelated content\n", encoding="utf-8")

            with self.assertRaisesRegex(RuntimeError, "unexpected files: keep.txt"):
                self._run_main(root, output)

            self.assertEqual(marker.read_text(encoding="utf-8"), "preserve unrelated content\n")
            self.assertFalse((output / "hermes-sdd-1.2.3.zip").exists())

    def test_release_builds_into_empty_managed_release_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "repo"
            self._create_clean_repo(root)

            self._run_main(root, root / "release")

            self.assertTrue((root / "release" / "hermes-sdd-1.2.3.zip").is_file())
            self.assertTrue((root / "release" / "hermes-sdd-1.2.3.tar.gz").is_file())

    def test_release_replaces_only_prior_managed_archives(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "repo"
            self._create_clean_repo(root)
            output = root / "release"
            output.mkdir()
            previous = output / "hermes-sdd-1.2.2.zip"
            previous.write_text("old archive", encoding="utf-8")
            previous_checksum = output / "hermes-sdd-1.2.2.zip.sha256"
            previous_checksum.write_text("old checksum", encoding="utf-8")
            unrelated = output / "keep.txt"
            unrelated.write_text("caller data", encoding="utf-8")

            with self.assertRaisesRegex(
                RuntimeError, "stale release artifacts: hermes-sdd-1.2.2.zip"
            ):
                self._run_main(root, output)

            self.assertTrue(previous.exists())
            self.assertEqual(previous_checksum.read_text(encoding="utf-8"), "old checksum")
            self.assertEqual(unrelated.read_text(encoding="utf-8"), "caller data")

    def test_release_output_rejects_symlinked_archive_target(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            root = base / "repo"
            self._create_clean_repo(root)
            output = root / "release"
            output.mkdir()
            outside = base / "outside.zip"
            outside.write_text("preserve external file", encoding="utf-8")
            (output / "hermes-sdd-1.2.3.zip").symlink_to(outside)

            with self.assertRaisesRegex(RuntimeError, "symlink"):
                self._run_main(root, output)

            self.assertEqual(outside.read_text(encoding="utf-8"), "preserve external file")

    def test_release_output_rejects_symlinked_checksum_target(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            root = base / "repo"
            self._create_clean_repo(root)
            output = root / "release"
            output.mkdir()
            outside = base / "outside.sha256"
            outside.write_text("preserve external checksum", encoding="utf-8")
            (output / "hermes-sdd-1.2.3.zip.sha256").symlink_to(outside)

            with self.assertRaisesRegex(RuntimeError, "symlinks: hermes-sdd-1.2.3.zip.sha256"):
                self._run_main(root, output)

            self.assertEqual(outside.read_text(encoding="utf-8"), "preserve external checksum")

    def test_release_output_rejects_stale_archives_from_other_versions(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "repo"
            self._create_clean_repo(root)
            output = root / "release"
            output.mkdir()
            stale = output / "hermes-sdd-1.2.2.zip"
            stale.write_text("stale archive", encoding="utf-8")

            with self.assertRaisesRegex(RuntimeError, "stale release artifacts"):
                self._run_main(root, output)

            self.assertEqual(stale.read_text(encoding="utf-8"), "stale archive")

    def test_release_output_ignores_unrelated_file_with_release_suffixes(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "repo"
            self._create_clean_repo(root)
            output = root / "release"
            output.mkdir()
            unrelated = output / "customer-export.zip"
            unrelated.write_text("caller data", encoding="utf-8")

            with self.assertRaisesRegex(RuntimeError, "unexpected files: customer-export.zip"):
                self._run_main(root, output)

            self.assertEqual(unrelated.read_text(encoding="utf-8"), "caller data")

    def test_release_output_rejects_other_repository_subdirectories(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "repo"
            self._create_clean_repo(root)
            output = root / "important"

            with self.assertRaisesRegex(RuntimeError, "inside the repository"):
                self._run_main(root, output)

            self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
