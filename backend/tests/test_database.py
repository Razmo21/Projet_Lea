from __future__ import annotations

import sqlite3
import sys
import tempfile
import threading
import unittest
from pathlib import Path


BACKEND_DIRECTORY = Path(__file__).resolve().parents[1]
if str(BACKEND_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIRECTORY))

from app.database import (  # noqa: E402
    DEFAULT_DATABASE_PATH,
    Database,
    RevisionConflictError,
)
from app.migrations import MigrationError, SCHEMA_VERSION, apply_migrations  # noqa: E402


class TemporaryDatabaseTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory(
            prefix="lea-db-test-", dir=Path(__file__).resolve().parent
        )
        self.database_path = Path(self.temporary_directory.name) / "nested" / "test.sqlite3"
        self.database = Database(self.database_path)

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def test_empty_database_migrates_idempotently_with_required_pragmas(self) -> None:
        self.assertFalse(self.database_path.parent.exists())
        self.assertEqual(self.database.initialize(), SCHEMA_VERSION)
        self.assertTrue(self.database_path.is_file())
        self.assertEqual(self.database.initialize(), SCHEMA_VERSION)
        self.assertNotEqual(self.database.path, DEFAULT_DATABASE_PATH)

        pragmas = self.database.pragmas()
        self.assertEqual(pragmas["foreign_keys"], 1)
        self.assertEqual(pragmas["journal_mode"].lower(), "wal")
        self.assertEqual(pragmas["schema_version"], SCHEMA_VERSION)

        with self.database.connection() as connection:
            indexes = {
                row[0]
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'index'"
                ).fetchall()
            }
        self.assertIn("idx_conversations_updated_at", indexes)
        self.assertIn("idx_messages_conversation_position", indexes)

    def test_initialize_wraps_sqlite_open_errors(self) -> None:
        database = Database(Path(self.temporary_directory.name))

        with self.assertRaisesRegex(
            RuntimeError,
            "Impossible de préparer la base SQLite locale",
        ) as captured:
            database.initialize()

        self.assertIsInstance(captured.exception.__cause__, sqlite3.Error)

    def test_unknown_future_schema_version_is_rejected(self) -> None:
        self.database.initialize()
        with self.database.connection() as connection:
            connection.execute(
                "INSERT INTO schema_migrations(version, applied_at) VALUES (99, 'future')"
            )

        with self.assertRaises(MigrationError):
            self.database.initialize()

    def test_partially_migrated_schema_is_rejected(self) -> None:
        self.database_path.parent.mkdir(parents=True)
        connection = sqlite3.connect(self.database_path)
        try:
            connection.execute(
                """
                CREATE TABLE schema_migrations (
                    version INTEGER PRIMARY KEY,
                    applied_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                "INSERT INTO schema_migrations(version, applied_at) VALUES (1, 'partial')"
            )
            connection.commit()
        finally:
            connection.close()

        with self.assertRaisesRegex(RuntimeError, "incomplet"):
            self.database.initialize()

    def test_failed_migration_rolls_back_its_schema_changes(self) -> None:
        self.database_path.parent.mkdir(parents=True)
        connection = sqlite3.connect(self.database_path, isolation_level=None)
        try:
            with self.assertRaises(MigrationError):
                apply_migrations(
                    connection,
                    {1: ("CREATE TABLE should_rollback(id INTEGER)", "INVALID SQL")},
                )
            table = connection.execute(
                "SELECT name FROM sqlite_master WHERE name = 'should_rollback'"
            ).fetchone()
            version = connection.execute(
                "SELECT COUNT(*) FROM schema_migrations"
            ).fetchone()[0]
        finally:
            connection.close()

        self.assertIsNone(table)
        self.assertEqual(version, 0)

    def test_constraints_order_foreign_keys_and_delete_cascade(self) -> None:
        self.database.initialize()
        conversation_id, user_id = self.database.create_pending_conversation("Question")
        self.database.complete_generation(conversation_id, user_id, "Réponse")

        with self.database.connection() as connection:
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute(
                    """
                    INSERT INTO messages(
                        id, conversation_id, position, role, content, status,
                        created_at, updated_at
                    ) VALUES ('duplicate', ?, 1, 'user', 'x', 'completed', 'x', 'x')
                    """,
                    (conversation_id,),
                )
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute(
                    """
                    INSERT INTO messages(
                        id, conversation_id, position, role, content, status,
                        created_at, updated_at
                    ) VALUES ('internal', ?, 3, 'user', '/no_think', 'completed', 'x', 'x')
                    """,
                    (conversation_id,),
                )
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute(
                    """
                    INSERT INTO messages(
                        id, conversation_id, position, role, content, status,
                        error_code, created_at, updated_at
                    ) VALUES ('unsafe-error', ?, 3, 'user', 'x', 'failed',
                              'C:\\secret\\path', 'x', 'x')
                    """,
                    (conversation_id,),
                )
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute(
                    """
                    INSERT INTO messages(
                        id, conversation_id, position, role, content, status,
                        created_at, updated_at
                    ) VALUES ('system', ?, 3, 'system', 'x', 'completed', 'x', 'x')
                    """,
                    (conversation_id,),
                )
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute(
                    """
                    INSERT INTO messages(
                        id, conversation_id, position, role, content, status,
                        created_at, updated_at
                    ) VALUES ('bad-status', ?, 3, 'user', 'x', 'unknown', 'x', 'x')
                    """,
                    (conversation_id,),
                )

        revision = self.database.get_conversation(conversation_id)["revision"]
        self.database.delete_conversation(conversation_id, revision)
        with self.database.connection() as connection:
            self.assertEqual(
                connection.execute(
                    "SELECT COUNT(*) FROM messages WHERE conversation_id = ?",
                    (conversation_id,),
                ).fetchone()[0],
                0,
            )

    def test_automatic_title_manual_title_and_revision_growth(self) -> None:
        self.database.initialize()
        conversation_id, user_id = self.database.create_pending_conversation(
            "  Une   première question avec espaces  "
        )
        initial = self.database.get_conversation(conversation_id)
        self.assertEqual(initial["title"], "Une première question avec espaces")
        self.assertEqual(initial["title_origin"], "automatic")

        self.database.complete_generation(conversation_id, user_id, "Réponse")
        completed = self.database.get_conversation(conversation_id)
        self.assertGreater(completed["revision"], initial["revision"])
        self.database.rename_conversation(
            conversation_id, "Titre manuel", completed["revision"]
        )
        renamed = self.database.get_conversation(conversation_id)
        self.assertEqual(renamed["title_origin"], "manual")

        first_user = renamed["messages"][0]
        self.database.edit_user_message(
            conversation_id,
            first_user["id"],
            "Première question modifiée",
            renamed["revision"],
        )
        edited = self.database.get_conversation(conversation_id)
        self.assertEqual(edited["title"], "Titre manuel")

    def test_destructive_edit_and_regeneration_remove_the_following_messages(self) -> None:
        self.database.initialize()
        conversation_id, q1 = self.database.create_pending_conversation("Q1")
        self.database.complete_generation(conversation_id, q1, "R1")
        revision = self.database.get_conversation(conversation_id)["revision"]
        q2 = self.database.add_pending_message(conversation_id, "Q2", revision)
        self.database.complete_generation(conversation_id, q2, "R2")
        before_edit = self.database.get_conversation(conversation_id)
        self.assertEqual([m["content"] for m in before_edit["messages"]], ["Q1", "R1", "Q2", "R2"])

        self.database.edit_user_message(
            conversation_id,
            q1,
            "Q1 modifiée",
            before_edit["revision"],
        )
        after_edit = self.database.get_conversation(conversation_id)
        self.assertEqual([m["content"] for m in after_edit["messages"]], ["Q1 modifiée"])
        self.assertEqual(after_edit["messages"][0]["status"], "pending")
        self.database.complete_generation(conversation_id, q1, "Nouvelle R1")

        revision = self.database.get_conversation(conversation_id)["revision"]
        q2_new = self.database.add_pending_message(conversation_id, "Q2 nouvelle", revision)
        self.database.complete_generation(conversation_id, q2_new, "R2 nouvelle")
        before_regeneration = self.database.get_conversation(conversation_id)
        assistant = before_regeneration["messages"][-1]
        self.database.regenerate_assistant_message(
            conversation_id,
            assistant["id"],
            before_regeneration["revision"],
        )
        after_regeneration = self.database.get_conversation(conversation_id)
        self.assertEqual(
            [m["content"] for m in after_regeneration["messages"]],
            ["Q1 modifiée", "Nouvelle R1", "Q2 nouvelle"],
        )
        self.assertEqual(after_regeneration["messages"][-1]["status"], "pending")

    def test_stale_revision_is_rejected_atomically(self) -> None:
        self.database.initialize()
        conversation_id, user_id = self.database.create_pending_conversation("Question")
        self.database.complete_generation(conversation_id, user_id, "Réponse")
        revision = self.database.get_conversation(conversation_id)["revision"]
        self.database.rename_conversation(conversation_id, "Premier onglet", revision)
        with self.assertRaises(RevisionConflictError):
            self.database.rename_conversation(conversation_id, "Second onglet", revision)
        self.assertEqual(
            self.database.get_conversation(conversation_id)["title"], "Premier onglet"
        )

    def test_pending_generation_is_recovered_as_failed_on_restart(self) -> None:
        self.database.initialize()
        conversation_id, _ = self.database.create_pending_conversation("Question interrompue")
        revision_before = self.database.get_conversation(conversation_id)["revision"]

        recovered_database = Database(self.database_path)
        recovered_database.initialize()
        conversation = recovered_database.get_conversation(conversation_id)

        self.assertFalse(conversation["generation_active"])
        self.assertEqual(conversation["messages"][0]["status"], "failed")
        self.assertEqual(conversation["messages"][0]["error"], "interrupted")
        self.assertGreater(conversation["revision"], revision_before)

    def test_get_conversation_uses_one_read_snapshot(self) -> None:
        self.database.initialize()
        conversation_id, first_user_id = self.database.create_pending_conversation("Q1")
        self.database.complete_generation(conversation_id, first_user_id, "R1")
        revision = self.database.get_conversation(conversation_id)["revision"]

        writer_start = threading.Event()
        writer_done = threading.Event()
        trace_triggered = threading.Event()
        writer_errors: list[BaseException] = []

        def write_during_read() -> None:
            writer_start.wait(5)
            try:
                Database(self.database_path).add_pending_message(
                    conversation_id, "Q2", revision
                )
            except BaseException as error:
                writer_errors.append(error)
            finally:
                writer_done.set()

        class CoordinatedReadDatabase(Database):
            def _connect(inner_self) -> sqlite3.Connection:
                connection = super()._connect()

                def trace(statement: str) -> None:
                    compact = " ".join(statement.lower().split())
                    if (
                        compact.startswith("select * from messages")
                        and not trace_triggered.is_set()
                    ):
                        trace_triggered.set()
                        writer_start.set()
                        if not writer_done.wait(5):
                            writer_errors.append(
                                TimeoutError("L’écriture concurrente n’a pas terminé.")
                            )

                connection.set_trace_callback(trace)
                return connection

        writer = threading.Thread(target=write_during_read, daemon=True)
        writer.start()
        snapshot = CoordinatedReadDatabase(self.database_path).get_conversation(
            conversation_id
        )
        writer.join(5)

        self.assertTrue(trace_triggered.is_set())
        self.assertFalse(writer.is_alive())
        if writer_errors:
            raise writer_errors[0]
        self.assertEqual(snapshot["message_count"], 2)
        self.assertEqual(len(snapshot["messages"]), 2)

        current = self.database.get_conversation(conversation_id)
        self.assertEqual(current["message_count"], 3)
        self.assertEqual(len(current["messages"]), 3)


if __name__ == "__main__":
    unittest.main()
