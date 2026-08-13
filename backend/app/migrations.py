from __future__ import annotations

import sqlite3
from collections.abc import Mapping, Sequence


SCHEMA_VERSION = 2

MIGRATIONS: Mapping[int, Sequence[str]] = {
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
}


class MigrationError(RuntimeError):
    """Raised when the local database schema cannot be migrated safely."""


def apply_migrations(
    connection: sqlite3.Connection,
    migrations: Mapping[int, Sequence[str]] = MIGRATIONS,
) -> int:
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
            for statement in migrations[version]:
                connection.execute(statement)
            connection.execute(
                "INSERT INTO schema_migrations(version, applied_at) "
                "VALUES (?, strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))",
                (version,),
            )
            connection.commit()
        except sqlite3.Error as error:
            connection.rollback()
            raise MigrationError(
                f"La migration SQLite {version} a échoué et a été annulée."
            ) from error

    row = connection.execute(
        "SELECT COALESCE(MAX(version), 0) FROM schema_migrations"
    ).fetchone()
    return int(row[0]) if row is not None else 0
