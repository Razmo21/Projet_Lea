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
    """Signale qu'une conversation demandée n'existe plus."""


class MessageNotFoundError(LookupError):
    """Signale qu'un message demandé n'existe pas dans la conversation."""


class RevisionConflictError(RuntimeError):
    """Protège une conversation contre une écriture fondée sur une ancienne révision."""


class GenerationConflictError(RuntimeError):
    """Signale qu'une génération concurrente utilise déjà la conversation."""


class ConversationOperationError(RuntimeError):
    """Signale une opération incompatible avec l'état courant d'une conversation."""


class ProjectNotFoundError(LookupError):
    """Signale un identifiant absent du registre local de projets."""


class AgentRunNotFoundError(LookupError):
    """Signale un run agentique absent de la persistance locale."""


class CheckpointNotFoundError(LookupError):
    """Signale un checkpoint absent de la persistance locale."""


class CheckpointStateError(RuntimeError):
    """Signale une transition de checkpoint incompatible avec son état courant."""


AGENT_RUN_STATES = frozenset(
    {
        "pending",
        "running",
        "waiting_for_tool",
        "completed",
        "failed",
        "cancelled",
        "limit_reached",
    }
)
FINAL_AGENT_RUN_STATES = frozenset({"completed", "failed", "cancelled", "limit_reached"})
AGENT_RUN_VALIDATION_STATUSES = frozenset(
    {"pending", "validated", "unverified", "not_requested", "failed"}
)
CHECKPOINT_STATES = frozenset(
    {"ready", "completed", "accepted", "rolled_back", "conflict", "failed"}
)
_UNSET = object()


def utc_now() -> str:
    """Retourne un horodatage UTC stable pour les lignes persistées."""

    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def normalize_spaces(value: str) -> str:
    """Réduit les espaces successifs sans modifier les autres caractères."""

    return " ".join(value.split())


def automatic_title(first_message: str) -> str:
    """Construit un titre court et lisible à partir du premier message."""

    normalized = normalize_spaces(first_message)
    if len(normalized) <= AUTOMATIC_TITLE_LENGTH:
        return normalized
    return normalized[: AUTOMATIC_TITLE_LENGTH - 1].rstrip() + "…"


def resolve_database_path(path: str | Path | None = None) -> Path:
    """Résout la base configurée relativement à la racine du projet si nécessaire."""

    configured = str(path) if path is not None else os.environ.get("LEA_DB_PATH", "")
    if not configured.strip():
        return DEFAULT_DATABASE_PATH

    candidate = Path(configured)
    return candidate if candidate.is_absolute() else PROJECT_ROOT / candidate


def canonical_uuid(value: object, label: str) -> str:
    """Normalise un UUID externe avant toute requête SQLite ou chemin dérivé."""

    try:
        return str(uuid.UUID(str(value)))
    except (ValueError, TypeError, AttributeError) as error:
        raise ValueError(f"{label} invalide.") from error


def _bounded_text(value: object, label: str, maximum: int, *, optional: bool = False) -> str | None:
    """Refuse NUL, vide et texte démesuré dans les métadonnées persistées."""

    if value is None and optional:
        return None
    if not isinstance(value, str):
        raise ValueError(f"{label} invalide.")
    normalized = value.strip()
    if not normalized or "\x00" in normalized or len(normalized) > maximum:
        raise ValueError(f"{label} invalide.")
    return normalized


