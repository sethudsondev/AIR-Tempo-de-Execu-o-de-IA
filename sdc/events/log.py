"""
SecureData Central -- Event Log (append-only).

Acontecimentos relevantes: memoria criada/atualizada, estado do mundo
mudou, deploy, etc. Nunca e editado nem apagado -- so recebe append e e
consultado por tipo / entidade / janela de tempo.
"""
from __future__ import annotations

import json

from sdc.core.types import Event, new_id, now
from sdc.db.connection import Database

_COLS = "id, event_type, entity_id, payload, project, source, timestamp"


def _row_to_event(row) -> Event:
    return Event(
        id=row["id"],
        event_type=row["event_type"],
        entity_id=row["entity_id"],
        payload=json.loads(row["payload"] or "{}"),
        project=row["project"],
        source=row["source"],
        timestamp=row["timestamp"],
    )


class EventLog:
    def __init__(self, db: Database) -> None:
        self.db = db

    def record(
        self,
        event_type: str,
        *,
        entity_id: str = "",
        payload: dict | None = None,
        project: str = "",
        source: str = "agent",
    ) -> Event:
        ev = Event(
            id=new_id("evt"),
            event_type=event_type,
            entity_id=entity_id,
            payload=payload or {},
            project=project,
            source=source,
            timestamp=now(),
        )
        with self.db.lock:
            self.db.conn.execute(
                f"INSERT INTO events ({_COLS}) VALUES (?,?,?,?,?,?,?)",
                (
                    ev.id, ev.event_type, ev.entity_id,
                    json.dumps(ev.payload, ensure_ascii=False),
                    ev.project, ev.source, ev.timestamp,
                ),
            )
            self.db.conn.commit()
            self.db.bump()
        return ev

    def recent(
        self,
        *,
        limit: int = 50,
        event_type: str | None = None,
        entity_id: str | None = None,
        project: str | None = None,
        since_ts: float | None = None,
    ) -> list[Event]:
        clauses: list[str] = []
        params: list = []
        if event_type:
            clauses.append("event_type = ?")
            params.append(event_type)
        if entity_id:
            clauses.append("entity_id = ?")
            params.append(entity_id)
        if project is not None:
            clauses.append("(project = ? OR project = '')")
            params.append(project)
        if since_ts is not None:
            clauses.append("timestamp >= ?")
            params.append(since_ts)
        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        params.append(max(1, limit))
        rows = self.db.query_all(
            f"SELECT {_COLS} FROM events {where} ORDER BY timestamp DESC LIMIT ?",
            tuple(params),
        )
        return [_row_to_event(r) for r in rows]

    def count(self) -> int:
        row = self.db.query_one("SELECT COUNT(*) FROM events")
        return int(row[0]) if row else 0
