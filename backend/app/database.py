from __future__ import annotations

import os
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterator

from .memory import (
    EmptyMemoryCommandError,
    MEMORY_DUPLICATE_CONFIRMATION,
    MEMORY_FORGOTTEN_CONFIRMATION,
    MEMORY_NOT_FOUND_CONFIRMATION,
    MEMORY_REMEMBERED_CONFIRMATION,
    MemoryCommand,
    ensure_memory_capacity,
    parse_memory_command,
)
from .migrations import SCHEMA_VERSION, apply_migrations


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATABASE_PATH = PROJECT_ROOT / "data" / "lea.sqlite3"
MAX_TITLE_LENGTH = 100
AUTOMATIC_TITLE_LENGTH = 72


class ConversationNotFoundError(LookupError):
    pass


class MessageNotFoundError(LookupError):
    pass


class RevisionConflictError(RuntimeError):
    pass


class GenerationConflictError(RuntimeError):
    pass


class ConversationOperationError(RuntimeError):
    pass


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def normalize_spaces(value: str) -> str:
    return " ".join(value.split())


def automatic_title(first_message: str) -> str:
    normalized = normalize_spaces(first_message)
    if len(normalized) <= AUTOMATIC_TITLE_LENGTH:
        return normalized
    return normalized[: AUTOMATIC_TITLE_LENGTH - 1].rstrip() + "…"


def resolve_database_path(path: str | Path | None = None) -> Path:
    configured = str(path) if path is not None else os.environ.get("LEA_DB_PATH", "")
    if not configured.strip():
        return DEFAULT_DATABASE_PATH

    candidate = Path(configured)
    return candidate if candidate.is_absolute() else PROJECT_ROOT / candidate


