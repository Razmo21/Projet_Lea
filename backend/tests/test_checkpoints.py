from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock
from uuid import uuid4


BACKEND_DIRECTORY = Path(__file__).resolve().parents[1]
if str(BACKEND_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIRECTORY))

from app.checkpoints import CheckpointConflictError, CheckpointService  # noqa: E402
from app.database import CheckpointStateError, Database  # noqa: E402
from app.workspace import FrozenProject, WorkspaceGuard  # noqa: E402


class CheckpointServiceTests(unittest.TestCase):
    """Exercise a complete local snapshot/restore cycle without Docker or an LLM."""

    def setUp(self) -> None:
        """Create an isolated project and SQLite database for each rollback scenario."""

        self.temporary_directory = tempfile.TemporaryDirectory(
            prefix="lea-checkpoint-test-", dir=Path(__file__).resolve().parent
        )
        self.base = Path(self.temporary_directory.name)
        self.workspace_root = self.base / "IA_WORKSPACE"
        self.project_path = self.workspace_root / "Example"
        (self.project_path / "package").mkdir(parents=True)
        (self.project_path / "keep.txt").write_text("before keep\n", encoding="utf-8")
        (self.project_path / "remove.txt").write_text("before remove\n", encoding="utf-8")
        (self.project_path / "package" / "nested.txt").write_text("before nested\n", encoding="utf-8")
        self.database = Database(self.base / "lea.sqlite3")
        self.database.initialize()
        projects = self.database.sync_projects([("Example", "Example")])
        self.project = projects[0]
        self.guard = WorkspaceGuard(self.workspace_root)
        self.service = CheckpointService(self.database, self.guard, self.base / "checkpoints")

    def tearDown(self) -> None:
        """Close the isolated temporary tree after all checkpoint files have been inspected."""

        self.temporary_directory.cleanup()

    def make_checkpoint(self) -> tuple[str, FrozenProject]:
        """Create a pending run and its snapshot on the frozen test project."""

        run_id = str(uuid4())
        frozen = self.guard.freeze_project(self.project["id"], self.project["relative_path"])
        self.database.create_agent_run(run_id, frozen.project_id, "development", "Répare le projet")
        checkpoint = self.service.create(run_id, frozen)
        return str(checkpoint["checkpoint_id"]), frozen

    def create_python_generated_artifacts(self, marker: str) -> list[Path]:
        """Create every cache form excluded from a checkpoint without touching source files."""

        cache_directory = self.project_path / "package" / "__pycache__"
        cache_directory.mkdir(exist_ok=True)
        compiled = cache_directory / "nested.cpython-313.pyc"
        optimized = self.project_path / "legacy.pyo"
        loose_compiled = self.project_path / "legacy.pyc"
        pytest_cache = self.project_path / ".pytest_cache" / "v" / "cache"
        pytest_cache.mkdir(parents=True, exist_ok=True)
        node_ids = pytest_cache / "nodeids"
        compiled.write_bytes(f"compiled-{marker}".encode("ascii"))
        optimized.write_bytes(f"optimized-{marker}".encode("ascii"))
        loose_compiled.write_bytes(f"loose-{marker}".encode("ascii"))
        node_ids.write_text(f"cache-{marker}\n", encoding="utf-8")
        return [
            cache_directory,
            compiled,
            optimized,
            loose_compiled,
            pytest_cache.parents[1],
            pytest_cache.parents[0],
            pytest_cache,
            node_ids,
        ]

    def complete_with_legacy_artifact_rows(
        self,
        checkpoint_id: str,
        frozen: FrozenProject,
        artifacts: list[Path],
    ) -> None:
        """Persist an old-style artifact-rich after snapshot to verify compatibility without migrations."""

        after_entries = [self.service._entry_state(entry) for entry in self.service._inventory(frozen)]
        for artifact in artifacts:
            metadata = artifact.stat()
            relative_path = artifact.relative_to(self.project_path).as_posix()
            if artifact.is_dir():
                after_entries.append(
                    {
                        "relative_path": relative_path,
                        "entry_type": "directory",
                        "sha256": None,
                        "size": None,
                        "modified_ns": int(metadata.st_mtime_ns),
                    }
                )
            else:
                digest, size = self.service._hash_file(artifact)
                after_entries.append(
                    {
                        "relative_path": relative_path,
                        "entry_type": "file",
                        "sha256": digest,
                        "size": size,
                        "modified_ns": int(metadata.st_mtime_ns),
                    }
                )
        self.database.complete_project_checkpoint(checkpoint_id, after_entries)

    def test_complete_changes_and_rollback_restore_modified_deleted_and_created_files(self) -> None:
        """Rollback restores old contents, deleted files, and removes files created by a run."""

        checkpoint_id, frozen = self.make_checkpoint()
        (self.project_path / "keep.txt").write_text("after keep\n", encoding="utf-8")
        (self.project_path / "remove.txt").unlink()
        (self.project_path / "created.txt").write_text("created\n", encoding="utf-8")
        self.service.complete(checkpoint_id, frozen)

        changes = {item["relative_path"]: item["change"] for item in self.service.changes(checkpoint_id)}
        self.assertEqual(changes["keep.txt"], "modified")
        self.assertEqual(changes["remove.txt"], "deleted")
        self.assertEqual(changes["created.txt"], "created")

        restored = self.service.rollback(checkpoint_id, frozen)
        self.assertEqual(restored["state"], "rolled_back")
        self.assertEqual((self.project_path / "keep.txt").read_text(encoding="utf-8"), "before keep\n")
        self.assertEqual((self.project_path / "remove.txt").read_text(encoding="utf-8"), "before remove\n")
        self.assertFalse((self.project_path / "created.txt").exists())

    def test_python_generated_artifacts_are_excluded_from_new_snapshot_diff_and_rollback(self) -> None:
        """Caches never pollute a new diff or block a source rollback after a manual test reruns."""

        checkpoint_id, frozen = self.make_checkpoint()
        target = self.project_path / "keep.txt"
        target.write_text("agent change\n", encoding="utf-8")
        self.create_python_generated_artifacts("run")
        self.service.complete(checkpoint_id, frozen)

        changes = {item["relative_path"]: item["change"] for item in self.service.changes(checkpoint_id)}
        self.assertEqual(changes, {"keep.txt": "modified"})
        stored_rows = self.database.list_checkpoint_files(checkpoint_id)
        self.assertFalse(any(self.service._is_generated_artifact_row(row) for row in stored_rows))

        # A manual test can recreate bytecode after the run.  Force the parent
        # directory timestamp to the same kind of volatile value Windows reports
        # when that cache changes, then verify it does not mask source safety.
        parent = self.project_path / "package"
        before_mtime = int(parent.stat().st_mtime_ns)
        (parent / "__pycache__" / "manual.cpython-313.pyc").write_bytes(b"manual cache")
        os.utime(parent, ns=(before_mtime + 2_000_000_000, before_mtime + 2_000_000_000))
        self.assertNotEqual(int(parent.stat().st_mtime_ns), before_mtime)

        restored = self.service.rollback(checkpoint_id, frozen)
        self.assertEqual(restored["state"], "rolled_back")
        self.assertEqual(target.read_text(encoding="utf-8"), "before keep\n")
        self.assertTrue((parent / "__pycache__" / "manual.cpython-313.pyc").is_file())

    def test_legacy_python_artifact_rows_are_hidden_and_do_not_block_rollback(self) -> None:
        """Compatibility filtering leaves historical rows intact while safely restoring real source files."""

        checkpoint_id, frozen = self.make_checkpoint()
        target = self.project_path / "keep.txt"
        target.write_text("agent change\n", encoding="utf-8")
        artifacts = self.create_python_generated_artifacts("legacy-run")
        self.complete_with_legacy_artifact_rows(checkpoint_id, frozen, artifacts)

        changes = {item["relative_path"]: item["change"] for item in self.service.changes(checkpoint_id)}
        self.assertEqual(changes, {"keep.txt": "modified"})
        self.assertTrue(
            any(
                self.service._is_generated_artifact_row(row)
                for row in self.database.list_checkpoint_files(checkpoint_id)
            )
        )

        (self.project_path / "package" / "__pycache__" / "manual.cpython-313.pyc").write_bytes(
            b"manual cache"
        )
        restored = self.service.rollback(checkpoint_id, frozen)
        self.assertEqual(restored["state"], "rolled_back")
        self.assertEqual(target.read_text(encoding="utf-8"), "before keep\n")

    def test_external_change_becomes_a_conflict_and_is_never_overwritten(self) -> None:
        """A genuine post-run source edit still blocks rollback despite generated cache activity."""

        checkpoint_id, frozen = self.make_checkpoint()
        target = self.project_path / "keep.txt"
        target.write_text("agent change\n", encoding="utf-8")
        self.create_python_generated_artifacts("run")
        self.service.complete(checkpoint_id, frozen)
        (self.project_path / "package" / "__pycache__" / "manual.cpython-313.pyc").write_bytes(
            b"manual cache"
        )
        target.write_text("external change\n", encoding="utf-8")

        with self.assertRaises(CheckpointConflictError):
            self.service.rollback(checkpoint_id, frozen)
        self.assertEqual(target.read_text(encoding="utf-8"), "external change\n")
        self.assertEqual(self.database.get_project_checkpoint(checkpoint_id)["state"], "conflict")

    def test_checkpoint_acceptance_is_persisted_and_blocks_later_rollback(self) -> None:
        """Accepting a completed diff retains its audit record but makes it immutable."""

        checkpoint_id, frozen = self.make_checkpoint()
        target = self.project_path / "keep.txt"
        target.write_text("agent change\n", encoding="utf-8")
        self.service.complete(checkpoint_id, frozen)

        accepted = self.service.accept(checkpoint_id)
        self.assertEqual(accepted["state"], "accepted")
        self.assertEqual(self.service.changes(checkpoint_id)[0]["relative_path"], "keep.txt")
        with self.assertRaises(CheckpointStateError):
            self.service.rollback(checkpoint_id, frozen)
        self.assertEqual(target.read_text(encoding="utf-8"), "agent change\n")

    def test_changes_are_unavailable_until_the_after_snapshot_is_complete(self) -> None:
        """A ready checkpoint never exposes missing after-state as a fabricated deletion diff."""

        checkpoint_id, _frozen = self.make_checkpoint()

        with self.assertRaises(CheckpointStateError):
            self.service.changes(checkpoint_id)

    def test_replaced_project_directory_becomes_a_conflict_before_rollback(self) -> None:
        """The persisted filesystem identity rejects a same-name project replacement."""

        checkpoint_id, frozen = self.make_checkpoint()
        (self.project_path / "keep.txt").write_text("agent change\n", encoding="utf-8")
        self.service.complete(checkpoint_id, frozen)
        archived = self.workspace_root / "Example-original"
        self.project_path.rename(archived)
        self.project_path.mkdir()
        replacement = self.project_path / "keep.txt"
        replacement.write_text("replacement content\n", encoding="utf-8")

        with self.assertRaises(CheckpointConflictError):
            self.service.rollback(checkpoint_id, frozen)
        self.assertEqual(replacement.read_text(encoding="utf-8"), "replacement content\n")
        self.assertEqual(self.database.get_project_checkpoint(checkpoint_id)["state"], "conflict")

    def test_late_external_edit_is_checked_again_before_rollback_overwrites_a_file(self) -> None:
        """A write after the global check is refused before the file replacement itself occurs."""

        checkpoint_id, frozen = self.make_checkpoint()
        target = self.project_path / "keep.txt"
        target.write_text("agent change\n", encoding="utf-8")
        self.service.complete(checkpoint_id, frozen)
        original_check = self.service._assert_after_unchanged

        def inject_external_write(*arguments: object) -> list[dict[str, object]]:
            """Simulate a user edit in the small interval after the first full inventory."""

            rows = original_check(*arguments)  # type: ignore[arg-type]
            target.write_text("external race\n", encoding="utf-8")
            return rows

        with mock.patch.object(self.service, "_assert_after_unchanged", side_effect=inject_external_write):
            with self.assertRaises(CheckpointConflictError):
                self.service.rollback(checkpoint_id, frozen)

        self.assertEqual(target.read_text(encoding="utf-8"), "external race\n")
        self.assertEqual(self.database.get_project_checkpoint(checkpoint_id)["state"], "conflict")

    def test_empty_project_can_still_receive_a_checkpoint_and_remove_created_files(self) -> None:
        """An initially empty project remains restorable after a run creates its first file."""

        for path in sorted(self.project_path.rglob("*"), key=lambda item: len(item.parts), reverse=True):
            if path.is_file():
                path.unlink()
            elif path.is_dir():
                path.rmdir()
        checkpoint_id, frozen = self.make_checkpoint()
        (self.project_path / "first.txt").write_text("new\n", encoding="utf-8")
        self.service.complete(checkpoint_id, frozen)
        self.service.rollback(checkpoint_id, frozen)
        self.assertEqual(list(self.project_path.iterdir()), [])

    def test_transient_empty_git_mountpoint_is_removed_only_after_it_is_fingerprinted(self) -> None:
        """A Docker-created empty nested mountpoint never appears as an agent project change."""

        checkpoint_id, frozen = self.make_checkpoint()
        mountpoint = self.project_path / ".git"
        mountpoint.mkdir()

        fingerprint = self.service.capture_empty_internal_git_mountpoint(checkpoint_id, frozen)

        self.assertIsNotNone(fingerprint)
        self.assertTrue(
            self.service.discard_empty_internal_git_mountpoint(checkpoint_id, frozen, fingerprint)
        )
        self.assertFalse(mountpoint.exists())
        self.service.complete(checkpoint_id, frozen)
        self.assertEqual(self.service.changes(checkpoint_id), [])

    def test_transient_git_cleanup_refuses_a_later_nonempty_write(self) -> None:
        """An external or agent write after capture is retained for normal checkpoint handling."""

        checkpoint_id, frozen = self.make_checkpoint()
        mountpoint = self.project_path / ".git"
        mountpoint.mkdir()
        fingerprint = self.service.capture_empty_internal_git_mountpoint(checkpoint_id, frozen)
        (mountpoint / "external.txt").write_text("do not remove\n", encoding="utf-8")

        self.assertFalse(
            self.service.discard_empty_internal_git_mountpoint(checkpoint_id, frozen, fingerprint)
        )
        self.assertTrue((mountpoint / "external.txt").is_file())
        self.service.complete(checkpoint_id, frozen)
        changes = {item["relative_path"] for item in self.service.changes(checkpoint_id)}
        self.assertEqual(changes, {".git", ".git/external.txt"})

    def test_transient_git_cleanup_never_touches_an_existing_repository(self) -> None:
        """A project that started with `.git` is excluded even if its directory is empty later."""

        mountpoint = self.project_path / ".git"
        mountpoint.mkdir()
        (mountpoint / "config").write_text("[core]\n", encoding="utf-8")
        checkpoint_id, frozen = self.make_checkpoint()

        self.assertIsNone(self.service.capture_empty_internal_git_mountpoint(checkpoint_id, frozen))
        self.assertFalse(self.service.discard_empty_internal_git_mountpoint(checkpoint_id, frozen, None))
        self.assertEqual((mountpoint / "config").read_text(encoding="utf-8"), "[core]\n")


if __name__ == "__main__":
    unittest.main()
