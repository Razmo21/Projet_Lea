from __future__ import annotations

import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4


BACKEND_DIRECTORY = Path(__file__).resolve().parents[1]
if str(BACKEND_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIRECTORY))

from app.conversation_deletion import (  # noqa: E402
    ConversationCleanupError,
    ConversationDeletionService,
)
from app.database import ConversationOperationError, Database  # noqa: E402
from app.memory import parse_memory_command  # noqa: E402


class ConversationDeletionTests(unittest.TestCase):
    """Vérifie les suppressions transversales sans toucher aux données réelles."""

    def setUp(self) -> None:
        """Crée une base, un projet et deux stockages privés entièrement temporaires."""

        self.temporary = tempfile.TemporaryDirectory(
            prefix="lea-delete-test-", dir=Path(__file__).resolve().parent
        )
        self.root = Path(self.temporary.name)
        self.database = Database(self.root / "lea.sqlite3")
        self.database.initialize()
        self.database.sync_projects([("Projet", "Projet")])
        self.project = self.database.list_projects()[0]
        self.checkpoints = self.root / "agent-checkpoints"
        self.runs = self.root / "openhands-runs"
        self.service = ConversationDeletionService(
            self.database, self.checkpoints, self.runs
        )

    def tearDown(self) -> None:
        """Retire les seules fixtures créées dans le répertoire temporaire du test."""

        self.temporary.cleanup()

    def _recorded_run(self, checkpoint_state: str) -> dict[str, str]:
        """Crée une conversation Programmation et un checkpoint dans l'état demandé."""

        run_id = str(uuid4())
        run = self.database.create_agent_run(
            run_id,
            self.project["id"],
            "development",
            "Lis le projet",
            record_conversation=True,
            model_id="test-model",
        )
        checkpoint_id = str(uuid4())
        storage_key = str(uuid4())
        self.database.create_project_checkpoint(
            checkpoint_id,
            run_id,
            self.project["id"],
            "Projet",
            "1:2",
            storage_key,
            [],
        )
        self.database.complete_project_checkpoint(checkpoint_id, [])
        self.database.update_agent_run(
            run_id,
            state="completed",
            validation_status="validated",
            result_summary="Tâche terminée.",
        )
        if checkpoint_state != "completed":
            self.database.transition_project_checkpoint(
                checkpoint_id,
                checkpoint_state,
                expected_states={"completed"},
            )

        run_directory = self.runs / run_id
        run_directory.mkdir(parents=True)
        (run_directory / "task.txt").write_text("Lis le projet", encoding="utf-8")
        checkpoint_directory = self.checkpoints / storage_key
        checkpoint_directory.mkdir(parents=True)
        (checkpoint_directory / "snapshot.bin").write_bytes(b"fixture")
        return {
            "run_id": run_id,
            "conversation_id": str(run["conversation_id"]),
            "checkpoint_id": checkpoint_id,
            "storage_key": storage_key,
        }

    def test_decided_programming_conversation_removes_only_private_artifacts(self) -> None:
        """Accept rend le run supprimable sans jamais toucher au projet utilisateur."""

        project_file = self.root / "project-user-file.txt"
        project_file.write_text("à conserver", encoding="utf-8")
        record = self._recorded_run("accepted")
        detail = self.database.get_conversation(record["conversation_id"])
        command = parse_memory_command("Retiens que je préfère les réponses courtes.")
        self.assertIsNotNone(command)
        self.database.apply_memory_command(
            command,
            "Retiens que je préfère les réponses courtes.",
            record["conversation_id"],
            detail["revision"],
        )
        detail = self.database.get_conversation(record["conversation_id"])

        cleaned = self.service.delete(record["conversation_id"], detail["revision"])

        self.assertEqual(cleaned, 2)
        self.assertFalse((self.runs / record["run_id"]).exists())
        self.assertFalse((self.checkpoints / record["storage_key"]).exists())
        self.assertEqual(project_file.read_text(encoding="utf-8"), "à conserver")
        with self.database.connection() as connection:
            for table in (
                "conversations",
                "messages",
                "agent_runs",
                "project_checkpoints",
                "checkpoint_files",
                "conversation_cleanup_artifacts",
            ):
                self.assertEqual(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0], 0)
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM projects").fetchone()[0], 1)
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM memories").fetchone()[0], 1)
            self.assertEqual(
                connection.execute("SELECT COUNT(*) FROM memory_sources").fetchone()[0],
                0,
            )
            self.assertEqual(connection.execute("PRAGMA foreign_key_check").fetchall(), [])

    def test_pending_checkpoint_blocks_deletion_without_side_effect(self) -> None:
        """Un checkpoint terminé mais indécis conserve conversation, run et copies."""

        record = self._recorded_run("completed")
        detail = self.database.get_conversation(record["conversation_id"])

        with self.assertRaisesRegex(ConversationOperationError, "Accepte ou restaure"):
            self.service.delete(record["conversation_id"], detail["revision"])

        self.assertTrue((self.runs / record["run_id"]).is_dir())
        self.assertTrue((self.checkpoints / record["storage_key"]).is_dir())
        self.assertEqual(self.database.get_conversation(record["conversation_id"])["id"], record["conversation_id"])
        self.assertEqual(self.database.list_cleanup_artifacts(), [])

    def test_external_cleanup_failure_is_tracked_and_retryable(self) -> None:
        """Un échec de fichier n'est pas annoncé comme succès et le même DELETE le répare."""

        record = self._recorded_run("rolled_back")
        detail = self.database.get_conversation(record["conversation_id"])
        with patch.object(
            self.service,
            "_remove_directory",
            side_effect=OSError("simulated locked file"),
        ):
            with self.assertRaises(ConversationCleanupError):
                self.service.delete(record["conversation_id"], detail["revision"])

        with self.database.connection() as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM conversations").fetchone()[0], 0)
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM agent_runs").fetchone()[0], 0)
        self.assertEqual(len(self.database.list_cleanup_artifacts(record["conversation_id"])), 2)

        restarted_database = Database(self.root / "lea.sqlite3")
        restarted_database.initialize()
        restarted_service = ConversationDeletionService(
            restarted_database, self.checkpoints, self.runs
        )
        self.assertEqual(
            restarted_service.delete(record["conversation_id"], detail["revision"]),
            2,
        )
        self.assertEqual(self.database.list_cleanup_artifacts(), [])
        self.assertFalse((self.runs / record["run_id"]).exists())
        self.assertFalse((self.checkpoints / record["storage_key"]).exists())

    def test_sql_failure_rolls_back_before_any_private_file_is_removed(self) -> None:
        """Une erreur transactionnelle garde la conversation et les deux copies intactes."""

        record = self._recorded_run("accepted")
        detail = self.database.get_conversation(record["conversation_id"])
        with self.database.connection() as connection:
            connection.execute(
                """
                CREATE TRIGGER fail_conversation_delete
                BEFORE DELETE ON conversations
                BEGIN
                    SELECT RAISE(ABORT, 'simulated database failure');
                END
                """
            )

        with self.assertRaises(sqlite3.IntegrityError):
            self.service.delete(record["conversation_id"], detail["revision"])

        self.assertTrue((self.runs / record["run_id"]).is_dir())
        self.assertTrue((self.checkpoints / record["storage_key"]).is_dir())
        self.assertEqual(self.database.list_cleanup_artifacts(), [])
        self.assertEqual(self.database.get_conversation(record["conversation_id"])["id"], record["conversation_id"])

    def test_web_sources_and_messages_disappear_with_only_the_target_conversation(self) -> None:
        """Les cascades retirent les preuves Web sans affecter une autre conversation."""

        target, target_message = self.database.create_pending_conversation("Question Web")
        self.database.complete_generation(
            target,
            target_message,
            "Réponse [S1]",
            web_sources=(
                {
                    "title": "Source publique",
                    "url": "https://example.com/source",
                    "domain": "example.com",
                    "snippet": "Preuve déterministe",
                    "provider": "fixture",
                    "consulted_at": "2026-11-05T12:00:00.000Z",
                    "retrieval_status": "read",
                    "source_kind": "html",
                },
            ),
        )
        survivor, survivor_message = self.database.create_pending_conversation("À garder")
        self.database.complete_generation(survivor, survivor_message, "Conservée")

        revision = self.database.get_conversation(target)["revision"]
        self.service.delete(target, revision)
        with self.database.connection() as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM web_sources").fetchone()[0], 0)
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM messages WHERE conversation_id = ?", (target,)).fetchone()[0], 0)
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM messages WHERE conversation_id = ?", (survivor,)).fetchone()[0], 2)


if __name__ == "__main__":
    unittest.main()
