"""Minimal, hash-verified project checkpoints for OpenHands runs.

The service intentionally stores snapshots outside SQLite while SQLite keeps
only metadata and hashes.  This keeps the database small and lets a rollback
refuse any external project change instead of overwriting it silently.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import stat
import tempfile
from dataclasses import dataclass
from pathlib import Path, PureWindowsPath
from uuid import UUID, uuid4

from .database import CheckpointStateError, Database
from .workspace import FILE_ATTRIBUTE_REPARSE_POINT, FrozenProject, WorkspaceGuard, WorkspacePathError


class CheckpointError(RuntimeError):
    """Reports a controlled checkpoint failure without leaking private storage paths."""


class CheckpointConflictError(CheckpointError):
    """Reports an external project change which makes a rollback unsafe."""


@dataclass(frozen=True)
class InventoryEntry:
    """Captures one regular file or directory without following any reparse point."""

    relative_path: str
    entry_type: str
    path: Path
    sha256: str | None
    size: int | None
    modified_ns: int

    def public(self, change: str) -> dict[str, str | int | None]:
        """Return the browser-safe part of an inventory entry."""

        return {
            "relative_path": self.relative_path,
            "entry_type": self.entry_type,
            "change": change,
            "before_sha256": None,
            "after_sha256": self.sha256,
        }


@dataclass(frozen=True)
class InternalGitMountpoint:
    """Identify the empty host directory Docker creates for a private `.git` tmpfs mount.

    The identity is captured after the run container starts and before the SDK
    can act.  Finalization can then remove only that unchanged transient
    mountpoint; an external replacement or write remains visible to the
    checkpoint conflict machinery.
    """

    device: int
    inode: int
    modified_ns: int


class CheckpointService:
    """Creates, finalizes, accepts, and safely restores one frozen project snapshot."""

    # Keep this deliberately small and explicit instead of consulting a
    # project's .gitignore: an ignored source or configuration file must
    # remain protected by a checkpoint.  These names are generated Python
    # execution artifacts only, and the two collections make a future
    # addition reviewable without broadening the rule accidentally.
    _GENERATED_ARTIFACT_DIRECTORY_NAMES = frozenset({"__pycache__", ".pytest_cache"})
    _GENERATED_ARTIFACT_FILE_SUFFIXES = (".pyc", ".pyo")

    def __init__(self, database: Database, guard: WorkspaceGuard, storage_root: str | Path) -> None:
        """Freeze the database, workspace authority, and private checkpoint storage root."""

        self.database = database
        self.guard = guard
        self.storage_root = Path(storage_root)

    @staticmethod
    def _relative_parts(relative_path: str) -> tuple[str, ...]:
        """Validate a database path before it is ever joined to a project directory."""

        candidate = PureWindowsPath(relative_path)
        if (
            not relative_path
            or candidate.is_absolute()
            or candidate.drive
            or candidate.root
            or ".." in candidate.parts
            or any(part in {"", "."} for part in candidate.parts)
        ):
            raise CheckpointError("Le chemin de checkpoint est invalide.")
        return tuple(candidate.parts)

    @staticmethod
    def _is_reparse(metadata: os.stat_result, path: Path) -> bool:
        """Recognize Windows reparse points and portable symbolic links without following either."""

        attributes = int(getattr(metadata, "st_file_attributes", 0))
        return path.is_symlink() or bool(attributes & FILE_ATTRIBUTE_REPARSE_POINT)

    @classmethod
    def _is_generated_artifact_path(cls, relative_parts: tuple[str, ...], entry_type: str) -> bool:
        """Recognize only generated Python cache paths, never project ignore rules.

        A directory rule covers its complete subtree because every descendant
        is cache data.  The suffix rule applies only to regular files, so a
        user directory coincidentally ending in ``.pyc`` or ``.pyo`` remains
        checkpointed normally.
        """

        normalized_parts = tuple(part.casefold() for part in relative_parts)
        if any(part in cls._GENERATED_ARTIFACT_DIRECTORY_NAMES for part in normalized_parts[:-1]):
            return True
        leaf = normalized_parts[-1]
        if entry_type == "directory":
            return leaf in cls._GENERATED_ARTIFACT_DIRECTORY_NAMES
        return entry_type == "file" and leaf.endswith(cls._GENERATED_ARTIFACT_FILE_SUFFIXES)

    @classmethod
    def _is_generated_artifact_row(cls, row: dict[str, object]) -> bool:
        """Apply the same narrow rule to persisted legacy checkpoint rows.

        Old checkpoints can already contain cache rows.  Filtering them at
        read/rollback time preserves their historical SQLite records while
        preventing regenerated cache data from blocking a safe source rollback.
        Invalid persisted paths intentionally remain visible to the normal
        validation path instead of being hidden by this compatibility branch.
        """

        try:
            relative_parts = cls._relative_parts(str(row["relative_path"]))
        except (CheckpointError, KeyError, TypeError):
            return False
        entry_types = (row.get("entry_type"), row.get("after_entry_type"))
        return any(
            isinstance(entry_type, str)
            and cls._is_generated_artifact_path(relative_parts, entry_type)
            for entry_type in entry_types
        )

    @staticmethod
    def _hash_file(path: Path) -> tuple[str, int]:
        """Hash a regular file incrementally so a large project never needs a RAM-sized copy."""

        digest = hashlib.sha256()
        size = 0
        try:
            with path.open("rb") as source:
                while chunk := source.read(1024 * 1024):
                    digest.update(chunk)
                    size += len(chunk)
        except OSError as error:
            raise CheckpointError("Un fichier du projet ne peut pas être inventorié.") from error
        return digest.hexdigest(), size

    def _inventory(self, frozen: FrozenProject) -> list[InventoryEntry]:
        """Walk a revalidated project without recursing through symlinks or junctions."""

        project = self.guard.revalidate_frozen_project(frozen)
        entries: list[InventoryEntry] = []

        def walk(directory: Path, relative_prefix: tuple[str, ...], *, collect: bool) -> None:
            """Visit one directory while retaining reparse checks inside ignored cache trees."""

            try:
                children = sorted(directory.iterdir(), key=lambda item: (item.name.casefold(), item.name))
            except OSError as error:
                raise CheckpointError("Le projet ne peut pas être inventorié.") from error
            for child in children:
                try:
                    metadata = child.stat(follow_symlinks=False)
                except OSError as error:
                    raise CheckpointError("Un élément du projet est inaccessible.") from error
                if self._is_reparse(metadata, child):
                    raise CheckpointError("Les liens et reparse points sont interdits dans un run OpenHands.")
                relative = (*relative_prefix, child.name)
                relative_path = "/".join(relative)
                mode = metadata.st_mode
                if stat.S_ISDIR(mode):
                    ignored = self._is_generated_artifact_path(relative, "directory")
                    if collect and not ignored:
                        entries.append(
                            InventoryEntry(relative_path, "directory", child, None, None, int(metadata.st_mtime_ns))
                        )
                    # Continue scanning ignored cache directories for a link
                    # or reparse point, but never include their volatile data
                    # in a snapshot or user-visible diff.
                    walk(child, relative, collect=collect and not ignored)
                elif stat.S_ISREG(mode):
                    if not collect or self._is_generated_artifact_path(relative, "file"):
                        continue
                    digest, size = self._hash_file(child)
                    # Hashing can observe a replacement.  Re-stat and reject a
                    # mismatch rather than preserving a misleading snapshot.
                    try:
                        after = child.stat(follow_symlinks=False)
                    except OSError as error:
                        raise CheckpointError("Un fichier a changé pendant l'inventaire.") from error
                    if self._is_reparse(after, child) or int(after.st_mtime_ns) != int(metadata.st_mtime_ns):
                        raise CheckpointError("Un fichier a changé pendant l'inventaire.")
                    entries.append(
                        InventoryEntry(relative_path, "file", child, digest, size, int(after.st_mtime_ns))
                    )
                else:
                    raise CheckpointError("Le projet contient un type de fichier non pris en charge.")

        walk(project.path, (), collect=True)
        self.guard.revalidate_frozen_project(frozen)
        return entries

    def _storage_directory(self, storage_key: str, *, create: bool) -> Path:
        """Resolve one UUID-named private storage directory below the configured checkpoint root."""

        try:
            canonical_key = str(UUID(storage_key))
        except (TypeError, ValueError, AttributeError) as error:
            raise CheckpointError("La clé de stockage de checkpoint est invalide.") from error
        root = self.storage_root.resolve(strict=False)
        target = root / canonical_key
        if create:
            target.mkdir(parents=True, exist_ok=False)
        try:
            resolved = target.resolve(strict=True)
            resolved.relative_to(root.resolve(strict=False))
        except (OSError, ValueError) as error:
            raise CheckpointError("Le stockage privé du checkpoint est indisponible.") from error
        return resolved

    @staticmethod
    def _entry_for_database(entry: InventoryEntry, backup_name: str | None) -> dict[str, object]:
        """Translate the pre-run inventory to the constrained SQLite checkpoint row."""

        return {
            "relative_path": entry.relative_path,
            "entry_type": entry.entry_type,
            "before_exists": True,
            "before_sha256": entry.sha256,
            "before_size": entry.size,
            "before_modified_ns": entry.modified_ns,
            "backup_name": backup_name,
        }

    def create(self, run_id: str, frozen: FrozenProject) -> dict[str, object]:
        """Copy an initial immutable snapshot before the Agent Server receives the project mount."""

        initial_entries = self._inventory(frozen)
        storage_key = str(uuid4())
        storage = self._storage_directory(storage_key, create=True)
        backup_directory = storage / "files"
        backup_directory.mkdir()
        database_entries: list[dict[str, object]] = []
        try:
            for entry in initial_entries:
                backup_name: str | None = None
                if entry.entry_type == "file":
                    # Re-check the file immediately before copying it.  The
                    # backup hash must equal the checked inventory hash.
                    metadata = entry.path.stat(follow_symlinks=False)
                    if self._is_reparse(metadata, entry.path):
                        raise CheckpointError("Un fichier a changé pendant le checkpoint.")
                    backup_name = f"{uuid4()}.bin"
                    backup_path = backup_directory / backup_name
                    shutil.copyfile(entry.path, backup_path)
                    digest, size = self._hash_file(backup_path)
                    if digest != entry.sha256 or size != entry.size:
                        raise CheckpointError("Un fichier a changé pendant le checkpoint.")
                database_entries.append(self._entry_for_database(entry, backup_name))
            # A second inventory rejects a source edit that occurred while the
            # backup copy was made, before SQLite advertises a usable snapshot.
            if self._inventory(frozen) != initial_entries:
                raise CheckpointError("Le projet a changé pendant le checkpoint.")
            project = self.guard.revalidate_frozen_project(frozen)
            return self.database.create_project_checkpoint(
                str(uuid4()),
                run_id,
                frozen.project_id,
                project.relative_path,
                f"{project.identity[0]}:{project.identity[1]}",
                storage_key,
                database_entries,
            )
        except BaseException:
            # The directory was created by this invocation and is never a user
            # project.  Removing it prevents an unusable snapshot from looking
            # like a valid one after an interrupted start.
            shutil.rmtree(storage, ignore_errors=True)
            raise

    @staticmethod
    def _entry_state(entry: InventoryEntry) -> dict[str, object]:
        """Create the compact after-state accepted by the existing SQLite schema."""

        return {
            "relative_path": entry.relative_path,
            "entry_type": entry.entry_type,
            "sha256": entry.sha256,
            "size": entry.size,
            "modified_ns": entry.modified_ns,
        }

    def complete(self, checkpoint_id: str, frozen: FrozenProject) -> dict[str, object]:
        """Freeze the after-run inventory only once the actual Agent Server has stopped."""

        try:
            after_entries = [self._entry_state(entry) for entry in self._inventory(frozen)]
            return self.database.complete_project_checkpoint(checkpoint_id, after_entries)
        except BaseException as error:
            # A failure must remain visible rather than being mistaken for a
            # completed checkpoint with an unknown after-state.
            try:
                self.database.transition_project_checkpoint(
                    checkpoint_id,
                    "failed",
                    expected_states={"ready"},
                    error="Inventaire final de checkpoint impossible.",
                )
            except (CheckpointStateError, ValueError):
                pass
            if isinstance(error, CheckpointError):
                raise
            raise CheckpointError("L'inventaire final du checkpoint a échoué.") from error

    @staticmethod
    def _internal_git_fingerprint(metadata: os.stat_result) -> InternalGitMountpoint:
        """Capture the fields needed to reject a replaced temporary mountpoint later."""

        return InternalGitMountpoint(
            device=int(metadata.st_dev),
            inode=int(metadata.st_ino),
            modified_ns=int(metadata.st_mtime_ns),
        )

    def _checkpoint_had_git_metadata(self, checkpoint_id: str) -> bool:
        """Keep an existing user repository outside the transient-Docker cleanup path."""

        return any(
            str(row["relative_path"]) == ".git" or str(row["relative_path"]).startswith(".git/")
            for row in self.database.list_checkpoint_files(checkpoint_id)
        )

    def capture_empty_internal_git_mountpoint(
        self,
        checkpoint_id: str,
        frozen: FrozenProject,
    ) -> InternalGitMountpoint | None:
        """Fingerprint Docker's empty nested tmpfs mountpoint without mutating a project.

        Docker Desktop may create the host-side directory required by a nested
        `/workspace/.git` tmpfs bind.  Capture it only when the checkpoint
        proves the project was not already a Git repository and it is an empty
        ordinary directory.  Any ambiguous path stays untouched.
        """

        if self._checkpoint_had_git_metadata(checkpoint_id):
            return None
        project = self.guard.revalidate_frozen_project(frozen)
        target = project.path / ".git"
        try:
            metadata = target.stat(follow_symlinks=False)
        except FileNotFoundError:
            return None
        except OSError:
            return None
        if self._is_reparse(metadata, target) or not stat.S_ISDIR(metadata.st_mode):
            return None
        try:
            if any(target.iterdir()):
                return None
        except OSError:
            return None
        return self._internal_git_fingerprint(metadata)

    def discard_empty_internal_git_mountpoint(
        self,
        checkpoint_id: str,
        frozen: FrozenProject,
        mountpoint: InternalGitMountpoint | None,
    ) -> bool:
        """Remove only the exact unchanged empty mountpoint captured for this run.

        This is intentionally narrower than a cleanup of `.git`: it refuses
        existing repositories, reparse points, files, non-empty directories,
        and any identity or timestamp change.  A refusal leaves the path for
        the normal post-run inventory and conflict protection instead of
        deleting a possible user or agent change.
        """

        if mountpoint is None or self._checkpoint_had_git_metadata(checkpoint_id):
            return False
        project = self.guard.revalidate_frozen_project(frozen)
        target = project.path / ".git"
        try:
            before = target.stat(follow_symlinks=False)
        except (FileNotFoundError, OSError):
            return False
        if self._is_reparse(before, target) or not stat.S_ISDIR(before.st_mode):
            return False
        if self._internal_git_fingerprint(before) != mountpoint:
            return False
        try:
            if any(target.iterdir()):
                return False
            after = target.stat(follow_symlinks=False)
        except (FileNotFoundError, OSError):
            return False
        if self._is_reparse(after, target) or not stat.S_ISDIR(after.st_mode):
            return False
        if self._internal_git_fingerprint(after) != mountpoint:
            return False
        try:
            target.rmdir()
        except OSError:
            return False
        return True

    @staticmethod
    def _identity_text(identity: tuple[int, int]) -> str:
        """Encode a Windows filesystem identity exactly as the checkpoint database does."""

        return f"{identity[0]}:{identity[1]}"

    def validate_checkpoint_project(self, checkpoint_id: str, frozen: FrozenProject) -> dict[str, object]:
        """Reject a rollback or recovery when its persisted project identity has changed.

        The mutable active project is deliberately absent from this check.  Both
        the frozen path captured by the run and the identity stored in SQLite
        must still identify the same direct child of IA_WORKSPACE.
        """

        checkpoint = self.database.get_project_checkpoint(checkpoint_id)
        if checkpoint["project_id"] != frozen.project_id:
            raise CheckpointError("Le checkpoint ne correspond pas au projet figé du run.")
        expected_identity = checkpoint["project_identity"]
        if expected_identity != self._identity_text(frozen.workspace_path.identity):
            raise CheckpointConflictError(
                "Le projet figé du checkpoint a changé ; restauration refusée pour éviter un écrasement."
            )
        try:
            current = self.guard.revalidate_frozen_project(frozen)
        except WorkspacePathError as error:
            raise CheckpointConflictError(
                "Le projet figé du checkpoint n'est plus identique ; restauration refusée."
            ) from error
        if self._identity_text(current.identity) != expected_identity:
            raise CheckpointConflictError(
                "Le projet figé du checkpoint a changé ; restauration refusée pour éviter un écrasement."
            )
        return checkpoint

    def record_conflict(self, checkpoint_id: str, message: str) -> dict[str, object]:
        """Persist one detected conflict while preserving already-terminal checkpoint states."""

        checkpoint = self.database.get_project_checkpoint(checkpoint_id)
        if checkpoint["state"] != "completed":
            return checkpoint
        try:
            return self.database.transition_project_checkpoint(
                checkpoint_id,
                "conflict",
                expected_states={"completed"},
                error=message,
            )
        except CheckpointStateError:
            # A concurrent accept or rollback owns the terminal state and must
            # never be overwritten by a late conflict observation.
            return self.database.get_project_checkpoint(checkpoint_id)

    @staticmethod
    def _row_change(row: dict[str, object]) -> str:
        """Classify one persisted before/after pair without exposing backup storage names."""

        before_exists = bool(row["before_exists"])
        after_exists = bool(row["after_exists"])
        if not before_exists and after_exists:
            return "created"
        if before_exists and not after_exists:
            return "deleted"
        if not before_exists and not after_exists:
            return "unchanged"
        if (
            row["entry_type"] != row["after_entry_type"]
            or row["before_sha256"] != row["after_sha256"]
            or row["before_size"] != row["after_size"]
        ):
            return "modified"
        return "unchanged"

    def changes(self, checkpoint_id: str) -> list[dict[str, object]]:
        """Return a browser-safe diff of files changed by a completed OpenHands run."""

        checkpoint = self.database.get_project_checkpoint(checkpoint_id)
        if checkpoint["state"] not in {"completed", "accepted", "rolled_back", "conflict"}:
            raise CheckpointStateError("Le diff est indisponible tant que le checkpoint n'est pas terminé.")
        return [
            {
                "relative_path": row["relative_path"],
                "entry_type": row["after_entry_type"] or row["entry_type"],
                "change": self._row_change(row),
            }
            for row in self.database.list_checkpoint_files(checkpoint_id)
            if not self._is_generated_artifact_row(row) and self._row_change(row) != "unchanged"
        ]

    def accept(self, checkpoint_id: str) -> dict[str, object]:
        """Mark a completed checkpoint accepted without deleting its audit metadata."""

        return self.database.transition_project_checkpoint(
            checkpoint_id,
            "accepted",
            expected_states={"completed"},
        )

    @staticmethod
    def _matches_after(current: InventoryEntry | None, row: dict[str, object]) -> bool:
        """Compare current filesystem state to the exact after-run checkpoint state."""

        if not bool(row["after_exists"]):
            return current is None
        if current is None or current.entry_type != row["after_entry_type"]:
            return False
        if current.entry_type == "directory":
            # Directory metadata changes whenever a generated cache is
            # recreated below it.  Files and child entries are independently
            # inventoried, so their exact presence/content still guards every
            # real source, configuration, or data change.
            return True
        if current.modified_ns != row["after_modified_ns"]:
            return False
        if current.entry_type == "file":
            return current.sha256 == row["after_sha256"] and current.size == row["after_size"]
        return False

    def _assert_after_unchanged(self, checkpoint_id: str, frozen: FrozenProject) -> list[dict[str, object]]:
        """Ensure no external write occurred since the run before changing anything on disk."""

        rows = [
            row
            for row in self.database.list_checkpoint_files(checkpoint_id)
            if not self._is_generated_artifact_row(row)
        ]
        current = {entry.relative_path: entry for entry in self._inventory(frozen)}
        for row in rows:
            relative_path = str(row["relative_path"])
            if not self._matches_after(current.pop(relative_path, None), row):
                raise CheckpointConflictError(
                    "Le projet a changé après le run ; rollback refusé pour éviter un écrasement."
                )
        if current:
            raise CheckpointConflictError(
                "Le projet a changé après le run ; rollback refusé pour éviter un écrasement."
            )
        return rows

    def _path_in_project(self, project_path: Path, relative_path: str) -> Path:
        """Join a persisted relative path only after the same strict syntax validation as the guard."""

        target = project_path.joinpath(*self._relative_parts(relative_path))
        try:
            target.relative_to(project_path)
        except ValueError as error:  # pragma: no cover - guarded by _relative_parts on Windows.
            raise CheckpointError("Le chemin de checkpoint sort du projet.") from error
        return target

    def _assert_target_chain(self, project_path: Path, target: Path) -> None:
        """Reject a reparse point inserted after the full post-run inventory.

        Rollback writes paths one at a time.  Rechecking every existing
        component immediately before that write closes the practical window in
        which a concurrent actor could replace a child directory with a link.
        """

        try:
            relative_parts = target.relative_to(project_path).parts
        except ValueError as error:  # pragma: no cover - guarded by _path_in_project.
            raise CheckpointError("Le chemin de checkpoint sort du projet.") from error
        cursor = project_path
        for part in relative_parts:
            cursor = cursor / part
            try:
                metadata = cursor.stat(follow_symlinks=False)
            except FileNotFoundError:
                return
            except OSError as error:
                raise CheckpointConflictError(
                    "Le projet a changé pendant le rollback ; restauration refusée."
                ) from error
            if self._is_reparse(metadata, cursor):
                raise CheckpointConflictError(
                    "Un lien ou reparse point est apparu pendant le rollback ; restauration refusée."
                )

    def _entry_at_target(self, project_path: Path, relative_path: str) -> InventoryEntry | None:
        """Read one rollback target without following a newly inserted reparse point."""

        target = self._path_in_project(project_path, relative_path)
        self._assert_target_chain(project_path, target)
        try:
            metadata = target.stat(follow_symlinks=False)
        except FileNotFoundError:
            return None
        except OSError as error:
            raise CheckpointConflictError(
                "Le projet a changé pendant le rollback ; restauration refusée."
            ) from error
        if self._is_reparse(metadata, target):
            raise CheckpointConflictError(
                "Un lien ou reparse point est apparu pendant le rollback ; restauration refusée."
            )
        if stat.S_ISDIR(metadata.st_mode):
            return InventoryEntry(relative_path, "directory", target, None, None, int(metadata.st_mtime_ns))
        if not stat.S_ISREG(metadata.st_mode):
            raise CheckpointConflictError(
                "Le type d'un fichier a changé pendant le rollback ; restauration refusée."
            )
        digest, size = self._hash_file(target)
        try:
            after = target.stat(follow_symlinks=False)
        except OSError as error:
            raise CheckpointConflictError(
                "Un fichier a changé pendant le rollback ; restauration refusée."
            ) from error
        if (
            self._is_reparse(after, target)
            or int(after.st_mtime_ns) != int(metadata.st_mtime_ns)
            or int(after.st_size) != int(metadata.st_size)
        ):
            raise CheckpointConflictError(
                "Un fichier a changé pendant le rollback ; restauration refusée."
            )
        return InventoryEntry(relative_path, "file", target, digest, size, int(after.st_mtime_ns))

    def _assert_target_after_state(
        self,
        project_path: Path,
        row: dict[str, object],
        *,
        allow_directory_timestamp_drift: bool = False,
    ) -> None:
        """Refuse an external target change immediately before a rollback mutation."""

        current = self._entry_at_target(project_path, str(row["relative_path"]))
        if (
            allow_directory_timestamp_drift
            and bool(row["after_exists"])
            and row["after_entry_type"] == "directory"
            and current is not None
            and current.entry_type == "directory"
        ):
            return
        if not self._matches_after(current, row):
            raise CheckpointConflictError(
                "Le projet a changé pendant le rollback ; restauration refusée pour éviter un écrasement."
            )

    def _assert_target_absent(self, project_path: Path, relative_path: str) -> None:
        """Ensure a path intentionally removed by this rollback was not recreated externally."""

        if self._entry_at_target(project_path, relative_path) is not None:
            raise CheckpointConflictError(
                "Le projet a changé pendant le rollback ; restauration refusée pour éviter un écrasement."
            )

    def rollback(self, checkpoint_id: str, frozen: FrozenProject) -> dict[str, object]:
        """Restore the initial snapshot while rechecking each target before it is changed."""

        checkpoint = self.database.get_project_checkpoint(checkpoint_id)
        if checkpoint["project_id"] != frozen.project_id:
            raise CheckpointError("Le checkpoint ne correspond pas au projet figé du run.")
        if checkpoint["state"] != "completed":
            raise CheckpointStateError("Seul un checkpoint terminé peut être restauré.")
        try:
            self.validate_checkpoint_project(checkpoint_id, frozen)
            rows = self._assert_after_unchanged(checkpoint_id, frozen)
            project = self.guard.revalidate_frozen_project(frozen)
            # The public row deliberately hides the storage key. Retrieve it
            # only through the trusted database connection used by this
            # backend service.
            storage = self._storage_directory(self._storage_key(checkpoint_id), create=False)
            removed_after_paths: set[str] = set()

            # Remove paths that did not exist before the run, deepest first.
            for row in sorted(
                rows,
                key=lambda item: len(self._relative_parts(str(item["relative_path"]))),
                reverse=True,
            ):
                if bool(row["before_exists"]):
                    continue
                relative_path = str(row["relative_path"])
                self._assert_target_after_state(
                    project.path,
                    row,
                    allow_directory_timestamp_drift=row["after_entry_type"] == "directory",
                )
                current = self._entry_at_target(project.path, relative_path)
                if current is None:
                    continue
                try:
                    if current.entry_type == "file":
                        current.path.unlink()
                    else:
                        current.path.rmdir()
                except OSError as error:
                    raise CheckpointConflictError(
                        "Le projet a changé pendant le rollback ; restauration refusée."
                    ) from error
                removed_after_paths.add(relative_path)

            # A file can have replaced an old directory (or vice versa). Remove
            # the incompatible after-state before rebuilding the original tree.
            for row in rows:
                if not bool(row["before_exists"]):
                    continue
                target = self._path_in_project(project.path, str(row["relative_path"]))
                expected_type = str(row["entry_type"])
                current = self._entry_at_target(project.path, str(row["relative_path"]))
                if current is None or current.entry_type == expected_type:
                    continue
                self._assert_target_after_state(
                    project.path,
                    row,
                    allow_directory_timestamp_drift=current.entry_type == "directory",
                )
                try:
                    if current.entry_type == "directory":
                        target.rmdir()
                    else:
                        target.unlink()
                except OSError as error:
                    raise CheckpointConflictError(
                        "Le projet a changé pendant le rollback ; restauration refusée."
                    ) from error
                removed_after_paths.add(str(row["relative_path"]))

            for row in sorted(rows, key=lambda item: len(self._relative_parts(str(item["relative_path"])))):
                if bool(row["before_exists"]) and row["entry_type"] == "directory":
                    relative_path = str(row["relative_path"])
                    target = self._path_in_project(project.path, relative_path)
                    if relative_path in removed_after_paths:
                        self._assert_target_absent(project.path, relative_path)
                    else:
                        self._assert_target_after_state(
                            project.path,
                            row,
                            allow_directory_timestamp_drift=True,
                        )
                    if not target.exists():
                        try:
                            target.mkdir()
                        except OSError as error:
                            raise CheckpointConflictError(
                                "Le projet a changé pendant le rollback ; restauration refusée."
                            ) from error

            files_root = storage / "files"
            for row in rows:
                if not bool(row["before_exists"]) or row["entry_type"] != "file":
                    continue
                backup_name = row["backup_name"]
                if not isinstance(backup_name, str):
                    raise CheckpointError("La sauvegarde de checkpoint est invalide.")
                source = files_root / backup_name
                relative_path = str(row["relative_path"])
                target = self._path_in_project(project.path, relative_path)
                if relative_path in removed_after_paths:
                    self._assert_target_absent(project.path, relative_path)
                else:
                    self._assert_target_after_state(project.path, row)
                if not target.parent.is_dir() or target.parent.is_symlink():
                    raise CheckpointConflictError(
                        "Le parent d'un fichier a changé pendant le rollback ; restauration refusée."
                    )
                temporary_path: Path | None = None
                with tempfile.NamedTemporaryFile(delete=False, dir=target.parent) as temporary:
                    temporary_path = Path(temporary.name)
                try:
                    shutil.copyfile(source, temporary_path)
                    digest, size = self._hash_file(temporary_path)
                    if digest != row["before_sha256"] or size != row["before_size"]:
                        raise CheckpointError("La sauvegarde de checkpoint ne correspond pas à son hash.")
                    os.replace(temporary_path, target)
                    modified_ns = row["before_modified_ns"]
                    if isinstance(modified_ns, int):
                        os.utime(target, ns=(modified_ns, modified_ns))
                finally:
                    if temporary_path is not None and temporary_path.exists():
                        temporary_path.unlink(missing_ok=True)

            # Verify that the restored tree is exactly the captured pre-run tree.
            restored = {entry.relative_path: entry for entry in self._inventory(frozen)}
            before_paths = {str(row["relative_path"]) for row in rows if bool(row["before_exists"])}
            if set(restored) != before_paths or any(
                not self._matches_before(restored.get(str(row["relative_path"])), row)
                for row in rows
            ):
                raise CheckpointError("La restauration de checkpoint est incomplète.")
            return self.database.transition_project_checkpoint(
                checkpoint_id,
                "rolled_back",
                expected_states={"completed"},
            )
        except CheckpointConflictError as error:
            self.record_conflict(checkpoint_id, "Le projet a changé pendant le rollback.")
            raise error
        except BaseException as error:
            message = "La restauration du checkpoint a échoué."
            try:
                self.database.transition_project_checkpoint(
                    checkpoint_id,
                    "failed",
                    expected_states={"completed"},
                    error=message,
                )
            except (CheckpointStateError, ValueError):
                pass
            if isinstance(error, CheckpointError):
                raise
            raise CheckpointError(message) from error

    @staticmethod
    def _matches_before(current: InventoryEntry | None, row: dict[str, object]) -> bool:
        """Compare a restored entry to its initial checkpoint metadata."""

        if not bool(row["before_exists"]):
            return current is None
        if current is None or current.entry_type != row["entry_type"]:
            return False
        if current.entry_type == "file":
            return (
                current.modified_ns == row["before_modified_ns"]
                and current.sha256 == row["before_sha256"]
                and current.size == row["before_size"]
            )
        # The compact v6 schema intentionally does not persist a before mtime
        # for directories; their contents are represented by separate rows.
        return True

    def _storage_key(self, checkpoint_id: str) -> str:
        """Read the private UUID only for the checkpoint service, never for an API response."""

        # Database intentionally hides storage_key from public checkpoint dicts.
        # This narrow query remains local to the trusted backend process.
        with self.database.connection() as connection:
            row = connection.execute(
                "SELECT storage_key FROM project_checkpoints WHERE checkpoint_id = ?", (checkpoint_id,)
            ).fetchone()
        if row is None:
            raise CheckpointError("Checkpoint introuvable.")
        return str(row["storage_key"])
