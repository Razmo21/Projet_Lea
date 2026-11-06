"""Nettoyage borné des copies privées liées à une conversation supprimée."""

from __future__ import annotations

import logging
import shutil
import sqlite3
from pathlib import Path
from uuid import UUID

from .database import ConversationNotFoundError, Database


FILE_ATTRIBUTE_REPARSE_POINT = 0x400
LOGGER = logging.getLogger(__name__)


class ConversationCleanupError(RuntimeError):
    """Signale qu'une copie contrôlée par Léa reste à supprimer."""


class ConversationDeletionService:
    """Coordonne la suppression SQLite et les deux stockages privés OpenHands."""

    def __init__(
        self,
        database: Database,
        checkpoint_root: str | Path,
        runtime_root: str | Path,
    ) -> None:
        """Fige les seules racines où ce service est autorisé à supprimer."""

        self.database = database
        self.roots = {
            "checkpoint": Path(checkpoint_root),
            "openhands_run": Path(runtime_root),
        }

    def _artifact_path(self, artifact_kind: str, storage_id: str) -> Path:
        """Résout un UUID sous sa racine fixe sans accepter de chemin externe."""

        root = self.roots.get(artifact_kind)
        if root is None:
            raise ConversationCleanupError("Le type de copie à supprimer est invalide.")
        try:
            canonical_id = str(UUID(storage_id))
        except (TypeError, ValueError, AttributeError) as error:
            raise ConversationCleanupError(
                "L’identifiant de copie à supprimer est invalide."
            ) from error

        resolved_root = root.resolve(strict=False)
        target = resolved_root / canonical_id
        try:
            target.resolve(strict=False).relative_to(resolved_root)
        except (OSError, ValueError) as error:
            raise ConversationCleanupError("La copie à supprimer sort du stockage privé.") from error
        return target

    @staticmethod
    def _remove_directory(target: Path) -> None:
        """Supprime un répertoire réel sans suivre de lien ni point de réanalyse."""

        try:
            metadata = target.lstat()
        except FileNotFoundError:
            return
        attributes = int(getattr(metadata, "st_file_attributes", 0))
        if target.is_symlink() or attributes & FILE_ATTRIBUTE_REPARSE_POINT:
            raise ConversationCleanupError(
                "La copie privée possède un type de chemin interdit."
            )
        if not target.is_dir():
            raise ConversationCleanupError("La copie privée attendue n’est pas un répertoire.")
        shutil.rmtree(target)

    def cleanup_pending(self, conversation_id: str | None = None) -> int:
        """Reprend chaque effacement en attente et n'acquitte qu'un retrait confirmé."""

        cleaned = 0
        for artifact in self.database.list_cleanup_artifacts(conversation_id):
            target = self._artifact_path(
                artifact["artifact_kind"], artifact["storage_id"]
            )
            try:
                self._remove_directory(target)
            except (OSError, ConversationCleanupError) as error:
                raise ConversationCleanupError(
                    "Une copie privée de la conversation reste à supprimer."
                ) from error
            self.database.complete_cleanup_artifact(
                artifact["artifact_kind"], artifact["storage_id"]
            )
            cleaned += 1
        return cleaned

    def delete(self, conversation_id: str, expected_revision: int) -> int:
        """Supprime la conversation puis confirme le retrait de ses copies privées."""

        try:
            self.database.delete_conversation(conversation_id, expected_revision)
        except ConversationNotFoundError:
            # Une première tentative peut avoir validé SQLite avant un échec de
            # fichier. Le même DELETE reprend alors ce nettoyage, sans recréer
            # ni archiver la conversation.
            if not self.database.list_cleanup_artifacts(conversation_id):
                raise
        cleaned = self.cleanup_pending(conversation_id)
        try:
            self.database.reclaim_storage()
        except (OSError, sqlite3.Error, RuntimeError) as error:
            # La conversation et ses copies sont déjà absentes. La compaction
            # est une maintenance distincte et pourra être reprise à l'arrêt.
            LOGGER.warning("sqlite_reclaim_deferred error=%s", type(error).__name__)
        return cleaned