class Database:
    """Autorité SQLite des conversations, messages et souvenirs de Léa."""

    # Connexions courtes : WAL autorise les lectures pendant une écriture.
    def __init__(self, path: str | Path | None = None) -> None:
        """Mémorise le chemin sans ouvrir prématurément de connexion SQLite."""

        self.path = resolve_database_path(path)

    def _connect(self) -> sqlite3.Connection:
        """Ouvre une connexion courte avec les garanties SQLite communes."""

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
        """Ferme toujours la connexion prêtée au bloc appelant."""

        connection = self._connect()
        try:
            yield connection
        finally:
            connection.close()

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        """Valide entièrement une écriture ou l'annule au premier échec."""

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
        """Reject a database whose required constraints or stage migrations are incomplete."""

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
            "projects": "table",
            "idx_projects_single_active": "index",
            "idx_projects_name": "index",
            "agent_runs": "table",
            "idx_agent_runs_project_created": "index",
            "idx_agent_runs_conversation_created": "index",
            "idx_agent_runs_validation_created": "index",
            "project_checkpoints": "table",
            "idx_project_checkpoints_project_created": "index",
            "idx_project_checkpoints_state_created": "index",
            "checkpoint_files": "table",
            "idx_checkpoint_files_checkpoint_path": "index",
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
        if "model_id" not in message_columns or "profile_id" not in message_columns:
            raise RuntimeError("L’identité du modèle des messages SQLite est absente.")
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
        project_columns = {
            str(row[1]): row
            for row in connection.execute("PRAGMA table_info(projects)").fetchall()
        }
        if set(project_columns) != {
            "id",
            "name",
            "relative_path",
            "created_at",
            "updated_at",
            "active",
        } or any(
            int(project_columns[name][3]) != 1
            for name in ("name", "relative_path", "created_at", "updated_at", "active")
        ):
            raise RuntimeError("Le registre SQLite des projets est incohérent.")
        project_indexes = {
            str(row[1]): bool(row[2])
            for row in connection.execute("PRAGMA index_list(projects)").fetchall()
        }
        if project_indexes.get("idx_projects_single_active") is not True:
            raise RuntimeError("L'unicité du projet actif est absente.")
        agent_run_columns = {
            str(row[1]): row
            for row in connection.execute("PRAGMA table_info(agent_runs)").fetchall()
        }
        if set(agent_run_columns) != {
            "run_id",
            "conversation_id",
            "project_id",
            "profile_id",
            "openhands_session_id",
            "task",
            "state",
            "started_at",
            "finished_at",
            "result_summary",
            "validation_status",
            "checkpoint_id",
            "created_at",
            "updated_at",
        } or any(
            int(agent_run_columns[name][3]) != 1
            # SQLite exposes `TEXT PRIMARY KEY` as nullable in PRAGMA even
            # though this application canonicalises every run UUID itself.
            # Do not reject a valid migrated v6 database on that SQLite quirk.
            for name in (
                "project_id",
                "profile_id",
                "task",
                "state",
                "validation_status",
                "created_at",
                "updated_at",
            )
        ):
            raise RuntimeError("Le stockage SQLite des runs agentiques est incohérent.")
        checkpoint_columns = {
            str(row[1]): row
            for row in connection.execute("PRAGMA table_info(project_checkpoints)").fetchall()
        }
        if set(checkpoint_columns) != {
            "checkpoint_id",
            "run_id",
            "project_id",
            "project_relative_path",
            "project_identity",
            "storage_key",
            "state",
            "created_at",
            "completed_at",
            "accepted_at",
            "rolled_back_at",
            "conflict_at",
            "error",
        } or any(
            int(checkpoint_columns[name][3]) != 1
            for name in (
                "run_id",
                "project_id",
                "project_relative_path",
                "project_identity",
                "storage_key",
                "state",
                "created_at",
            )
        ):
            raise RuntimeError("Le stockage SQLite des checkpoints est incohérent.")
        checkpoint_file_columns = {
            str(row[1]): row
            for row in connection.execute("PRAGMA table_info(checkpoint_files)").fetchall()
        }
        if set(checkpoint_file_columns) != {
            "checkpoint_id",
            "relative_path",
            "entry_type",
            "before_exists",
            "before_sha256",
            "before_size",
            "before_modified_ns",
            "backup_name",
            "after_exists",
            "after_entry_type",
            "after_sha256",
            "after_size",
            "after_modified_ns",
        } or any(
            int(checkpoint_file_columns[name][3]) != 1
            for name in ("checkpoint_id", "relative_path", "entry_type", "before_exists")
        ):
            raise RuntimeError("L'inventaire SQLite des checkpoints est incohérent.")
        quick_check = connection.execute("PRAGMA quick_check").fetchone()
        if quick_check is None or str(quick_check[0]).lower() != "ok":
            raise RuntimeError("Le contrôle d’intégrité SQLite a échoué.")
        if connection.execute("PRAGMA foreign_key_check").fetchone() is not None:
            raise RuntimeError("Une violation de clé étrangère existe dans SQLite.")

    def pragmas(self) -> dict[str, Any]:
        """Expose les réglages SQLite utiles aux diagnostics locaux."""

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
        """Transforme les générations laissées en attente par un arrêt en échecs rejouables."""

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
        """Convertit une ligne conversation en résumé public typé."""

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
        """Convertit une ligne message en dictionnaire public stable."""

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
            "model_id": str(row["model_id"]) if row["model_id"] is not None else None,
            "profile_id": str(row["profile_id"]) if row["profile_id"] is not None else None,
        }

    @staticmethod
    def _memory_from_row(row: sqlite3.Row) -> dict[str, str]:
        """Convertit une ligne mémoire sans exposer de détail SQLite."""

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
        """Charge une conversation ou produit l'erreur métier commune."""

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
        """Charge un message en vérifiant qu'il appartient à la conversation."""

        row = connection.execute(
            "SELECT * FROM messages WHERE id = ? AND conversation_id = ?",
            (message_id, conversation_id),
        ).fetchone()
        if row is None:
            raise MessageNotFoundError("Message introuvable dans cette conversation.")
        return row

    @staticmethod
    def _assert_mutation_allowed(row: sqlite3.Row, expected_revision: int) -> None:
        """Refuse les écritures périmées ou concurrentes avant toute mutation."""

        if int(row["revision"]) != expected_revision:
            raise RevisionConflictError(
                "La conversation a changé dans une autre fenêtre. Son état actuel a été rechargé."
            )
        if bool(row["generation_active"]):
            raise GenerationConflictError(
                "Une génération est déjà active pour cette conversation."
            )

    def list_conversations(self, search: str = "") -> list[dict[str, Any]]:
        """Liste les conversations, éventuellement filtrées par titre ou contenu."""

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
        """Lit un détail de conversation et ses messages dans le même snapshot."""

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
        """Retourne les souvenirs explicites dans leur ordre de création."""

        # Cette liste est l'unique mémoire générale injectée au modèle.
        with self.connection() as connection:
            rows = connection.execute(
                "SELECT * FROM memories ORDER BY created_at ASC, id ASC"
            ).fetchall()
        return [self._memory_from_row(row) for row in rows]

    def list_projects(self) -> list[dict[str, Any]]:
        """Retourne uniquement les métadonnées relatives du registre de projets."""

        with self.connection() as connection:
            rows = connection.execute(
                """
                SELECT id, name, relative_path, created_at, updated_at, active
                FROM projects
                ORDER BY name COLLATE NOCASE ASC, id ASC
                """
            ).fetchall()
        return [{**dict(row), "active": bool(row["active"])} for row in rows]

    def sync_projects(self, projects: list[tuple[str, str]]) -> list[dict[str, Any]]:
        """Synchronise atomiquement les dossiers déjà validés par WorkspaceGuard."""

        now = utc_now()
        with self.transaction() as connection:
            retained_ids: list[str] = []
            for name, relative_path in projects:
                existing = connection.execute(
                    "SELECT id, name, relative_path FROM projects WHERE relative_path = ? COLLATE NOCASE",
                    (relative_path,),
                ).fetchone()
                if existing is None:
                    project_id = str(uuid.uuid4())
                    connection.execute(
                        """
                        INSERT INTO projects(
                            id, name, relative_path, created_at, updated_at, active
                        ) VALUES (?, ?, ?, ?, ?, 0)
                        """,
                        (project_id, name, relative_path, now, now),
                    )
                else:
                    project_id = str(existing["id"])
                    if str(existing["name"]) != name or str(existing["relative_path"]) != relative_path:
                        connection.execute(
                            "UPDATE projects SET name = ?, relative_path = ?, updated_at = ? WHERE id = ?",
                            (name, relative_path, now, project_id),
                        )
                retained_ids.append(project_id)

            if retained_ids:
                placeholders = ",".join("?" for _ in retained_ids)
                connection.execute(
                    f"DELETE FROM projects WHERE id NOT IN ({placeholders})",
                    tuple(retained_ids),
                )
            else:
                connection.execute("DELETE FROM projects")
        return self.list_projects()

    def activate_project(self, project_id: str) -> dict[str, Any]:
        """Sélectionne exactement un projet connu dans une transaction sérialisée."""

        with self.transaction() as connection:
            project = connection.execute(
                "SELECT id FROM projects WHERE id = ?",
                (project_id,),
            ).fetchone()
            if project is None:
                raise ProjectNotFoundError("Le projet demandé n'existe plus.")
            connection.execute("UPDATE projects SET active = 0 WHERE active = 1")
            connection.execute(
                "UPDATE projects SET active = 1, updated_at = ? WHERE id = ?",
                (utc_now(), project_id),
            )
        return next(project for project in self.list_projects() if project["id"] == project_id)

    def get_active_project(self) -> dict[str, Any] | None:
        """Retourne l'unique projet actif ou None sans construire son chemin absolu."""

        with self.connection() as connection:
            row = connection.execute(
                """
                SELECT id, name, relative_path, created_at, updated_at, active
                FROM projects WHERE active = 1
                """
            ).fetchone()
        return None if row is None else {**dict(row), "active": True}

    def get_project(self, project_id: str) -> dict[str, Any]:
        """Retourne un projet persisté par UUID sans fabriquer de chemin absolu."""

        canonical_id = canonical_uuid(project_id, "Identifiant de projet")
        with self.connection() as connection:
            row = connection.execute(
                """
                SELECT id, name, relative_path, created_at, updated_at, active
                FROM projects WHERE id = ?
                """,
                (canonical_id,),
            ).fetchone()
        if row is None:
            raise ProjectNotFoundError("Le projet demandé n'existe plus.")
        return {**dict(row), "active": bool(row["active"])}

    @staticmethod
    def _agent_run_from_row(row: sqlite3.Row) -> dict[str, Any]:
        """Convertit une ligne de run sans exposer d'état SQLite implicite."""

        validation_status = str(row["validation_status"])
        # Historical rows and technically stopped runs may contain old model
        # prose or tool-shaped JSON.  They remain auditable in SQLite but never
        # become a browser-facing final response unless current structured
        # FinishTool evidence validated the run.
        result_summary = (
            str(row["result_summary"])
            if validation_status == "validated" and row["result_summary"] is not None
            else None
        )
        return {
            "run_id": str(row["run_id"]),
            "conversation_id": str(row["conversation_id"]) if row["conversation_id"] is not None else None,
            "project_id": str(row["project_id"]),
            "profile_id": str(row["profile_id"]),
            "openhands_session_id": (
                str(row["openhands_session_id"])
                if row["openhands_session_id"] is not None
                else None
            ),
            "task": str(row["task"]),
            "state": str(row["state"]),
            "started_at": str(row["started_at"]) if row["started_at"] is not None else None,
            "finished_at": str(row["finished_at"]) if row["finished_at"] is not None else None,
            "result_summary": result_summary,
            "validation_status": validation_status,
            "checkpoint_id": str(row["checkpoint_id"]) if row["checkpoint_id"] is not None else None,
            "created_at": str(row["created_at"]),
            "updated_at": str(row["updated_at"]),
        }

    @staticmethod
    def _checkpoint_from_row(row: sqlite3.Row) -> dict[str, Any]:
        """Convertit les métadonnées d'un checkpoint sans révéler son chemin de stockage."""

        result = {
            "checkpoint_id": str(row["checkpoint_id"]),
            "run_id": str(row["run_id"]),
            "project_id": str(row["project_id"]),
            "project_relative_path": str(row["project_relative_path"]),
            "project_identity": str(row["project_identity"]),
            "state": str(row["state"]),
            "created_at": str(row["created_at"]),
            "completed_at": str(row["completed_at"]) if row["completed_at"] is not None else None,
            "accepted_at": str(row["accepted_at"]) if row["accepted_at"] is not None else None,
            "rolled_back_at": str(row["rolled_back_at"]) if row["rolled_back_at"] is not None else None,
            "conflict_at": str(row["conflict_at"]) if row["conflict_at"] is not None else None,
            "error": str(row["error"]) if row["error"] is not None else None,
        }
        if "file_count" in row.keys():
            result["file_count"] = int(row["file_count"])
        return result

    @staticmethod
    def _checkpoint_file_from_row(row: sqlite3.Row) -> dict[str, Any]:
        """Expose les hashes nécessaires au diff tout en laissant le backup privé au moteur."""

        return {
            "checkpoint_id": str(row["checkpoint_id"]),
            "relative_path": str(row["relative_path"]),
            "entry_type": str(row["entry_type"]),
            "before_exists": bool(row["before_exists"]),
            "before_sha256": str(row["before_sha256"]) if row["before_sha256"] is not None else None,
            "before_size": int(row["before_size"]) if row["before_size"] is not None else None,
            "before_modified_ns": (
                int(row["before_modified_ns"]) if row["before_modified_ns"] is not None else None
            ),
            "backup_name": str(row["backup_name"]) if row["backup_name"] is not None else None,
            "after_exists": bool(row["after_exists"]) if row["after_exists"] is not None else None,
            "after_entry_type": (
                str(row["after_entry_type"]) if row["after_entry_type"] is not None else None
            ),
            "after_sha256": str(row["after_sha256"]) if row["after_sha256"] is not None else None,
            "after_size": int(row["after_size"]) if row["after_size"] is not None else None,
            "after_modified_ns": (
                int(row["after_modified_ns"]) if row["after_modified_ns"] is not None else None
            ),
        }

    @staticmethod
    def _default_agent_run_validation_status(state: str) -> str:
        """Return the fail-closed validation state implied by a lifecycle state."""

        if state in {"pending", "running", "waiting_for_tool"}:
            return "pending"
        if state == "completed":
            return "unverified"
        return "failed"

    @classmethod
    def _agent_run_validation_status(
        cls, state: str, requested: object | None
    ) -> str:
        """Validate that a public success claim matches the immutable run lifecycle."""

        candidate = (
            cls._default_agent_run_validation_status(state)
            if requested is None
            else requested
        )
        if not isinstance(candidate, str) or candidate not in AGENT_RUN_VALIDATION_STATUSES:
            raise ValueError("Statut de validation du run invalide.")
        if state in {"pending", "running", "waiting_for_tool"}:
            if candidate != "pending":
                raise ValueError("Un run actif doit rester en validation en attente.")
        elif state == "completed":
            if candidate not in {"validated", "unverified", "not_requested"}:
                raise ValueError("Un run terminé exige un statut de validation cohérent.")
        elif candidate != "failed":
            raise ValueError("Un run interrompu ou échoué ne peut pas être validé.")
        return candidate

    def create_agent_run(
        self,
        run_id: str,
        project_id: str,
        profile_id: str,
        task: str,
        *,
        conversation_id: str | None = None,
        openhands_session_id: str | None = None,
        state: str = "pending",
        validation_status: str | None = None,
    ) -> dict[str, Any]:
        """Crée un run dont le projet est immuable pour toute sa durée de vie."""

        canonical_run_id = canonical_uuid(run_id, "Identifiant de run")
        canonical_project_id = canonical_uuid(project_id, "Identifiant de projet")
        canonical_conversation_id = (
            canonical_uuid(conversation_id, "Identifiant de conversation")
            if conversation_id is not None
            else None
        )
        normalized_profile = _bounded_text(profile_id, "Profil", 128)
        normalized_task = _bounded_text(task, "Tâche", 16_384)
        normalized_session = _bounded_text(
            openhands_session_id, "Session OpenHands", 512, optional=True
        )
        if state not in AGENT_RUN_STATES:
            raise ValueError("État de run invalide.")
        normalized_validation = self._agent_run_validation_status(
            state, validation_status
        )
        now = utc_now()
        started_at = now if state in {"running", "waiting_for_tool"} else None
        finished_at = now if state in FINAL_AGENT_RUN_STATES else None
        with self.transaction() as connection:
            if canonical_conversation_id is not None:
                conversation = connection.execute(
                    "SELECT id FROM conversations WHERE id = ?", (canonical_conversation_id,)
                ).fetchone()
                if conversation is None:
                    raise ConversationNotFoundError("Conversation introuvable.")
            connection.execute(
                """
                INSERT INTO agent_runs(
                    run_id, conversation_id, project_id, profile_id,
                    openhands_session_id, task, state, started_at, finished_at,
                    result_summary, validation_status, checkpoint_id, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, ?, NULL, ?, ?)
                """,
                (
                    canonical_run_id,
                    canonical_conversation_id,
                    canonical_project_id,
                    normalized_profile,
                    normalized_session,
                    normalized_task,
                    state,
                    started_at,
                    finished_at,
                    normalized_validation,
                    now,
                    now,
                ),
            )
        return self.get_agent_run(canonical_run_id)

    def get_agent_run(self, run_id: str) -> dict[str, Any]:
        """Résout un run exact après canonicalisation de son UUID."""

        canonical_run_id = canonical_uuid(run_id, "Identifiant de run")
        with self.connection() as connection:
            row = connection.execute(
                "SELECT * FROM agent_runs WHERE run_id = ?", (canonical_run_id,)
            ).fetchone()
        if row is None:
            raise AgentRunNotFoundError("Run agent introuvable.")
        return self._agent_run_from_row(row)

    def list_agent_runs(
        self,
        *,
        project_id: str | None = None,
        conversation_id: str | None = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """Liste les runs persistés, sans transcript OpenHands ni contenus de fichiers."""

        if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 100:
            raise ValueError("Limite de runs invalide.")
        conditions: list[str] = []
        values: list[Any] = []
        if project_id is not None:
            conditions.append("project_id = ?")
            values.append(canonical_uuid(project_id, "Identifiant de projet"))
        if conversation_id is not None:
            conditions.append("conversation_id = ?")
            values.append(canonical_uuid(conversation_id, "Identifiant de conversation"))
        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        with self.connection() as connection:
            rows = connection.execute(
                f"""
                SELECT * FROM agent_runs
                {where}
                ORDER BY created_at DESC, run_id DESC
                LIMIT ?
                """,
                (*values, limit),
            ).fetchall()
        return [self._agent_run_from_row(row) for row in rows]

    def list_incomplete_agent_runs(self) -> list[dict[str, Any]]:
        """Return persisted runs that need safe ownership recovery after a backend restart."""

        with self.connection() as connection:
            rows = connection.execute(
                """
                SELECT * FROM agent_runs
                WHERE state IN ('pending', 'running', 'waiting_for_tool')
                ORDER BY created_at ASC, run_id ASC
                """
            ).fetchall()
        return [self._agent_run_from_row(row) for row in rows]

    def update_agent_run(
        self,
        run_id: str,
        *,
        state: str | None = None,
        validation_status: str | None | object = _UNSET,
        openhands_session_id: str | None | object = _UNSET,
        result_summary: str | None | object = _UNSET,
    ) -> dict[str, Any]:
        """Met à jour l'état observable sans jamais accepter un nouveau projet ou une nouvelle tâche."""

        canonical_run_id = canonical_uuid(run_id, "Identifiant de run")
        if state is not None and state not in AGENT_RUN_STATES:
            raise ValueError("État de run invalide.")
        updates: list[str] = []
        values: list[Any] = []
        now = utc_now()
        with self.transaction() as connection:
            row = connection.execute(
                "SELECT * FROM agent_runs WHERE run_id = ?", (canonical_run_id,)
            ).fetchone()
            if row is None:
                raise AgentRunNotFoundError("Run agent introuvable.")
            current_state = str(row["state"])
            next_state = state or current_state
            if current_state in FINAL_AGENT_RUN_STATES and next_state != current_state:
                raise CheckpointStateError("Un run terminé ne peut plus changer d'état.")
            requested_validation = (
                validation_status
                if validation_status is not _UNSET
                else (
                    str(row["validation_status"])
                    if state is None
                    else self._default_agent_run_validation_status(next_state)
                )
            )
            next_validation = self._agent_run_validation_status(
                next_state, requested_validation
            )
            if (
                current_state in FINAL_AGENT_RUN_STATES
                and next_validation != str(row["validation_status"])
            ):
                raise CheckpointStateError(
                    "La validation d'un run terminé est immuable."
                )
            if state is not None:
                updates.append("state = ?")
                values.append(next_state)
                if next_state in {"running", "waiting_for_tool"} and row["started_at"] is None:
                    updates.append("started_at = ?")
                    values.append(now)
                if next_state in FINAL_AGENT_RUN_STATES and row["finished_at"] is None:
                    updates.append("finished_at = ?")
                    values.append(now)
            if validation_status is not _UNSET or state is not None:
                if next_validation != str(row["validation_status"]):
                    updates.append("validation_status = ?")
                    values.append(next_validation)
            if openhands_session_id is not _UNSET:
                updates.append("openhands_session_id = ?")
                values.append(
                    _bounded_text(openhands_session_id, "Session OpenHands", 512, optional=True)
                )
            if result_summary is not _UNSET:
                updates.append("result_summary = ?")
                values.append(
                    _bounded_text(result_summary, "Résumé du run", 100_000, optional=True)
                )
            if updates:
                updates.append("updated_at = ?")
                values.append(now)
                values.append(canonical_run_id)
                connection.execute(
                    f"UPDATE agent_runs SET {', '.join(updates)} WHERE run_id = ?", values
                )
            updated = connection.execute(
                "SELECT * FROM agent_runs WHERE run_id = ?", (canonical_run_id,)
            ).fetchone()
        if updated is None:  # pragma: no cover - la transaction vient de vérifier la ligne.
            raise AgentRunNotFoundError("Run agent introuvable.")
        return self._agent_run_from_row(updated)

    @staticmethod
    def _checkpoint_file_insert_values(
        checkpoint_id: str,
        entry: dict[str, Any],
    ) -> tuple[Any, ...]:
        """Construit une ligne d'inventaire vérifiée avant son insertion atomique."""

        relative_path = _bounded_text(entry.get("relative_path"), "Chemin de checkpoint", 4096)
        entry_type = entry.get("entry_type")
        if entry_type not in {"file", "directory"}:
            raise ValueError("Type d'entrée de checkpoint invalide.")
        before_exists = bool(entry.get("before_exists"))
        before_sha256 = entry.get("before_sha256")
        before_size = entry.get("before_size")
        before_modified_ns = entry.get("before_modified_ns")
        backup_name = entry.get("backup_name")
        if entry_type == "file" and before_exists:
            if (
                not isinstance(before_sha256, str)
                or len(before_sha256) != 64
                or any(character not in "0123456789abcdef" for character in before_sha256)
                or not isinstance(before_size, int)
                or before_size < 0
                or not isinstance(before_modified_ns, int)
                or before_modified_ns < 0
            ):
                raise ValueError("Snapshot de fichier invalide.")
            backup = _bounded_text(backup_name, "Nom de sauvegarde", 256)
        else:
            before_sha256 = None
            before_size = None
            before_modified_ns = None
            backup = None
        return (
            checkpoint_id,
            relative_path,
            entry_type,
            int(before_exists),
            before_sha256,
            before_size,
            before_modified_ns,
            backup,
            None,
            None,
            None,
            None,
            None,
        )

    def create_project_checkpoint(
        self,
        checkpoint_id: str,
        run_id: str,
        project_id: str,
        project_relative_path: str,
        project_identity: str,
        storage_key: str,
        files: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Lie atomiquement un inventaire complet au run déjà créé pour ce projet figé."""

        canonical_checkpoint_id = canonical_uuid(checkpoint_id, "Identifiant de checkpoint")
        canonical_run_id = canonical_uuid(run_id, "Identifiant de run")
        canonical_project_id = canonical_uuid(project_id, "Identifiant de projet")
        canonical_storage_key = canonical_uuid(storage_key, "Clé de stockage")
        relative_path = _bounded_text(project_relative_path, "Chemin relatif de projet", 1024)
        identity = _bounded_text(project_identity, "Identité de projet", 256)
        file_values = [
            self._checkpoint_file_insert_values(canonical_checkpoint_id, entry) for entry in files
        ]
        if len({values[1] for values in file_values}) != len(file_values):
            raise ValueError("Le checkpoint contient des chemins dupliqués.")
        now = utc_now()
        with self.transaction() as connection:
            run = connection.execute(
                "SELECT project_id, checkpoint_id FROM agent_runs WHERE run_id = ?", (canonical_run_id,)
            ).fetchone()
            if run is None:
                raise AgentRunNotFoundError("Run agent introuvable.")
            if str(run["project_id"]) != canonical_project_id:
                raise CheckpointStateError("Le checkpoint ne correspond pas au projet figé du run.")
            if run["checkpoint_id"] is not None:
                raise CheckpointStateError("Ce run possède déjà un checkpoint.")
            connection.execute(
                """
                INSERT INTO project_checkpoints(
                    checkpoint_id, run_id, project_id, project_relative_path,
                    project_identity, storage_key, state, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, 'ready', ?)
                """,
                (
                    canonical_checkpoint_id,
                    canonical_run_id,
                    canonical_project_id,
                    relative_path,
                    identity,
                    canonical_storage_key,
                    now,
                ),
            )
            connection.executemany(
                """
                INSERT INTO checkpoint_files(
                    checkpoint_id, relative_path, entry_type, before_exists,
                    before_sha256, before_size, before_modified_ns, backup_name,
                    after_exists, after_entry_type, after_sha256, after_size,
                    after_modified_ns
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                file_values,
            )
            connection.execute(
                "UPDATE agent_runs SET checkpoint_id = ?, updated_at = ? WHERE run_id = ?",
                (canonical_checkpoint_id, now, canonical_run_id),
            )
        return self.get_project_checkpoint(canonical_checkpoint_id)

    def get_project_checkpoint(self, checkpoint_id: str) -> dict[str, Any]:
        """Retourne l'état d'un checkpoint exact avec son nombre d'entrées inventoriées."""

        canonical_checkpoint_id = canonical_uuid(checkpoint_id, "Identifiant de checkpoint")
        with self.connection() as connection:
            row = connection.execute(
                """
                SELECT c.*, COUNT(f.relative_path) AS file_count
                FROM project_checkpoints AS c
                LEFT JOIN checkpoint_files AS f ON f.checkpoint_id = c.checkpoint_id
                WHERE c.checkpoint_id = ?
                GROUP BY c.checkpoint_id
                """,
                (canonical_checkpoint_id,),
            ).fetchone()
        if row is None:
            raise CheckpointNotFoundError("Checkpoint introuvable.")
        return self._checkpoint_from_row(row)

    def list_project_checkpoints(
        self,
        *,
        run_id: str | None = None,
        project_id: str | None = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """Liste les checkpoints persistés avec leurs seuls métadonnées et compteurs."""

        if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 100:
            raise ValueError("Limite de checkpoints invalide.")
        conditions: list[str] = []
        values: list[Any] = []
        if run_id is not None:
            conditions.append("c.run_id = ?")
            values.append(canonical_uuid(run_id, "Identifiant de run"))
        if project_id is not None:
            conditions.append("c.project_id = ?")
            values.append(canonical_uuid(project_id, "Identifiant de projet"))
        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        with self.connection() as connection:
            rows = connection.execute(
                f"""
                SELECT c.*, COUNT(f.relative_path) AS file_count
                FROM project_checkpoints AS c
                LEFT JOIN checkpoint_files AS f ON f.checkpoint_id = c.checkpoint_id
                {where}
                GROUP BY c.checkpoint_id
                ORDER BY c.created_at DESC, c.checkpoint_id DESC
                LIMIT ?
                """,
                (*values, limit),
            ).fetchall()
        return [self._checkpoint_from_row(row) for row in rows]

    def list_checkpoint_files(self, checkpoint_id: str) -> list[dict[str, Any]]:
        """Retourne l'inventaire hashé ordonné requis pour un diff ou un rollback contrôlé."""

        canonical_checkpoint_id = canonical_uuid(checkpoint_id, "Identifiant de checkpoint")
        with self.connection() as connection:
            exists = connection.execute(
                "SELECT 1 FROM project_checkpoints WHERE checkpoint_id = ?",
                (canonical_checkpoint_id,),
            ).fetchone()
            if exists is None:
                raise CheckpointNotFoundError("Checkpoint introuvable.")
            rows = connection.execute(
                """
                SELECT * FROM checkpoint_files
                WHERE checkpoint_id = ?
                ORDER BY relative_path ASC
                """,
                (canonical_checkpoint_id,),
            ).fetchall()
        return [self._checkpoint_file_from_row(row) for row in rows]

    @staticmethod
    def _after_values(entry: dict[str, Any] | None) -> tuple[Any, ...]:
        """Transforme un état courant en colonnes after_* sans confondre absence et NULL."""

        if entry is None:
            return (0, None, None, None, None)
        entry_type = entry.get("entry_type")
        if entry_type not in {"file", "directory"}:
            raise ValueError("Type d'entrée finale invalide.")
        modified_ns = entry.get("modified_ns")
        if not isinstance(modified_ns, int) or modified_ns < 0:
            raise ValueError("Statut final de checkpoint invalide.")
        if entry_type == "directory":
            return (1, "directory", None, None, modified_ns)
        sha256_value = entry.get("sha256")
        size = entry.get("size")
        if (
            not isinstance(sha256_value, str)
            or len(sha256_value) != 64
            or any(character not in "0123456789abcdef" for character in sha256_value)
            or not isinstance(size, int)
            or size < 0
        ):
            raise ValueError("Hash final de checkpoint invalide.")
        return (1, "file", sha256_value, size, modified_ns)

    def complete_project_checkpoint(
        self,
        checkpoint_id: str,
        after_entries: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Fige l'inventaire après run afin que le rollback détecte toute écriture extérieure."""

        canonical_checkpoint_id = canonical_uuid(checkpoint_id, "Identifiant de checkpoint")
        after_by_path: dict[str, dict[str, Any]] = {}
        for entry in after_entries:
            relative_path = _bounded_text(entry.get("relative_path"), "Chemin final de checkpoint", 4096)
            if relative_path in after_by_path:
                raise ValueError("L'inventaire final contient des chemins dupliqués.")
            after_by_path[relative_path] = {**entry, "relative_path": relative_path}
        now = utc_now()
        with self.transaction() as connection:
            checkpoint = connection.execute(
                "SELECT state FROM project_checkpoints WHERE checkpoint_id = ?",
                (canonical_checkpoint_id,),
            ).fetchone()
            if checkpoint is None:
                raise CheckpointNotFoundError("Checkpoint introuvable.")
            if str(checkpoint["state"]) != "ready":
                raise CheckpointStateError("Seul un checkpoint prêt peut être finalisé.")
            before_rows = connection.execute(
                "SELECT * FROM checkpoint_files WHERE checkpoint_id = ?",
                (canonical_checkpoint_id,),
            ).fetchall()
            known_paths = {str(row["relative_path"]) for row in before_rows}
            for row in before_rows:
                after_values = self._after_values(after_by_path.pop(str(row["relative_path"]), None))
                connection.execute(
                    """
                    UPDATE checkpoint_files
                    SET after_exists = ?, after_entry_type = ?, after_sha256 = ?,
                        after_size = ?, after_modified_ns = ?
                    WHERE checkpoint_id = ? AND relative_path = ?
                    """,
                    (*after_values, canonical_checkpoint_id, str(row["relative_path"])),
                )
            for relative_path in sorted(after_by_path):
                entry = after_by_path[relative_path]
                after_values = self._after_values(entry)
                connection.execute(
                    """
                    INSERT INTO checkpoint_files(
                        checkpoint_id, relative_path, entry_type, before_exists,
                        before_sha256, before_size, before_modified_ns, backup_name,
                        after_exists, after_entry_type, after_sha256, after_size,
                        after_modified_ns
                    ) VALUES (?, ?, ?, 0, NULL, NULL, NULL, NULL, ?, ?, ?, ?, ?)
                    """,
                    (
                        canonical_checkpoint_id,
                        relative_path,
                        str(entry["entry_type"]),
                        *after_values,
                    ),
                )
            connection.execute(
                """
                UPDATE project_checkpoints
                SET state = 'completed', completed_at = ?, error = NULL
                WHERE checkpoint_id = ?
                """,
                (now, canonical_checkpoint_id),
            )
        return self.get_project_checkpoint(canonical_checkpoint_id)

    def transition_project_checkpoint(
        self,
        checkpoint_id: str,
        state: str,
        *,
        expected_states: set[str] | frozenset[str],
        error: str | None = None,
    ) -> dict[str, Any]:
        """Applique une transition explicite et refuse les écrasements d'état terminal."""

        canonical_checkpoint_id = canonical_uuid(checkpoint_id, "Identifiant de checkpoint")
        if state not in CHECKPOINT_STATES or not expected_states <= CHECKPOINT_STATES:
            raise ValueError("Transition de checkpoint invalide.")
        normalized_error = _bounded_text(error, "Erreur de checkpoint", 2_000, optional=True)
        now = utc_now()
        timestamp_column = {
            "accepted": "accepted_at",
            "rolled_back": "rolled_back_at",
            "conflict": "conflict_at",
        }.get(state)
        with self.transaction() as connection:
            row = connection.execute(
                "SELECT state FROM project_checkpoints WHERE checkpoint_id = ?",
                (canonical_checkpoint_id,),
            ).fetchone()
            if row is None:
                raise CheckpointNotFoundError("Checkpoint introuvable.")
            if str(row["state"]) not in expected_states:
                raise CheckpointStateError("Transition de checkpoint refusée par son état courant.")
            assignments = ["state = ?", "error = ?"]
            values: list[Any] = [state, normalized_error]
            if timestamp_column is not None:
                assignments.append(f"{timestamp_column} = ?")
                values.append(now)
            values.append(canonical_checkpoint_id)
            connection.execute(
                f"UPDATE project_checkpoints SET {', '.join(assignments)} WHERE checkpoint_id = ?",
                values,
            )
        return self.get_project_checkpoint(canonical_checkpoint_id)

    def apply_memory_command(
        self,
        command: MemoryCommand,
        original_message: str,
        conversation_id: str | None,
        expected_revision: int | None,
    ) -> str:
        """Applique une commande mémoire et sa confirmation dans une transaction unique."""

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
        """Crée une conversation et sa première question en attente."""

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
        """Ajoute une nouvelle question après contrôle de la révision courante."""

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
        """Retourne l'historique terminé et la question, sans les souvenirs."""

        history, question, _memories = self.generation_context_before(
            conversation_id, user_message_id
        )
        return history, question

    def generation_context_before(
        self, conversation_id: str, user_message_id: str
    ) -> tuple[list[dict[str, str]], str, list[str]]:
        """Lit atomiquement l'historique, la question et les souvenirs d'une génération."""

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
        """Reconstruit le contexte précédant une réponse assistant à régénérer."""

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
        self,
        conversation_id: str,
        user_message_id: str,
        answer: str,
        model_id: str | None = None,
        profile_id: str | None = None,
    ) -> None:
        """Persiste la réponse et clôt atomiquement la question en attente."""

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
                    error_code, created_at, updated_at, model_id, profile_id
                ) VALUES (?, ?, ?, 'assistant', ?, 'completed', NULL, ?, ?, ?, ?)
                """,
                (
                    assistant_id,
                    conversation_id,
                    assistant_position,
                    answer,
                    now,
                    now,
                    model_id,
                    profile_id,
                ),
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
        """Rend une question échouée rejouable et libère la conversation."""

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
        """Remplace le titre après contrôle optimiste de la révision."""

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
        """Supprime une conversation sans effacer les faits de mémoire globaux."""

        # La conversation et ses messages disparaissent par cascade. Les faits
        # de mémoire sont globaux : seule une commande « Oublie que » les retire.
        with self.transaction() as connection:
            conversation = self._conversation_row(connection, conversation_id)
            self._assert_mutation_allowed(conversation, expected_revision)
            connection.execute("DELETE FROM conversations WHERE id = ?", (conversation_id,))

    def retry_message(
        self, conversation_id: str, message_id: str, expected_revision: int
    ) -> str:
        """Replace la dernière question échouée dans l'état attendu par le générateur."""

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
        """Modifie une question et retire atomiquement la suite devenue incohérente."""

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
        """Supprime une réponse et remet sa question associée en attente."""

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
        """Compte les messages persistés d'une conversation."""

        with self.connection() as connection:
            return int(
                connection.execute(
                    "SELECT COUNT(*) FROM messages WHERE conversation_id = ?",
                    (conversation_id,),
                ).fetchone()[0]
            )
