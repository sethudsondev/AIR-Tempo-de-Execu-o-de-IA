"""
SecureData Central -- World State.

Estado atual de entidades como (entity_type, entity_id, attribute) -> value,
com VERSIONAMENTO TEMPORAL: mudar um valor nao apaga o anterior, fecha ele
(valid_until = agora) e abre uma linha nova (valid_from = agora,
valid_until = NULL). Assim da para responder:
  - qual o estado atual?          -> get()
  - qual era o anterior?          -> previous()
  - quando mudou / qual a origem? -> history()
"""
from __future__ import annotations

from sdc.core.types import WorldFact, new_id, now
from sdc.db.connection import Database

_COLS = "id, entity_type, entity_id, attribute, value, version, valid_from, valid_until, source, updated_at"


def _row_to_fact(row) -> WorldFact:
    return WorldFact(
        id=row["id"],
        entity_type=row["entity_type"],
        entity_id=row["entity_id"],
        attribute=row["attribute"],
        value=row["value"],
        version=row["version"],
        valid_from=row["valid_from"],
        valid_until=row["valid_until"],
        source=row["source"],
        updated_at=row["updated_at"],
    )


class WorldState:
    def __init__(self, db: Database) -> None:
        self.db = db

    # -- escrita ---------------------------------------------------------

    def set(
        self,
        entity_type: str,
        entity_id: str,
        attribute: str,
        value: str,
        *,
        source: str = "agent",
    ) -> tuple[WorldFact, str]:
        """Retorna (fact, outcome) com outcome in {'created','changed','unchanged'}."""
        current = self.get(entity_type, entity_id, attribute)
        if current is not None and current.value == value:
            return current, "unchanged"

        ts = now()
        version = (current.version + 1) if current else 1

        with self.db.lock:
            if current is not None:
                self.db.conn.execute(
                    "UPDATE world_state SET valid_until = ?, updated_at = ? WHERE id = ?",
                    (ts, ts, current.id),
                )
            fact = WorldFact(
                id=new_id("wf"),
                entity_type=entity_type,
                entity_id=entity_id,
                attribute=attribute,
                value=value,
                version=version,
                valid_from=ts,
                valid_until=None,
                source=source,
                updated_at=ts,
            )
            self.db.conn.execute(
                f"INSERT INTO world_state ({_COLS}) VALUES (?,?,?,?,?,?,?,?,?,?)",
                (
                    fact.id, fact.entity_type, fact.entity_id, fact.attribute, fact.value,
                    fact.version, fact.valid_from, fact.valid_until, fact.source, fact.updated_at,
                ),
            )
            self.db.conn.commit()
            self.db.bump()

        return fact, ("changed" if current else "created")

    def set_many(self, entity_type: str, entity_id: str, attrs: dict, *, source: str = "agent") -> list[tuple[WorldFact, str]]:
        return [
            self.set(entity_type, entity_id, str(k), str(v), source=source)
            for k, v in attrs.items()
        ]

    # -- leitura -------------------------------------------------------

    def get(self, entity_type: str, entity_id: str, attribute: str) -> WorldFact | None:
        row = self.db.query_one(
            f"SELECT {_COLS} FROM world_state "
            f"WHERE entity_type = ? AND entity_id = ? AND attribute = ? AND valid_until IS NULL",
            (entity_type, entity_id, attribute),
        )
        return _row_to_fact(row) if row else None

    def previous(self, entity_type: str, entity_id: str, attribute: str) -> WorldFact | None:
        rows = self.db.query_all(
            f"SELECT {_COLS} FROM world_state "
            f"WHERE entity_type = ? AND entity_id = ? AND attribute = ? "
            f"ORDER BY version DESC LIMIT 2",
            (entity_type, entity_id, attribute),
        )
        return _row_to_fact(rows[1]) if len(rows) > 1 else None

    def history(self, entity_type: str, entity_id: str, attribute: str) -> list[WorldFact]:
        rows = self.db.query_all(
            f"SELECT {_COLS} FROM world_state "
            f"WHERE entity_type = ? AND entity_id = ? AND attribute = ? ORDER BY version",
            (entity_type, entity_id, attribute),
        )
        return [_row_to_fact(r) for r in rows]

    def get_entity(self, entity_type: str, entity_id: str) -> dict[str, WorldFact]:
        rows = self.db.query_all(
            f"SELECT {_COLS} FROM world_state "
            f"WHERE entity_type = ? AND entity_id = ? AND valid_until IS NULL ORDER BY attribute",
            (entity_type, entity_id),
        )
        return {r["attribute"]: _row_to_fact(r) for r in rows}

    def all_current(self, entity_type: str | None = None) -> list[WorldFact]:
        if entity_type is None:
            rows = self.db.query_all(
                f"SELECT {_COLS} FROM world_state WHERE valid_until IS NULL ORDER BY updated_at DESC"
            )
        else:
            rows = self.db.query_all(
                f"SELECT {_COLS} FROM world_state WHERE valid_until IS NULL AND entity_type = ? "
                f"ORDER BY updated_at DESC",
                (entity_type,),
            )
        return [_row_to_fact(r) for r in rows]

    def changed_since(self, since_ts: float, *, limit: int = 100) -> list[WorldFact]:
        rows = self.db.query_all(
            f"SELECT {_COLS} FROM world_state WHERE valid_from >= ? ORDER BY valid_from DESC LIMIT ?",
            (since_ts, max(1, limit)),
        )
        return [_row_to_fact(r) for r in rows]

    def count_current(self) -> int:
        row = self.db.query_one("SELECT COUNT(*) FROM world_state WHERE valid_until IS NULL")
        return int(row[0]) if row else 0