class Database:
    """Autorité SQLite des conversations, messages et souvenirs de Léa."""

    # Connexions courtes : WAL autorise les lectures pendant une écriture.
    def __init__(self, path: str | Path | None = None) -> None:
        self.path = resolve_database_path(path)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(
            self.path,
            timeout=5.0,
            isolation_level=None,
            check_same_thread=False,
        )
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout = 5000")
        connection.execute("PRAGMA foreign_keys = ON")
        connection.create_function(
            "LEA_CASEFOLD",
            1,
            lambda value: str(value).casefold(),
            deterministic=True,
        )
        return connection

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        connection = self._connect()
        try:
            yield connection
        finally:
            connection.close()

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        with self.connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                yield connection
            except BaseException:
                connection.rollback()
                raise
            else:
                connection.commit()

    def initialize(self) -> int:
        """Prépare le fichier, applique les migrations et vérifie ses invariants."""

        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.connection() as connection:
                journal_mode = connection.execute("PRAGMA journal_mode = WAL").fetchone()
                if journal_mode is None or str(journal_mode[0]).lower() != "wal":
                    raise RuntimeError("SQLite n’a pas activé le mode WAL.")
                version = apply_migrations(connection)
                if version != SCHEMA_VERSION:
                    raise RuntimeError(
                        f"Version SQLite inattendue : {version} au lieu de {SCHEMA_VERSION}."
                    )
                self._validate_schema(connection)
            self.recover_interrupted_generations()
            return version
        except (OSError, sqlite3.Error) as error:
            raise RuntimeError(
                f"Impossible de préparer la base SQLite locale : {self.path}"
            ) from error

    @staticmethod
    def _validate_schema(connection: sqlite3.Connection) -> None:
        # Les noms seuls ne suffisent pas : les contraintes de provenance et
        # les cascades font partie des garanties structurelles du stockage.
        required_objects = {
            "schema_migrations": "table",
            "conversations": "table",
            "messages": "table",
            "memories": "table",
            "memory_sources": "table",
            "idx_conversations_updated_at": "index",
            "idx_messages_conversation_position": "index",
            "idx_messages_conversation_status": "index",
            "idx_memories_normalized_content": "index",
            "idx_memory_sources_conversation_id": "index",
        }
        rows = connection.execute(
            "SELECT name, type FROM sqlite_master WHERE name IN ({})".format(
                ",".join("?" for _ in required_objects)
            ),
            tuple(required_objects),
        ).fetchall()
        actual_objects = {str(row[0]): str(row[1]) for row in rows}
        if actual_objects != required_objects:
            raise RuntimeError("Le schéma SQLite local est incomplet ou incohérent.")
        message_columns = {
            str(row[1]): row
            for row in connection.execute("PRAGMA table_info(messages)").fetchall()
        }
        kind_column = message_columns.get("kind")
        if (
            kind_column is None
            or int(kind_column[3]) != 1
            or str(kind_column[4]).strip("'") != "conversation"
        ):
            raise RuntimeError("La classification des messages SQLite est incohérente.")
        memory_columns = {
            str(row[1]): row
            for row in connection.execute("PRAGMA table_info(memories)").fetchall()
        }
        if set(memory_columns) != {
            "id",
            "content",
            "normalized_content",
            "created_at",
            "updated_at",
        } or any(
            int(memory_columns[name][3]) != 1
            for name in ("content", "normalized_content", "created_at", "updated_at")
        ):
            raise RuntimeError("Le schéma de la mémoire SQLite est incohérent.")
        memory_indexes = {
            str(row[1]): bool(row[2])
            for row in connection.execute("PRAGMA index_list(memories)").fetchall()
        }
        if memory_indexes.get("idx_memories_normalized_content") is not True:
            raise RuntimeError("L’unicité de la mémoire SQLite est absente.")
        source_columns = {
            str(row[1]): row
            for row in connection.execute("PRAGMA table_info(memory_sources)").fetchall()
        }
        if (
            set(source_columns) != {"memory_id", "conversation_id", "created_at"}
            or any(int(source_columns[name][3]) != 1 for name in source_columns)
            or int(source_columns["memory_id"][5]) != 1
            or int(source_columns["conversation_id"][5]) != 2
        ):
            raise RuntimeError("La provenance des souvenirs SQLite est incohérente.")
        source_foreign_keys = {
            (str(row[3]), str(row[2]), str(row[4]), str(row[6]).upper())
            for row in connection.execute(
                "PRAGMA foreign_key_list(memory_sources)"
            ).fetchall()
        }
        if source_foreign_keys != {
            ("memory_id", "memories", "id", "CASCADE"),
            ("conversation_id", "conversations", "id", "CASCADE"),
        }:
            raise RuntimeError("Les cascades de provenance SQLite sont incohérentes.")
        quick_check = connection.execute("PRAGMA quick_check").fetchone()
        if quick_check is None or str(quick_check[0]).lower() != "ok":
            raise RuntimeError("Le contrôle d’intégrité SQLite a échoué.")
        if connection.execute("PRAGMA foreign_key_check").fetchone() is not None:
            raise RuntimeError("Une violation de clé étrangère existe dans SQLite.")

    def pragmas(self) -> dict[str, Any]:
        with self.connection() as connection:
            return {
                "foreign_keys": int(connection.execute("PRAGMA foreign_keys").fetchone()[0]),
                "journal_mode": str(connection.execute("PRAGMA journal_mode").fetchone()[0]),
                "schema_version": int(
                    connection.execute(
                        "SELECT COALESCE(MAX(version), 0) FROM schema_migrations"
                    ).fetchone()[0]
                ),
            }

    def recover_interrupted_generations(self) -> int:
        now = utc_now()
        with self.transaction() as connection:
            rows = connection.execute(
                """
                SELECT DISTINCT conversation_id
                FROM messages
                WHERE status = 'pending'
                UNION
                SELECT id FROM conversations WHERE generation_active = 1
                """
            ).fetchall()
            conversation_ids = [str(row[0]) for row in rows]
            if not conversation_ids:
                return 0

            placeholders = ",".join("?" for _ in conversation_ids)
            connection.execute(
                f"""
                UPDATE messages
                SET status = 'failed', error_code = 'interrupted', updated_at = ?
                WHERE status = 'pending' AND conversation_id IN ({placeholders})
                """,
                (now, *conversation_ids),
            )
            connection.execute(
                f"""
                UPDATE conversations
                SET generation_active = 0, revision = revision + 1, updated_at = ?
                WHERE id IN ({placeholders})
                """,
                (now, *conversation_ids),
            )
            return len(conversation_ids)

    @staticmethod
    def _summary_from_row(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": str(row["id"]),
            "title": str(row["title"]),
            "title_origin": str(row["title_origin"]),
            "created_at": str(row["created_at"]),
            "updated_at": str(row["updated_at"]),
            "revision": int(row["revision"]),
            "generation_active": bool(row["generation_active"]),
            "message_count": int(row["message_count"]) if "message_count" in row.keys() else 0,
        }

    @staticmethod
    def _message_from_row(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": str(row["id"]),
            "conversation_id": str(row["conversation_id"]),
            "position": int(row["position"]),
            "role": str(row["role"]),
            "content": str(row["content"]),
            "status": str(row["status"]),
            "error": str(row["error_code"]) if row["error_code"] is not None else None,
            "created_at": str(row["created_at"]),
            "updated_at": str(row["updated_at"]),
            "kind": str(row["kind"]),
        }

    @staticmethod
    def _memory_from_row(row: sqlite3.Row) -> dict[str, str]:
        return {
            "id": str(row["id"]),
            "content": str(row["content"]),
            "normalized_content": str(row["normalized_content"]),
            "created_at": str(row["created_at"]),
            "updated_at": str(row["updated_at"]),
        }

    @staticmethod
    def _conversation_row(
        connection: sqlite3.Connection, conversation_id: str
    ) -> sqlite3.Row:
        row = connection.execute(
            "SELECT * FROM conversations WHERE id = ?", (conversation_id,)
        ).fetchone()
        if row is None:
            raise ConversationNotFoundError("Conversation introuvable.")
        return row

    @staticmethod
    def _message_row(
        connection: sqlite3.Connection, conversation_id: str, message_id: str
    ) -> sqlite3.Row:
        row = connection.execute(
            "SELECT * FROM messages WHERE id = ? AND conversation_id = ?",
            (message_id, conversation_id),
        ).fetchone()
        if row is None:
            raise MessageNotFoundError("Message introuvable dans cette conversation.")
        return row

    @staticmethod
    def _assert_mutation_allowed(row: sqlite3.Row, expected_revision: int) -> None:
        if int(row["revision"]) != expected_revision:
            raise RevisionConflictError(
                "La conversation a changé dans une autre fenêtre. Son état actuel a été rechargé."
            )
        if bool(row["generation_active"]):
            raise GenerationConflictError(
                "Une génération est déjà active pour cette conversation."
            )

    def list_conversations(self, search: str = "") -> list[dict[str, Any]]:
        normalized_search = normalize_spaces(search)
        parameters: tuple[Any, ...] = ()
        condition = ""
        if normalized_search:
            condition = """
                WHERE instr(LEA_CASEFOLD(c.title), LEA_CASEFOLD(?)) > 0
                   OR EXISTS (
                       SELECT 1 FROM messages searched
                       WHERE searched.conversation_id = c.id
                         AND instr(LEA_CASEFOLD(searched.content), LEA_CASEFOLD(?)) > 0
                   )
            """
            parameters = (normalized_search, normalized_search)

        with self.connection() as connection:
            rows = connection.execute(
                f"""
                SELECT c.*, COUNT(m.id) AS message_count
                FROM conversations c
                LEFT JOIN messages m ON m.conversation_id = c.id
                {condition}
                GROUP BY c.id
                ORDER BY c.updated_at DESC, c.id
                """,
                parameters,
            ).fetchall()
        return [self._summary_from_row(row) for row in rows]

    def get_conversation(self, conversation_id: str) -> dict[str, Any]:
        # Les deux SELECT partagent un snapshot pour garder compteur et messages cohérents.
        with self.connection() as connection:
            connection.execute("BEGIN")
            try:
                row = connection.execute(
                    """
                    SELECT c.*, COUNT(m.id) AS message_count
                    FROM conversations c
                    LEFT JOIN messages m ON m.conversation_id = c.id
                    WHERE c.id = ?
                    GROUP BY c.id
                    """,
                    (conversation_id,),
                ).fetchone()
                if row is None:
                    raise ConversationNotFoundError("Conversation introuvable.")
                messages = connection.execute(
                    """
                    SELECT * FROM messages
                    WHERE conversation_id = ?
                    ORDER BY position ASC
                    """,
                    (conversation_id,),
                ).fetchall()
            except BaseException:
                connection.rollback()
                raise
            else:
                connection.commit()

        detail = self._summary_from_row(row)
        detail["messages"] = [self._message_from_row(message) for message in messages]
        return detail

    def list_memories(self) -> list[dict[str, str]]:
        # Cette liste est l'unique mémoire générale injectée au modèle.
        with self.connection() as connection:
            rows = connection.execute(
                "SELECT * FROM memories ORDER BY created_at ASC, id ASC"
            ).fetchall()
        return [self._memory_from_row(row) for row in rows]

    def apply_memory_command(
        self,
        command: MemoryCommand,
        original_message: str,
        conversation_id: str | None,
        expected_revision: int | None,
    ) -> str:
        now = utc_now()
        user_message_id = str(uuid.uuid4())
        assistant_message_id = str(uuid.uuid4())

        # Mémoire, provenance informative, conversation et confirmation sont
        # commitées ou annulées ensemble. BEGIN IMMEDIATE sérialise les writers.
        with self.transaction() as connection:
            is_new_conversation = conversation_id is None
            if conversation_id is None:
                if expected_revision is not None:
                    raise ConversationOperationError(
                        "Une nouvelle conversation ne possède pas encore de révision."
                    )
                conversation_id = str(uuid.uuid4())
                first_position = 1
            else:
                if expected_revision is None:
                    raise ConversationOperationError(
                        "La révision attendue est obligatoire pour une conversation existante."
                    )
                conversation = self._conversation_row(connection, conversation_id)
                self._assert_mutation_allowed(conversation, expected_revision)
                last_message = connection.execute(
                    """
                    SELECT role, status FROM messages
                    WHERE conversation_id = ? ORDER BY position DESC LIMIT 1
                    """,
                    (conversation_id,),
                ).fetchone()
                if last_message is not None and (
                    str(last_message["role"]) != "assistant"
                    or str(last_message["status"]) != "completed"
                ):
                    raise ConversationOperationError(
                        "La dernière question doit être réessayée avant de poursuivre."
                    )
                first_position = int(
                    connection.execute(
                        """
                        SELECT COALESCE(MAX(position), 0) + 1
                        FROM messages WHERE conversation_id = ?
                        """,
                        (conversation_id,),
                    ).fetchone()[0]
                )

            memory_id: str | None = None
            if command.action == "remember":
                existing = connection.execute(
                    "SELECT id FROM memories WHERE normalized_content = ?",
                    (command.normalized_content,),
                ).fetchone()
                if existing is None:
                    memory_id = str(uuid.uuid4())
                    existing_contents = [
                        str(row[0])
                        for row in connection.execute(
                            "SELECT content FROM memories ORDER BY created_at ASC, id ASC"
                        ).fetchall()
                    ]
                    ensure_memory_capacity([*existing_contents, command.content])
                    connection.execute(
                        """
                        INSERT INTO memories(
                            id, content, normalized_content, created_at, updated_at
                        ) VALUES (?, ?, ?, ?, ?)
                        """,
                        (
                            memory_id,
                            command.content,
                            command.normalized_content,
                            now,
                            now,
                        ),
                    )
                    confirmation = MEMORY_REMEMBERED_CONFIRMATION
                else:
                    memory_id = str(existing["id"])
                    confirmation = MEMORY_DUPLICATE_CONFIRMATION
            else:
                deleted = connection.execute(
                    "DELETE FROM memories WHERE normalized_content = ?",
                    (command.normalized_content,),
                ).rowcount
                confirmation = (
                    MEMORY_FORGOTTEN_CONFIRMATION
                    if deleted == 1
                    else MEMORY_NOT_FOUND_CONFIRMATION
                )

            if is_new_conversation:
                connection.execute(
                    """
                    INSERT INTO conversations(
                        id, title, title_origin, created_at, updated_at,
                        revision, generation_active
                    ) VALUES (?, ?, 'automatic', ?, ?, 1, 0)
                    """,
                    (conversation_id, automatic_title(original_message), now, now),
                )
            else:
                connection.execute(
                    """
                    UPDATE conversations
                    SET revision = revision + 1, updated_at = ?
                    WHERE id = ?
                    """,
                    (now, conversation_id),
                )

            if memory_id is not None:
                # Un fait unique peut avoir plusieurs conversations sources.
                # La clé composée évite de compter deux fois la même source.
                connection.execute(
                    """
                    INSERT OR IGNORE INTO memory_sources(
                        memory_id, conversation_id, created_at
                    ) VALUES (?, ?, ?)
                    """,
                    (memory_id, conversation_id, now),
                )

            connection.execute(
                """
                INSERT INTO messages(
                    id, conversation_id, position, role, content, status,
                    error_code, created_at, updated_at, kind
                ) VALUES (?, ?, ?, 'user', ?, 'completed', NULL, ?, ?, 'memory')
                """,
                (
                    user_message_id,
                    conversation_id,
                    first_position,
                    original_message,
                    now,
                    now,
                ),
            )
            connection.execute(
                """
                INSERT INTO messages(
                    id, conversation_id, position, role, content, status,
                    error_code, created_at, updated_at, kind
                ) VALUES (?, ?, ?, 'assistant', ?, 'completed', NULL, ?, ?, 'memory')
                """,
                (
                    assistant_message_id,
                    conversation_id,
                    first_position + 1,
                    confirmation,
                    now,
                    now,
                ),
            )

        return conversation_id

    def create_pending_conversation(self, content: str) -> tuple[str, str]:
        conversation_id = str(uuid.uuid4())
        message_id = str(uuid.uuid4())
        now = utc_now()
        title = automatic_title(content)
        with self.transaction() as connection:
            connection.execute(
                """
                INSERT INTO conversations(
                    id, title, title_origin, created_at, updated_at,
                    revision, generation_active
                ) VALUES (?, ?, 'automatic', ?, ?, 1, 1)
                """,
                (conversation_id, title, now, now),
            )
            connection.execute(
                """
                INSERT INTO messages(
                    id, conversation_id, position, role, content, status,
                    error_code, created_at, updated_at
                ) VALUES (?, ?, 1, 'user', ?, 'pending', NULL, ?, ?)
                """,
                (message_id, conversation_id, content, now, now),
            )
        return conversation_id, message_id

    def add_pending_message(
        self, conversation_id: str, content: str, expected_revision: int
    ) -> str:
        message_id = str(uuid.uuid4())
        now = utc_now()
        with self.transaction() as connection:
            conversation = self._conversation_row(connection, conversation_id)
            self._assert_mutation_allowed(conversation, expected_revision)
            last_message = connection.execute(
                """
                SELECT role, status FROM messages
                WHERE conversation_id = ? ORDER BY position DESC LIMIT 1
                """,
                (conversation_id,),
            ).fetchone()
            if last_message is not None and (
                str(last_message["role"]) != "assistant"
                or str(last_message["status"]) != "completed"
            ):
                raise ConversationOperationError(
                    "La dernière question doit être réessayée avant de poursuivre."
                )
            position = int(
                connection.execute(
                    "SELECT COALESCE(MAX(position), 0) + 1 FROM messages WHERE conversation_id = ?",
                    (conversation_id,),
                ).fetchone()[0]
            )
            connection.execute(
                """
                UPDATE conversations
                SET generation_active = 1, revision = revision + 1, updated_at = ?
                WHERE id = ?
                """,
                (now, conversation_id),
            )
            connection.execute(
                """
                INSERT INTO messages(
                    id, conversation_id, position, role, content, status,
                    error_code, created_at, updated_at
                ) VALUES (?, ?, ?, 'user', ?, 'pending', NULL, ?, ?)
                """,
                (message_id, conversation_id, position, content, now, now),
            )
        return message_id

    def completed_history_before(
        self, conversation_id: str, user_message_id: str
    ) -> tuple[list[dict[str, str]], str]:
        history, question, _memories = self.generation_context_before(
            conversation_id, user_message_id
        )
        return history, question

    def generation_context_before(
        self, conversation_id: str, user_message_id: str
    ) -> tuple[list[dict[str, str]], str, list[str]]:
        with self.connection() as connection:
            connection.execute("BEGIN")
            try:
                current = self._message_row(
                    connection, conversation_id, user_message_id
                )
                if (
                    str(current["role"]) != "user"
                    or str(current["kind"]) != "conversation"
                ):
                    raise ConversationOperationError(
                        "La génération doit partir d’un message utilisateur normal."
                    )
                rows = connection.execute(
                    """
                    SELECT role, content FROM messages
                    WHERE conversation_id = ? AND position < ?
                      AND status = 'completed' AND kind = 'conversation'
                    ORDER BY position ASC
                    """,
                    (conversation_id, int(current["position"])),
                ).fetchall()
                memory_rows = connection.execute(
                    "SELECT content FROM memories ORDER BY created_at ASC, id ASC"
                ).fetchall()
            except BaseException:
                connection.rollback()
                raise
            else:
                connection.commit()
        return (
            [{"role": str(row["role"]), "content": str(row["content"])} for row in rows],
            str(current["content"]),
            [str(row["content"]) for row in memory_rows],
        )

    def regeneration_context_for_assistant(
        self, conversation_id: str, assistant_message_id: str
    ) -> tuple[list[dict[str, str]], str, list[str]]:
        with self.connection() as connection:
            connection.execute("BEGIN")
            try:
                assistant = self._message_row(
                    connection, conversation_id, assistant_message_id
                )
                if (
                    str(assistant["role"]) != "assistant"
                    or str(assistant["kind"]) != "conversation"
                ):
                    raise ConversationOperationError(
                        "La régénération doit cibler une réponse normale de Léa."
                    )
                user = connection.execute(
                    """
                    SELECT * FROM messages
                    WHERE conversation_id = ? AND position = ?
                      AND role = 'user' AND kind = 'conversation'
                    """,
                    (conversation_id, int(assistant["position"]) - 1),
                ).fetchone()
                if user is None:
                    raise ConversationOperationError(
                        "La question associée à cette réponse est introuvable."
                    )
                rows = connection.execute(
                    """
                    SELECT role, content FROM messages
                    WHERE conversation_id = ? AND position < ?
                      AND status = 'completed' AND kind = 'conversation'
                    ORDER BY position ASC
                    """,
                    (conversation_id, int(user["position"])),
                ).fetchall()
                memory_rows = connection.execute(
                    "SELECT content FROM memories ORDER BY created_at ASC, id ASC"
                ).fetchall()
            except BaseException:
                connection.rollback()
                raise
            else:
                connection.commit()
        return (
            [{"role": str(row["role"]), "content": str(row["content"])} for row in rows],
            str(user["content"]),
            [str(row["content"]) for row in memory_rows],
        )

    def complete_generation(
        self, conversation_id: str, user_message_id: str, answer: str
    ) -> None:
        assistant_id = str(uuid.uuid4())
        now = utc_now()
        with self.transaction() as connection:
            conversation = self._conversation_row(connection, conversation_id)
            user_message = self._message_row(connection, conversation_id, user_message_id)
            if not bool(conversation["generation_active"]):
                raise ConversationOperationError("La génération n’est plus active.")
            if (
                str(user_message["role"]) != "user"
                or str(user_message["kind"]) != "conversation"
                or str(user_message["status"]) != "pending"
            ):
                raise ConversationOperationError("La question n’est plus en attente.")
            assistant_position = int(user_message["position"]) + 1
            connection.execute(
                """
                INSERT INTO messages(
                    id, conversation_id, position, role, content, status,
                    error_code, created_at, updated_at
                ) VALUES (?, ?, ?, 'assistant', ?, 'completed', NULL, ?, ?)
                """,
                (assistant_id, conversation_id, assistant_position, answer, now, now),
            )
            connection.execute(
                """
                UPDATE messages
                SET status = 'completed', error_code = NULL, updated_at = ?
                WHERE id = ?
                """,
                (now, user_message_id),
            )
            connection.execute(
                """
                UPDATE conversations
                SET generation_active = 0, revision = revision + 1, updated_at = ?
                WHERE id = ?
                """,
                (now, conversation_id),
            )

    def fail_generation(
        self, conversation_id: str, user_message_id: str, error_code: str
    ) -> None:
        now = utc_now()
        with self.transaction() as connection:
            conversation = self._conversation_row(connection, conversation_id)
            user_message = self._message_row(connection, conversation_id, user_message_id)
            if (
                str(user_message["role"]) != "user"
                or str(user_message["kind"]) != "conversation"
            ):
                raise ConversationOperationError("Le message en échec n’est pas une question.")
            if str(user_message["status"]) == "pending":
                connection.execute(
                    """
                    UPDATE messages
                    SET status = 'failed', error_code = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (error_code, now, user_message_id),
                )
            if bool(conversation["generation_active"]):
                connection.execute(
                    """
                    UPDATE conversations
                    SET generation_active = 0, revision = revision + 1, updated_at = ?
                    WHERE id = ?
                    """,
                    (now, conversation_id),
                )

    def rename_conversation(
        self, conversation_id: str, title: str, expected_revision: int
    ) -> None:
        now = utc_now()
        with self.transaction() as connection:
            conversation = self._conversation_row(connection, conversation_id)
            self._assert_mutation_allowed(conversation, expected_revision)
            connection.execute(
                """
                UPDATE conversations
                SET title = ?, title_origin = 'manual', revision = revision + 1, updated_at = ?
                WHERE id = ?
                """,
                (title, now, conversation_id),
            )

    def delete_conversation(self, conversation_id: str, expected_revision: int) -> None:
        # La conversation et ses messages disparaissent par cascade. Les faits
        # de mémoire sont globaux : seule une commande « Oublie que » les retire.
        with self.transaction() as connection:
            conversation = self._conversation_row(connection, conversation_id)
            self._assert_mutation_allowed(conversation, expected_revision)
            connection.execute("DELETE FROM conversations WHERE id = ?", (conversation_id,))

    def retry_message(
        self, conversation_id: str, message_id: str, expected_revision: int
    ) -> str:
        now = utc_now()
        with self.transaction() as connection:
            conversation = self._conversation_row(connection, conversation_id)
            self._assert_mutation_allowed(conversation, expected_revision)
            message = self._message_row(connection, conversation_id, message_id)
            if (
                str(message["kind"]) != "conversation"
                or str(message["role"]) != "user"
                or str(message["status"]) != "failed"
            ):
                raise ConversationOperationError(
                    "Seule une question en échec peut être réessayée."
                )
            try:
                command = parse_memory_command(str(message["content"]))
            except EmptyMemoryCommandError:
                command = True
            if command is not None:
                raise ConversationOperationError(
                    "Une commande mémoire doit être envoyée comme nouveau message."
                )
            later_count = int(
                connection.execute(
                    """
                    SELECT COUNT(*) FROM messages
                    WHERE conversation_id = ? AND position > ?
                    """,
                    (conversation_id, int(message["position"])),
                ).fetchone()[0]
            )
            if later_count:
                raise ConversationOperationError(
                    "Cette question n’est pas la dernière question réessayable."
                )
            connection.execute(
                """
                UPDATE messages
                SET status = 'pending', error_code = NULL, updated_at = ?
                WHERE id = ?
                """,
                (now, message_id),
            )
            connection.execute(
                """
                UPDATE conversations
                SET generation_active = 1, revision = revision + 1, updated_at = ?
                WHERE id = ?
                """,
                (now, conversation_id),
            )
        return message_id

    def edit_user_message(
        self,
        conversation_id: str,
        message_id: str,
        content: str,
        expected_revision: int,
    ) -> str:
        now = utc_now()
        with self.transaction() as connection:
            conversation = self._conversation_row(connection, conversation_id)
            self._assert_mutation_allowed(conversation, expected_revision)
            message = self._message_row(connection, conversation_id, message_id)
            if str(message["kind"]) != "conversation":
                raise ConversationOperationError(
                    "Un tour de gestion de la mémoire ne peut pas être modifié."
                )
            if str(message["role"]) != "user":
                raise ConversationOperationError(
                    "Seul un message utilisateur peut être modifié."
                )
            try:
                command = parse_memory_command(content)
            except EmptyMemoryCommandError:
                command = True
            if command is not None:
                raise ConversationOperationError(
                    "Une commande mémoire doit être envoyée comme nouveau message."
                )
            position = int(message["position"])
            connection.execute(
                "DELETE FROM messages WHERE conversation_id = ? AND position > ?",
                (conversation_id, position),
            )
            connection.execute(
                """
                UPDATE messages
                SET content = ?, status = 'pending', error_code = NULL, updated_at = ?
                WHERE id = ?
                """,
                (content, now, message_id),
            )
            title = str(conversation["title"])
            if position == 1 and str(conversation["title_origin"]) == "automatic":
                title = automatic_title(content)
            connection.execute(
                """
                UPDATE conversations
                SET title = ?, generation_active = 1,
                    revision = revision + 1, updated_at = ?
                WHERE id = ?
                """,
                (title, now, conversation_id),
            )
        return message_id

    def regenerate_assistant_message(
        self, conversation_id: str, message_id: str, expected_revision: int
    ) -> str:
        now = utc_now()
        with self.transaction() as connection:
            conversation = self._conversation_row(connection, conversation_id)
            self._assert_mutation_allowed(conversation, expected_revision)
            assistant = self._message_row(connection, conversation_id, message_id)
            if str(assistant["kind"]) != "conversation":
                raise ConversationOperationError(
                    "Un tour de gestion de la mémoire ne peut pas être régénéré."
                )
            if str(assistant["role"]) != "assistant":
                raise ConversationOperationError(
                    "Seule une réponse de Léa peut être régénérée."
                )
            assistant_position = int(assistant["position"])
            user = connection.execute(
                """
                SELECT * FROM messages
                WHERE conversation_id = ? AND position = ? AND role = 'user'
                """,
                (conversation_id, assistant_position - 1),
            ).fetchone()
            if user is None:
                raise ConversationOperationError(
                    "La question associée à cette réponse est introuvable."
                )
            if str(user["kind"]) != "conversation":
                raise ConversationOperationError(
                    "Un tour de gestion de la mémoire ne peut pas être régénéré."
                )
            try:
                command = parse_memory_command(str(user["content"]))
            except EmptyMemoryCommandError:
                command = True
            if command is not None:
                raise ConversationOperationError(
                    "Une commande mémoire ne peut pas être régénérée."
                )
            connection.execute(
                "DELETE FROM messages WHERE conversation_id = ? AND position >= ?",
                (conversation_id, assistant_position),
            )
            connection.execute(
                """
                UPDATE messages
                SET status = 'pending', error_code = NULL, updated_at = ?
                WHERE id = ?
                """,
                (now, str(user["id"])),
            )
            connection.execute(
                """
                UPDATE conversations
                SET generation_active = 1, revision = revision + 1, updated_at = ?
                WHERE id = ?
                """,
                (now, conversation_id),
            )
        return str(user["id"])

    def count_messages(self, conversation_id: str) -> int:
        with self.connection() as connection:
            return int(
                connection.execute(
                    "SELECT COUNT(*) FROM messages WHERE conversation_id = ?",
                    (conversation_id,),
                ).fetchone()[0]
            )
