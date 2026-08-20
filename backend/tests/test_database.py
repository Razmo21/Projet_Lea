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
    MEMORY_DUPLICATE_CONFIRMATION,
    MEMORY_FORGOTTEN_CONFIRMATION,
    MEMORY_NOT_FOUND_CONFIRMATION,
    MEMORY_REMEMBERED_CONFIRMATION,
    RevisionConflictError,
)
from app.memory import (  # noqa: E402
    MEMORY_CONTEXT_TOKEN_LIMIT,
    MemoryCapacityError,
    estimate_memory_context_tokens,
    parse_memory_command,
)
from app.migrations import (  # noqa: E402
    MIGRATIONS,
    MigrationError,
    SCHEMA_VERSION,
    apply_migrations,
)


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
        self.assertIn("idx_memories_normalized_content", indexes)
        self.assertIn("idx_memory_sources_conversation_id", indexes)

        with self.database.connection() as connection:
            tables = {
                row[0]
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                ).fetchall()
            }
            kind = next(
                row
                for row in connection.execute("PRAGMA table_info(messages)")
                if row[1] == "kind"
            )
        self.assertIn("memories", tables)
        self.assertIn("memory_sources", tables)
        self.assertEqual(kind[3], 1)
        self.assertEqual(kind[4], "'conversation'")
        with self.database.connection() as connection:
            source_foreign_keys = {
                (row[3], row[2], row[4], row[6])
                for row in connection.execute(
                    "PRAGMA foreign_key_list(memory_sources)"
                ).fetchall()
            }
        self.assertEqual(
            source_foreign_keys,
            {
                ("memory_id", "memories", "id", "CASCADE"),
                ("conversation_id", "conversations", "id", "CASCADE"),
            },
        )

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
            connection.executemany(
                "INSERT INTO schema_migrations(version, applied_at) VALUES (?, 'partial')",
                ((1,), (2,), (3,)),
            )
            connection.commit()
        finally:
            connection.close()

        with self.assertRaisesRegex(RuntimeError, "incomplet"):
            self.database.initialize()

    def test_stage_8_database_migrates_to_latest_schema_without_data_loss(self) -> None:
        self.database_path.parent.mkdir(parents=True)
        connection = sqlite3.connect(self.database_path, isolation_level=None)
        try:
            self.assertEqual(apply_migrations(connection, {1: MIGRATIONS[1]}), 1)
            connection.execute(
                """
                INSERT INTO conversations(
                    id, title, title_origin, created_at, updated_at,
                    revision, generation_active
                ) VALUES ('conversation-v1', 'Titre v1', 'manual', 'created', 'updated', 7, 0)
                """
            )
            connection.execute(
                """
                INSERT INTO messages(
                    id, conversation_id, position, role, content, status,
                    error_code, created_at, updated_at
                ) VALUES (
                    'message-v1', 'conversation-v1', 1, 'user',
                    'Contenu v1', 'completed', NULL, 'created', 'updated'
                )
                """
            )
        finally:
            connection.close()

        self.assertEqual(self.database.initialize(), SCHEMA_VERSION)
        detail = self.database.get_conversation("conversation-v1")
        self.assertEqual(detail["title"], "Titre v1")
        self.assertEqual(detail["revision"], 7)
        self.assertEqual(detail["messages"][0]["content"], "Contenu v1")
        self.assertEqual(detail["messages"][0]["kind"], "conversation")

        with self.database.connection() as migrated:
            versions = [
                int(row[0])
                for row in migrated.execute(
                    "SELECT version FROM schema_migrations ORDER BY version"
                ).fetchall()
            ]
            self.assertEqual(versions, [1, 2, 3])
            self.assertEqual(migrated.execute("PRAGMA quick_check").fetchone()[0], "ok")
            self.assertEqual(migrated.execute("PRAGMA foreign_key_check").fetchall(), [])

    def test_stage_9_database_backfills_sources_and_preserves_global_memories(self) -> None:
        self.database_path.parent.mkdir(parents=True)
        connection = sqlite3.connect(self.database_path, isolation_level=None)
        try:
            connection.execute("PRAGMA foreign_keys = ON")
            self.assertEqual(
                apply_migrations(connection, {1: MIGRATIONS[1], 2: MIGRATIONS[2]}),
                2,
            )
            connection.execute(
                """
                INSERT INTO conversations(
                    id, title, title_origin, created_at, updated_at,
                    revision, generation_active
                ) VALUES ('source-v2', 'Souvenir v2', 'automatic',
                          '2026-01-01T00:00:00.000Z',
                          '2026-01-01T00:00:00.000Z', 1, 0)
                """
            )
            connection.execute(
                """
                INSERT INTO conversations(
                    id, title, title_origin, created_at, updated_at,
                    revision, generation_active
                ) VALUES ('duplicate-source-v2', 'Doublon v2', 'automatic',
                          '2026-01-02T00:00:00.000Z',
                          '2026-01-02T00:00:00.000Z', 1, 0)
                """
            )
            connection.execute(
                """
                INSERT INTO memories(
                    id, content, normalized_content, created_at, updated_at
                ) VALUES ('memory-live', 'mon chien s''appelle Rex.',
                          'mon chien s''appelle rex',
                          '2026-01-01T00:00:00.000Z',
                          '2026-01-01T00:00:00.000Z')
                """
            )
            connection.execute(
                """
                INSERT INTO memories(
                    id, content, normalized_content, created_at, updated_at
                ) VALUES ('memory-orphan', 'ancien fait', 'ancien fait',
                          '2025-01-01T00:00:00.000Z',
                          '2025-01-01T00:00:00.000Z')
                """
            )
            connection.executemany(
                """
                INSERT INTO messages(
                    id, conversation_id, position, role, content, status,
                    error_code, created_at, updated_at, kind
                ) VALUES (?, ?, ?, ?, ?, 'completed', NULL, ?, ?, 'memory')
                """,
                (
                    (
                        "memory-user-v2",
                        "source-v2",
                        1,
                        "user",
                        "Retiens que mon chien s'appelle Rex.",
                        "2026-01-01T00:00:00.000Z",
                        "2026-01-01T00:00:00.000Z",
                    ),
                    (
                        "memory-assistant-v2",
                        "source-v2",
                        2,
                        "assistant",
                        MEMORY_REMEMBERED_CONFIRMATION,
                        "2026-01-01T00:00:00.000Z",
                        "2026-01-01T00:00:00.000Z",
                    ),
                    (
                        "duplicate-user-v2",
                        "duplicate-source-v2",
                        1,
                        "user",
                        "Mémorise que mon chien s'appelle Rex !",
                        "2026-01-02T00:00:00.000Z",
                        "2026-01-02T00:00:00.000Z",
                    ),
                    (
                        "duplicate-assistant-v2",
                        "duplicate-source-v2",
                        2,
                        "assistant",
                        MEMORY_DUPLICATE_CONFIRMATION,
                        "2026-01-02T00:00:00.000Z",
                        "2026-01-02T00:00:00.000Z",
                    ),
                ),
            )
        finally:
            connection.close()

        self.assertEqual(self.database.initialize(), SCHEMA_VERSION)
        self.assertEqual(
            [memory["normalized_content"] for memory in self.database.list_memories()],
            ["ancien fait", "mon chien s'appelle rex"],
        )
        with self.database.connection() as migrated:
            self.assertEqual(
                [
                    tuple(row)
                    for row in migrated.execute(
                        """
                        SELECT memory_id, conversation_id FROM memory_sources
                        ORDER BY conversation_id
                        """
                    ).fetchall()
                ],
                [
                    ("memory-live", "duplicate-source-v2"),
                    ("memory-live", "source-v2"),
                ],
            )
            self.assertEqual(migrated.execute("PRAGMA quick_check").fetchone()[0], "ok")
            self.assertEqual(migrated.execute("PRAGMA foreign_key_check").fetchall(), [])

    def test_stage_9_migration_rolls_back_a_failed_rebuild(self) -> None:
        self.database_path.parent.mkdir(parents=True)
        connection = sqlite3.connect(self.database_path, isolation_level=None)
        try:
            connection.execute("PRAGMA foreign_keys = ON")
            self.assertEqual(apply_migrations(connection, {1: MIGRATIONS[1]}), 1)
            connection.execute(
                """
                INSERT INTO conversations(
                    id, title, title_origin, created_at, updated_at,
                    revision, generation_active
                ) VALUES ('rollback-conversation', 'Titre', 'manual',
                          'created', 'updated', 4, 0)
                """
            )
            connection.execute(
                """
                INSERT INTO messages(
                    id, conversation_id, position, role, content, status,
                    error_code, created_at, updated_at
                ) VALUES ('rollback-message', 'rollback-conversation', 1,
                          'user', 'Contenu intact', 'completed', NULL,
                          'created', 'updated')
                """
            )
            failing_v2 = tuple(MIGRATIONS[2][:-1]) + ("INVALID SQL",)
            with self.assertRaises(MigrationError):
                apply_migrations(connection, {1: MIGRATIONS[1], 2: failing_v2})
            versions = connection.execute(
                "SELECT version FROM schema_migrations ORDER BY version"
            ).fetchall()
            old_columns = {
                row[1] for row in connection.execute("PRAGMA table_info(messages)")
            }
            memories = connection.execute(
                "SELECT name FROM sqlite_master WHERE name = 'memories'"
            ).fetchone()
            conversation = connection.execute(
                "SELECT title, revision FROM conversations WHERE id = 'rollback-conversation'"
            ).fetchone()
            message = connection.execute(
                "SELECT content FROM messages WHERE id = 'rollback-message'"
            ).fetchone()
            quick_check = connection.execute("PRAGMA quick_check").fetchone()[0]
            foreign_key_violations = connection.execute(
                "PRAGMA foreign_key_check"
            ).fetchall()
        finally:
            connection.close()

        self.assertEqual(versions, [(1,)])
        self.assertNotIn("kind", old_columns)
        self.assertIsNone(memories)
        self.assertEqual(conversation, ("Titre", 4))
        self.assertEqual(message, ("Contenu intact",))
        self.assertEqual(quick_check, "ok")
        self.assertEqual(foreign_key_violations, [])

    def test_stage_9_provenance_migration_rolls_back_completely(self) -> None:
        self.database_path.parent.mkdir(parents=True)
        connection = sqlite3.connect(self.database_path, isolation_level=None)
        try:
            connection.execute("PRAGMA foreign_keys = ON")
            self.assertEqual(
                apply_migrations(connection, {1: MIGRATIONS[1], 2: MIGRATIONS[2]}),
                2,
            )
            connection.execute(
                """
                INSERT INTO memories(
                    id, content, normalized_content, created_at, updated_at
                ) VALUES ('orphan-before-failure', 'fait intact', 'fait intact',
                          'created', 'updated')
                """
            )
            # L'instruction invalide vient après le backfill : le test prouve
            # que la provenance et la version migrée sont annulées ensemble.
            failing_v3 = tuple(MIGRATIONS[3]) + ("INVALID SQL",)
            with self.assertRaises(MigrationError):
                apply_migrations(
                    connection,
                    {1: MIGRATIONS[1], 2: MIGRATIONS[2], 3: failing_v3},
                )
            versions = connection.execute(
                "SELECT version FROM schema_migrations ORDER BY version"
            ).fetchall()
            source_table = connection.execute(
                "SELECT name FROM sqlite_master WHERE name = 'memory_sources'"
            ).fetchone()
            memory = connection.execute(
                "SELECT content FROM memories WHERE id = 'orphan-before-failure'"
            ).fetchone()
        finally:
            connection.close()

        self.assertEqual(versions, [(1,), (2,)])
        self.assertIsNone(source_table)
        self.assertEqual(memory, ("fait intact",))

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
            connection.execute(
                """
                INSERT INTO messages(
                    id, conversation_id, position, role, content, status,
                    created_at, updated_at
                ) VALUES ('literal-marker', ?, 3, 'user',
                          'Je parle du texte /no_think.', 'completed', 'x', 'x')
                """,
                (conversation_id,),
            )
            self.assertEqual(
                connection.execute(
                    "SELECT content FROM messages WHERE id = 'literal-marker'"
                ).fetchone()[0],
                "Je parle du texte /no_think.",
            )
            connection.execute("DELETE FROM messages WHERE id = 'literal-marker'")
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
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute(
                    """
                    INSERT INTO messages(
                        id, conversation_id, position, role, content, status,
                        created_at, updated_at, kind
                    ) VALUES ('bad-kind', ?, 3, 'user', 'x', 'completed',
                              'x', 'x', 'unknown')
                    """,
                    (conversation_id,),
                )
            connection.execute(
                """
                INSERT INTO memories(
                    id, content, normalized_content, created_at, updated_at
                ) VALUES ('memory-one', 'Je m''appelle Stan.',
                          'je m''appelle stan', 'x', 'x')
                """
            )
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute(
                    """
                    INSERT INTO memories(
                        id, content, normalized_content, created_at, updated_at
                    ) VALUES ('memory-two', 'je m''appelle Stan',
                              'je m''appelle stan', 'y', 'y')
                    """
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

    def test_memory_commands_are_atomic_exact_and_visible(self) -> None:
        self.database.initialize()
        remember = parse_memory_command("Retiens que je m'appelle Stan.")
        self.assertIsNotNone(remember)
        conversation_id = self.database.apply_memory_command(
            remember,
            "Retiens que je m'appelle Stan.",
            None,
            None,
        )
        remembered = self.database.get_conversation(conversation_id)
        self.assertEqual(remembered["revision"], 1)
        self.assertEqual(
            [message["content"] for message in remembered["messages"]],
            ["Retiens que je m'appelle Stan.", MEMORY_REMEMBERED_CONFIRMATION],
        )
        self.assertEqual(
            [message["kind"] for message in remembered["messages"]],
            ["memory", "memory"],
        )
        self.assertEqual(len(self.database.list_memories()), 1)
        self.assertEqual(self.database.list_memories()[0]["content"], "je m'appelle Stan.")
        with self.database.connection() as connection:
            self.assertEqual(
                connection.execute("SELECT COUNT(*) FROM memory_sources").fetchone()[0],
                1,
            )

        duplicate = parse_memory_command("  RETIENS que je m’appelle Stan !")
        self.assertIsNotNone(duplicate)
        self.database.apply_memory_command(
            duplicate,
            "RETIENS que je m’appelle Stan !",
            conversation_id,
            remembered["revision"],
        )
        duplicated = self.database.get_conversation(conversation_id)
        self.assertEqual(duplicated["messages"][-1]["content"], MEMORY_DUPLICATE_CONFIRMATION)
        self.assertEqual(len(self.database.list_memories()), 1)
        with self.database.connection() as connection:
            self.assertEqual(
                connection.execute("SELECT COUNT(*) FROM memory_sources").fetchone()[0],
                1,
            )

        semantic_miss = parse_memory_command("Oublie que mon prénom est Stan.")
        self.assertIsNotNone(semantic_miss)
        self.database.apply_memory_command(
            semantic_miss,
            "Oublie que mon prénom est Stan.",
            conversation_id,
            duplicated["revision"],
        )
        missed = self.database.get_conversation(conversation_id)
        self.assertEqual(missed["messages"][-1]["content"], MEMORY_NOT_FOUND_CONFIRMATION)
        self.assertEqual(len(self.database.list_memories()), 1)

        forget = parse_memory_command("Oublie que je m’appelle Stan")
        self.assertIsNotNone(forget)
        self.database.apply_memory_command(
            forget,
            "Oublie que je m’appelle Stan",
            conversation_id,
            missed["revision"],
        )
        forgotten = self.database.get_conversation(conversation_id)
        self.assertEqual(forgotten["messages"][-1]["content"], MEMORY_FORGOTTEN_CONFIRMATION)
        self.assertEqual(self.database.list_memories(), [])
        with self.database.connection() as connection:
            self.assertEqual(
                connection.execute("SELECT COUNT(*) FROM memory_sources").fetchone()[0],
                0,
            )

    def test_deleting_the_only_source_conversation_keeps_global_memory(self) -> None:
        self.database.initialize()
        command = parse_memory_command("Mémorise que mon chien s'appelle Rex.")
        self.assertIsNotNone(command)
        conversation_id = self.database.apply_memory_command(
            command,
            "Mémorise que mon chien s'appelle Rex.",
            None,
            None,
        )
        detail = self.database.get_conversation(conversation_id)

        self.database.delete_conversation(conversation_id, detail["revision"])

        self.assertEqual(
            [memory["normalized_content"] for memory in self.database.list_memories()],
            ["mon chien s'appelle rex"],
        )
        with self.database.connection() as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM messages").fetchone()[0], 0)
            self.assertEqual(
                connection.execute("SELECT COUNT(*) FROM memory_sources").fetchone()[0],
                0,
            )

    def test_memory_survives_deletion_of_all_source_conversations(self) -> None:
        self.database.initialize()
        command = parse_memory_command("Retiens que mon chien s'appelle Rex.")
        self.assertIsNotNone(command)
        first_conversation = self.database.apply_memory_command(
            command,
            "Retiens que mon chien s'appelle Rex.",
            None,
            None,
        )
        duplicate_command = parse_memory_command("Mémorise que mon chien s'appelle Rex.")
        self.assertIsNotNone(duplicate_command)
        second_conversation = self.database.apply_memory_command(
            duplicate_command,
            "Mémorise que mon chien s'appelle Rex.",
            None,
            None,
        )

        with self.database.connection() as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM memories").fetchone()[0], 1)
            self.assertEqual(
                connection.execute("SELECT COUNT(*) FROM memory_sources").fetchone()[0],
                2,
            )

        first_revision = self.database.get_conversation(first_conversation)["revision"]
        self.database.delete_conversation(first_conversation, first_revision)
        self.assertEqual(len(self.database.list_memories()), 1)
        with self.database.connection() as connection:
            self.assertEqual(
                connection.execute("SELECT conversation_id FROM memory_sources").fetchone()[0],
                second_conversation,
            )

        second_revision = self.database.get_conversation(second_conversation)["revision"]
        self.database.delete_conversation(second_conversation, second_revision)
        self.assertEqual(
            [memory["normalized_content"] for memory in self.database.list_memories()],
            ["mon chien s'appelle rex"],
        )
        with self.database.connection() as connection:
            self.assertEqual(
                connection.execute("SELECT COUNT(*) FROM memory_sources").fetchone()[0],
                0,
            )

    def test_memory_command_rolls_back_if_confirmation_cannot_be_stored(self) -> None:
        self.database.initialize()
        with self.database.connection() as connection:
            connection.execute(
                """
                CREATE TRIGGER fail_memory_confirmation
                BEFORE INSERT ON messages
                WHEN NEW.kind = 'memory' AND NEW.role = 'assistant'
                BEGIN
                    SELECT RAISE(ABORT, 'simulated confirmation failure');
                END
                """
            )
        command = parse_memory_command("Retiens que je m'appelle Stan.")
        self.assertIsNotNone(command)

        with self.assertRaises(sqlite3.IntegrityError):
            self.database.apply_memory_command(
                command,
                "Retiens que je m'appelle Stan.",
                None,
                None,
            )

        with self.database.connection() as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM memories").fetchone()[0], 0)
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM memory_sources").fetchone()[0], 0)
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM conversations").fetchone()[0], 0)
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM messages").fetchone()[0], 0)

    def test_memory_tours_cannot_be_edited_regenerated_or_retried(self) -> None:
        self.database.initialize()
        command = parse_memory_command("Retiens que je m'appelle Stan.")
        self.assertIsNotNone(command)
        conversation_id = self.database.apply_memory_command(
            command,
            "Retiens que je m'appelle Stan.",
            None,
            None,
        )
        detail = self.database.get_conversation(conversation_id)
        user, assistant = detail["messages"]

        from app.database import ConversationOperationError

        with self.assertRaises(ConversationOperationError):
            self.database.edit_user_message(
                conversation_id,
                user["id"],
                "Autre texte",
                detail["revision"],
            )
        with self.assertRaises(ConversationOperationError):
            self.database.regenerate_assistant_message(
                conversation_id,
                assistant["id"],
                detail["revision"],
            )
        with self.assertRaises(ConversationOperationError):
            self.database.retry_message(
                conversation_id,
                user["id"],
                detail["revision"],
            )

    def test_memory_capacity_refuses_candidate_without_partial_write(self) -> None:
        self.database.initialize()
        conversation_id: str | None = None
        revision: int | None = None
        rejected = False

        for index in range(30):
            original = f"Retiens que souvenir {index} " + "x" * 180 + "."
            command = parse_memory_command(original)
            self.assertIsNotNone(command)
            memories_before = self.database.list_memories()
            conversations_before = self.database.list_conversations()
            message_count_before = sum(
                item["message_count"] for item in conversations_before
            )
            try:
                conversation_id = self.database.apply_memory_command(
                    command,
                    original,
                    conversation_id,
                    revision,
                )
            except MemoryCapacityError:
                rejected = True
                self.assertEqual(self.database.list_memories(), memories_before)
                self.assertEqual(
                    sum(
                        item["message_count"]
                        for item in self.database.list_conversations()
                    ),
                    message_count_before,
                )
                break
            detail = self.database.get_conversation(conversation_id)
            revision = detail["revision"]

        self.assertTrue(rejected)
        contents = [memory["content"] for memory in self.database.list_memories()]
        self.assertGreater(len(contents), 1)
        self.assertLessEqual(
            estimate_memory_context_tokens(contents),
            MEMORY_CONTEXT_TOKEN_LIMIT,
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
