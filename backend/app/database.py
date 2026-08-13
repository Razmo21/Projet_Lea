from __future__ import annotations

import os
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterator

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
        required_objects = {
            "schema_migrations": "table",
            "conversations": "table",
            "messages": "table",
            "idx_conversations_updated_at": "index",
            "idx_messages_conversation_position": "index",
            "idx_messages_conversation_status": "index",
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
        with self.connection() as connection:
            current = self._message_row(connection, conversation_id, user_message_id)
            if str(current["role"]) != "user":
                raise ConversationOperationError("La génération doit partir d’un message utilisateur.")
            rows = connection.execute(
                """
                SELECT role, content FROM messages
                WHERE conversation_id = ? AND position < ? AND status = 'completed'
                ORDER BY position ASC
                """,
                (conversation_id, int(current["position"])),
            ).fetchall()
        return (
            [{"role": str(row["role"]), "content": str(row["content"])} for row in rows],
            str(current["content"]),
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
            if str(user_message["role"]) != "user" or str(user_message["status"]) != "pending":
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
            if str(user_message["role"]) != "user":
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
            if str(message["role"]) != "user" or str(message["status"]) != "failed":
                raise ConversationOperationError(
                    "Seule une question en échec peut être réessayée."
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
            if str(message["role"]) != "user":
                raise ConversationOperationError(
                    "Seul un message utilisateur peut être modifié."
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
