"""
SecureData Central -- migrations versionadas.

Cada entrada de MIGRATIONS e (versao_int, nome, sql). Aplicadas em ordem,
uma unica vez, registradas em schema_migrations. Adicionar uma migration
= adicionar uma tupla no fim da lista; NUNCA editar/reordenar as antigas
(um banco em producao ja aplicou -- editar quebraria a idempotencia).
"""
from __future__ import annotations

import sqlite3

MIGRATIONS: list[tuple[int, str, str]] = [
    (
        1,
        "core_schema",
        """
        CREATE TABLE IF NOT EXISTS memories (
            id          TEXT PRIMARY KEY,
            key         TEXT NOT NULL,
            content     TEXT NOT NULL,
            type        TEXT NOT NULL DEFAULT 'note',
            source      TEXT NOT NULL DEFAULT 'agent',
            importance  TEXT NOT NULL DEFAULT 'medium',
            project     TEXT NOT NULL DEFAULT '',
            status      TEXT NOT NULL DEFAULT 'active',
            version     INTEGER NOT NULL DEFAULT 1,
            supersedes  TEXT,
            created_at  REAL NOT NULL,
            updated_at  REAL NOT NULL,
            metadata    TEXT NOT NULL DEFAULT '{}'
        );
        CREATE INDEX IF NOT EXISTS idx_mem_key      ON memories(key);
        CREATE INDEX IF NOT EXISTS idx_mem_status   ON memories(status);
        CREATE INDEX IF NOT EXISTS idx_mem_project  ON memories(project);
        CREATE INDEX IF NOT EXISTS idx_mem_updated  ON memories(updated_at);

        CREATE TABLE IF NOT EXISTS world_state (
            id           TEXT PRIMARY KEY,
            entity_type  TEXT NOT NULL,
            entity_id    TEXT NOT NULL,
            attribute    TEXT NOT NULL,
            value        TEXT NOT NULL,
            version      INTEGER NOT NULL DEFAULT 1,
            valid_from   REAL NOT NULL,
            valid_until  REAL,
            source       TEXT NOT NULL DEFAULT 'agent',
            updated_at   REAL NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_world_entity  ON world_state(entity_type, entity_id);
        CREATE INDEX IF NOT EXISTS idx_world_attr    ON world_state(entity_type, entity_id, attribute);
        CREATE INDEX IF NOT EXISTS idx_world_current ON world_state(entity_type, entity_id, attribute, valid_until);

        CREATE TABLE IF NOT EXISTS context_refs (
            id          TEXT PRIMARY KEY,
            session_id  TEXT NOT NULL,
            memory_id   TEXT NOT NULL,
            relevance   REAL NOT NULL DEFAULT 0,
            created_at  REAL NOT NULL,
            metadata    TEXT NOT NULL DEFAULT '{}'
        );
        CREATE INDEX IF NOT EXISTS idx_ctx_session ON context_refs(session_id);

        CREATE TABLE IF NOT EXISTS events (
            id          TEXT PRIMARY KEY,
            event_type  TEXT NOT NULL,
            entity_id   TEXT NOT NULL DEFAULT '',
            payload     TEXT NOT NULL DEFAULT '{}',
            project     TEXT NOT NULL DEFAULT '',
            source      TEXT NOT NULL DEFAULT 'agent',
            timestamp   REAL NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_evt_type    ON events(event_type);
        CREATE INDEX IF NOT EXISTS idx_evt_entity  ON events(entity_id);
        CREATE INDEX IF NOT EXISTS idx_evt_time    ON events(timestamp);
        CREATE INDEX IF NOT EXISTS idx_evt_project ON events(project);
        """,
    ),
    (
        2,
        "memories_unique_active_key",
        # Garante 1 memoria ACTIVE por (key, project) -- a recencia e feita
        # por supersede, entao nao pode haver duas ativas na mesma chave.
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_mem_active_key
            ON memories(key, project) WHERE status = 'active';
        """,
    ),
]


def _ensure_migrations_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version    INTEGER PRIMARY KEY,
            name       TEXT NOT NULL,
            applied_at REAL NOT NULL DEFAULT (strftime('%s','now'))
        )
        """
    )


def run_migrations(conn: sqlite3.Connection) -> list[int]:
    """Aplica as migrations pendentes em ordem. Retorna a lista de versoes
    aplicadas NESTA chamada (vazia se o banco ja estava atualizado)."""
    _ensure_migrations_table(conn)
    done = {row[0] for row in conn.execute("SELECT version FROM schema_migrations").fetchall()}
    applied_now: list[int] = []

    for version, name, sql in sorted(MIGRATIONS, key=lambda m: m[0]):
        if version in done:
            continue
        conn.executescript(sql)
        conn.execute(
            "INSERT INTO schema_migrations (version, name, applied_at) VALUES (?, ?, strftime('%s','now'))",
            (version, name),
        )
        conn.commit()
        applied_now.append(version)

    return applied_now


def current_version(conn: sqlite3.Connection) -> int:
    _ensure_migrations_table(conn)
    row = conn.execute("SELECT MAX(version) FROM schema_migrations").fetchone()
    return int(row[0]) if row and row[0] is not None else 0
