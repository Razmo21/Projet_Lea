from __future__ import annotations

import sqlite3
from collections.abc import Callable, Mapping, Sequence

from .memory import (
    EmptyMemoryCommandError,
    MEMORY_DUPLICATE_CONFIRMATION,
    MEMORY_REMEMBERED_CONFIRMATION,
    parse_memory_command,
)


MigrationOperation = str | Callable[[sqlite3.Connection], None]
SCHEMA_VERSION = 7


def _backfill_memory_sources(connection: sqlite3.Connection) -> None:
    """Relie les souvenirs v2 aux commandes encore présentes quand c'est possible.

    Le schéma v2 ne mémorisait pas la provenance. Les horodatages et la paire
    commande/confirmation permettent de retrouver les sources encore vivantes.
    La provenance reste informative : un souvenir sans conversation source est
    valide, global, et ne doit surtout pas être effacé par une migration.
    """

    memories = connection.execute(
        "SELECT id, normalized_content, created_at FROM memories"
    ).fetchall()
    for memory_id, normalized_content, memory_created_at in memories:
        candidates = connection.execute(
            """
            SELECT user.conversation_id, user.content, user.created_at
            FROM messages AS user
            JOIN messages AS assistant
              ON assistant.conversation_id = user.conversation_id
             AND assistant.position = user.position + 1
            WHERE user.role = 'user'
              AND user.status = 'completed'
              AND user.kind = 'memory'
              AND assistant.role = 'assistant'
              AND assistant.status = 'completed'
              AND assistant.kind = 'memory'
              AND assistant.content IN (?, ?)
              AND user.created_at >= ?
            ORDER BY user.created_at ASC, user.id ASC
            """,
            (
                MEMORY_REMEMBERED_CONFIRMATION,
                MEMORY_DUPLICATE_CONFIRMATION,
                memory_created_at,
            ),
        ).fetchall()
        for conversation_id, original_message, source_created_at in candidates:
            try:
                command = parse_memory_command(str(original_message))
            except EmptyMemoryCommandError:
                continue
            if (
                command is not None
                and command.action == "remember"
                and command.normalized_content == str(normalized_content)
            ):
                connection.execute(
                    """
                    INSERT OR IGNORE INTO memory_sources(
                        memory_id, conversation_id, created_at
                    ) VALUES (?, ?, ?)
                    """,
                    (memory_id, conversation_id, source_created_at),
                )

