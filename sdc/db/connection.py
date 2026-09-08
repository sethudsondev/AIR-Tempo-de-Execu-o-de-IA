"""
SecureData Central -- conexao SQLite compartilhada.

check_same_thread=False: o servidor MCP despacha tool calls em worker
threads; a conexao e serializada por um Lock proprio (ver Database.lock).
WAL + foreign_keys ligados. Nenhuma query e montada por concatenacao de
string com dado do usuario -- sempre placeholders parametrizados.
"""
from __future__ import annotations

import sqlite3
import threading
from pathlib import Path

from sdc.db.migrations import run_migrations


class Database:
    def __init__(self, db_path: str | Path = ":memory:") -> None:
        self.path = str(db_path)
        self.lock = threading.RLock()
        self.conn = sqlite3.connect(self.path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        if self.path != ":memory:":
            self.conn.execute("PRAGMA journal_mode = WAL")
        self.conn.execute("PRAGMA busy_timeout = 5000")
        self.applied_migrations = run_migrations(self.conn)
        # contador de versao: o indice de busca (context/retrieval) so
        # reconstroi cache quando algo realmente mudou.
        self._version = 0

    def bump(self) -> None:
        self._version += 1

    def version(self) -> int:
        return self._version

    # -- helpers finos, todos parametrizados --------------------------------

    def execute(self, sql: str, params: tuple = ()) -> sqlite3.Cursor:
        with self.lock:
            cur = self.conn.execute(sql, params)
            self.conn.commit()
            return cur

    def query_one(self, sql: str, params: tuple = ()) -> sqlite3.Row | None:
        with self.lock:
            return self.conn.execute(sql, params).fetchone()

    def query_all(self, sql: str, params: tuple = ()) -> list[sqlite3.Row]:
        with self.lock:
            return self.conn.execute(sql, params).fetchall()

    def close(self) -> None:
        with self.lock:
            self.conn.close()