MIGRATIONS: Mapping[int, Sequence[MigrationOperation]] = {
    # v1 : conversations persistantes de l'étape 8.
    1: (
        """
        CREATE TABLE conversations (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL CHECK(length(title) BETWEEN 1 AND 100),
            title_origin TEXT NOT NULL CHECK(title_origin IN ('automatic', 'manual')),
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            revision INTEGER NOT NULL DEFAULT 0 CHECK(revision >= 0),
            generation_active INTEGER NOT NULL DEFAULT 0
                CHECK(generation_active IN (0, 1)),
            CHECK(instr(title, char(0)) = 0),
            CHECK(instr(lower(title), '/no_think') = 0),
            CHECK(instr(lower(title), '<think') = 0),
            CHECK(instr(lower(title), '</think') = 0)
        )
        """,
        """
        CREATE TABLE messages (
            id TEXT PRIMARY KEY,
            conversation_id TEXT NOT NULL,
            position INTEGER NOT NULL CHECK(position >= 1),
            role TEXT NOT NULL CHECK(role IN ('user', 'assistant')),
            content TEXT NOT NULL CHECK(length(content) > 0),
            status TEXT NOT NULL CHECK(status IN ('pending', 'completed', 'failed')),
            error_code TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY(conversation_id) REFERENCES conversations(id) ON DELETE CASCADE,
            UNIQUE(conversation_id, position),
            CHECK(instr(content, char(0)) = 0),
            CHECK(instr(lower(content), '/no_think') = 0),
            CHECK(instr(lower(content), '<think') = 0),
            CHECK(instr(lower(content), '</think') = 0),
            CHECK(role = 'user' OR (status = 'completed' AND error_code IS NULL)),
            CHECK(
                (status IN ('pending', 'completed') AND error_code IS NULL)
                OR (status = 'failed' AND error_code IN (
                    'model_unavailable', 'model_error', 'interrupted'
                ))
            )
        )
        """,
        """
        CREATE INDEX idx_conversations_updated_at
        ON conversations(updated_at DESC, id)
        """,
        """
        CREATE INDEX idx_messages_conversation_position
        ON messages(conversation_id, position)
        """,
        """
        CREATE INDEX idx_messages_conversation_status
        ON messages(conversation_id, status)
        """,
    ),
    # v2 : mémoire explicite globale et classification des tours mémoire.
    2: (
        """
        CREATE TABLE conversations_v2 (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL CHECK(length(title) BETWEEN 1 AND 100),
            title_origin TEXT NOT NULL CHECK(title_origin IN ('automatic', 'manual')),
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            revision INTEGER NOT NULL DEFAULT 0 CHECK(revision >= 0),
            generation_active INTEGER NOT NULL DEFAULT 0
                CHECK(generation_active IN (0, 1)),
            CHECK(instr(title, char(0)) = 0),
            CHECK(instr(lower(title), '<think') = 0),
            CHECK(instr(lower(title), '</think') = 0)
        )
        """,
        """
        INSERT INTO conversations_v2(
            id, title, title_origin, created_at, updated_at,
            revision, generation_active
        )
        SELECT
            id, title, title_origin, created_at, updated_at,
            revision, generation_active
        FROM conversations
        """,
        """
        CREATE TABLE messages_v2 (
            id TEXT PRIMARY KEY,
            conversation_id TEXT NOT NULL,
            position INTEGER NOT NULL CHECK(position >= 1),
            role TEXT NOT NULL CHECK(role IN ('user', 'assistant')),
            content TEXT NOT NULL CHECK(length(content) > 0),
            status TEXT NOT NULL CHECK(status IN ('pending', 'completed', 'failed')),
            error_code TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            kind TEXT NOT NULL DEFAULT 'conversation'
                CHECK(kind IN ('conversation', 'memory')),
            FOREIGN KEY(conversation_id) REFERENCES conversations_v2(id) ON DELETE CASCADE,
            UNIQUE(conversation_id, position),
            CHECK(instr(content, char(0)) = 0),
            CHECK(instr(lower(content), '<think') = 0),
            CHECK(instr(lower(content), '</think') = 0),
            CHECK(role = 'user' OR (status = 'completed' AND error_code IS NULL)),
            CHECK(kind = 'conversation' OR (status = 'completed' AND error_code IS NULL)),
            CHECK(
                (status IN ('pending', 'completed') AND error_code IS NULL)
                OR (status = 'failed' AND error_code IN (
                    'model_unavailable', 'model_error', 'interrupted'
                ))
            )
        )
        """,
        """
        INSERT INTO messages_v2(
            id, conversation_id, position, role, content, status,
            error_code, created_at, updated_at, kind
        )
        SELECT
            id, conversation_id, position, role, content, status,
            error_code, created_at, updated_at, 'conversation'
        FROM messages
        """,
        "DROP TABLE messages",
        "DROP TABLE conversations",
        "ALTER TABLE conversations_v2 RENAME TO conversations",
        "ALTER TABLE messages_v2 RENAME TO messages",
        """
        CREATE INDEX idx_conversations_updated_at
        ON conversations(updated_at DESC, id)
        """,
        """
        CREATE INDEX idx_messages_conversation_position
        ON messages(conversation_id, position)
        """,
        """
        CREATE INDEX idx_messages_conversation_status
        ON messages(conversation_id, status)
        """,
        """
        CREATE TABLE memories (
            id TEXT PRIMARY KEY,
            content TEXT NOT NULL CHECK(length(content) > 0),
            normalized_content TEXT NOT NULL CHECK(length(normalized_content) > 0),
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            CHECK(instr(content, char(0)) = 0),
            CHECK(instr(normalized_content, char(0)) = 0)
        )
        """,
        """
        CREATE UNIQUE INDEX idx_memories_normalized_content
        ON memories(normalized_content)
        """,
    ),
    # v3 : provenance informative des commandes explicites encore visibles.
    3: (
        """
        CREATE TABLE memory_sources (
            memory_id TEXT NOT NULL,
            conversation_id TEXT NOT NULL,
            created_at TEXT NOT NULL,
            PRIMARY KEY(memory_id, conversation_id),
            FOREIGN KEY(memory_id) REFERENCES memories(id) ON DELETE CASCADE,
            FOREIGN KEY(conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
        )
        """,
        """
        CREATE INDEX idx_memory_sources_conversation_id
        ON memory_sources(conversation_id, memory_id)
        """,
        _backfill_memory_sources,
    ),
    # v4 : identité nullable du cerveau ayant produit chaque réponse assistant.
    4: (
        "ALTER TABLE messages ADD COLUMN model_id TEXT",
        "ALTER TABLE messages ADD COLUMN profile_id TEXT",
    ),
    # v5 : registre minimal des projets confinés à IA_WORKSPACE.
    5: (
        """
        CREATE TABLE projects (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL CHECK(length(name) BETWEEN 1 AND 255),
            relative_path TEXT NOT NULL COLLATE NOCASE UNIQUE
                CHECK(length(relative_path) BETWEEN 1 AND 1024),
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            active INTEGER NOT NULL DEFAULT 0 CHECK(active IN (0, 1)),
            CHECK(instr(name, char(0)) = 0),
            CHECK(instr(relative_path, char(0)) = 0)
        )
        """,
        """
        CREATE UNIQUE INDEX idx_projects_single_active
        ON projects(active) WHERE active = 1
        """,
        """
        CREATE INDEX idx_projects_name
        ON projects(name COLLATE NOCASE, id)
        """,
    ),
    # v6 : persistance minimale des runs agentiques et de leurs checkpoints.
    # Les contenus de snapshot restent dans le stockage local de checkpoints ;
    # SQLite ne conserve ici que les métadonnées, hashes et états nécessaires
    # pour retrouver, accepter ou restaurer un run après redémarrage.
    6: (
        """
        CREATE TABLE agent_runs (
            run_id TEXT PRIMARY KEY CHECK(length(run_id) = 36),
            conversation_id TEXT,
            project_id TEXT NOT NULL CHECK(length(project_id) = 36),
            profile_id TEXT NOT NULL CHECK(length(profile_id) BETWEEN 1 AND 128),
            openhands_session_id TEXT,
            task TEXT NOT NULL CHECK(length(task) BETWEEN 1 AND 16384),
            state TEXT NOT NULL CHECK(state IN (
                'pending', 'running', 'waiting_for_tool', 'completed',
                'failed', 'cancelled', 'limit_reached'
            )),
            started_at TEXT,
            finished_at TEXT,
            result_summary TEXT,
            checkpoint_id TEXT UNIQUE CHECK(checkpoint_id IS NULL OR length(checkpoint_id) = 36),
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY(conversation_id) REFERENCES conversations(id) ON DELETE SET NULL,
            CHECK(instr(profile_id, char(0)) = 0),
            CHECK(instr(task, char(0)) = 0),
            CHECK(openhands_session_id IS NULL OR instr(openhands_session_id, char(0)) = 0),
            CHECK(result_summary IS NULL OR instr(result_summary, char(0)) = 0)
        )
        """,
        """
        CREATE INDEX idx_agent_runs_project_created
        ON agent_runs(project_id, created_at DESC, run_id)
        """,
        """
        CREATE INDEX idx_agent_runs_conversation_created
        ON agent_runs(conversation_id, created_at DESC, run_id)
        """,
        """
        CREATE TABLE project_checkpoints (
            checkpoint_id TEXT PRIMARY KEY CHECK(length(checkpoint_id) = 36),
            run_id TEXT NOT NULL UNIQUE CHECK(length(run_id) = 36),
            project_id TEXT NOT NULL CHECK(length(project_id) = 36),
            project_relative_path TEXT NOT NULL CHECK(length(project_relative_path) BETWEEN 1 AND 1024),
            project_identity TEXT NOT NULL CHECK(length(project_identity) BETWEEN 3 AND 256),
            storage_key TEXT NOT NULL UNIQUE CHECK(length(storage_key) = 36),
            state TEXT NOT NULL CHECK(state IN (
                'ready', 'completed', 'accepted', 'rolled_back', 'conflict', 'failed'
            )),
            created_at TEXT NOT NULL,
            completed_at TEXT,
            accepted_at TEXT,
            rolled_back_at TEXT,
            conflict_at TEXT,
            error TEXT,
            FOREIGN KEY(run_id) REFERENCES agent_runs(run_id) ON DELETE CASCADE,
            CHECK(instr(project_relative_path, char(0)) = 0),
            CHECK(instr(project_identity, char(0)) = 0),
            CHECK(instr(storage_key, char(0)) = 0),
            CHECK(error IS NULL OR instr(error, char(0)) = 0)
        )
        """,
        """
        CREATE INDEX idx_project_checkpoints_project_created
        ON project_checkpoints(project_id, created_at DESC, checkpoint_id)
        """,
        """
        CREATE INDEX idx_project_checkpoints_state_created
        ON project_checkpoints(state, created_at DESC, checkpoint_id)
        """,
        """
        CREATE TABLE checkpoint_files (
            checkpoint_id TEXT NOT NULL CHECK(length(checkpoint_id) = 36),
            relative_path TEXT NOT NULL CHECK(length(relative_path) BETWEEN 1 AND 4096),
            entry_type TEXT NOT NULL CHECK(entry_type IN ('file', 'directory')),
            before_exists INTEGER NOT NULL CHECK(before_exists IN (0, 1)),
            before_sha256 TEXT,
            before_size INTEGER,
            before_modified_ns INTEGER,
            backup_name TEXT,
            after_exists INTEGER CHECK(after_exists IN (0, 1)),
            after_entry_type TEXT CHECK(after_entry_type IN ('file', 'directory')),
            after_sha256 TEXT,
            after_size INTEGER,
            after_modified_ns INTEGER,
            PRIMARY KEY(checkpoint_id, relative_path),
            FOREIGN KEY(checkpoint_id) REFERENCES project_checkpoints(checkpoint_id) ON DELETE CASCADE,
            CHECK(instr(relative_path, char(0)) = 0),
            CHECK(backup_name IS NULL OR instr(backup_name, char(0)) = 0),
            CHECK(
                (entry_type = 'directory' AND before_sha256 IS NULL AND before_size IS NULL AND backup_name IS NULL)
                OR (entry_type = 'file' AND before_exists = 0 AND before_sha256 IS NULL AND before_size IS NULL AND backup_name IS NULL)
                OR (entry_type = 'file' AND before_exists = 1 AND length(before_sha256) = 64 AND before_size >= 0 AND backup_name IS NOT NULL)
            ),
            CHECK(
                after_exists IS NULL
                OR (after_exists = 0 AND after_entry_type IS NULL AND after_sha256 IS NULL AND after_size IS NULL AND after_modified_ns IS NULL)
                OR (after_exists = 1 AND after_entry_type = 'directory' AND after_sha256 IS NULL AND after_size IS NULL)
                OR (after_exists = 1 AND after_entry_type = 'file' AND length(after_sha256) = 64 AND after_size >= 0)
            )
        )
        """,
        """
        CREATE INDEX idx_checkpoint_files_checkpoint_path
        ON checkpoint_files(checkpoint_id, relative_path)
        """,
    ),
    # v7 : une fin technique OpenHands n'est pas une validation utilisateur.
    # Les lignes historiques v6 sont conservées mais restent explicitement
    # non vérifiées : aucune preuve ne peut être inventée a posteriori.
    7: (
        """
        ALTER TABLE agent_runs
        ADD COLUMN validation_status TEXT NOT NULL DEFAULT 'unverified'
        CHECK(validation_status IN (
            'pending', 'validated', 'unverified', 'not_requested', 'failed'
        ))
        """,
        """
        CREATE INDEX idx_agent_runs_validation_created
        ON agent_runs(validation_status, created_at DESC, run_id)
        """,
    ),
}


class MigrationError(RuntimeError):
    """Raised when the local database schema cannot be migrated safely."""


def apply_migrations(
    connection: sqlite3.Connection,
    migrations: Mapping[int, Sequence[MigrationOperation]] = MIGRATIONS,
) -> int:
    """Applique chaque version une seule fois et annule entièrement celle qui échoue."""

    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version INTEGER PRIMARY KEY CHECK(version >= 1),
            applied_at TEXT NOT NULL
        )
        """
    )

    applied_versions = {
        int(row[0])
        for row in connection.execute(
            "SELECT version FROM schema_migrations ORDER BY version"
        ).fetchall()
    }
    known_versions = set(migrations)
    unknown_versions = applied_versions - known_versions
    if unknown_versions:
        future = ", ".join(str(version) for version in sorted(unknown_versions))
        raise MigrationError(
            f"La base SQLite utilise une version de schéma inconnue ({future})."
        )

    for version in sorted(known_versions):
        if version in applied_versions:
            continue

        try:
            connection.execute("BEGIN IMMEDIATE")
            for operation in migrations[version]:
                if isinstance(operation, str):
                    connection.execute(operation)
                else:
                    operation(connection)
            connection.execute(
                "INSERT INTO schema_migrations(version, applied_at) "
                "VALUES (?, strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))",
                (version,),
            )
            connection.commit()
        except Exception as error:
            connection.rollback()
            raise MigrationError(
                f"La migration SQLite {version} a échoué et a été annulée."
            ) from error

    row = connection.execute(
        "SELECT COALESCE(MAX(version), 0) FROM schema_migrations"
    ).fetchone()
    return int(row[0]) if row is not None else 0
