"""
SecureData Central -- Memory Store.

Fatos/informacoes discretas com:
  - recencia por SUPERSEDE (a versao nova marca a antiga como 'superseded',
    nao apaga) -- da para auditar a evolucao com history();
  - importancia (low/medium/high/critical) usada pelo Context Engine;
  - dedup: gravar de novo a MESMA chave com o MESMO conteudo nao cria
    versao nova, so devolve a existente.

Uma unica memoria ACTIVE por (key, project) -- garantido por indice unico
parcial (migration 2) alem da logica aqui.
"""
from __future__ import annotations

import json

from sdc.core.types import (
    IMPORTANCE_WEIGHT,
    Importance,
    Memory,
    MemoryStatus,
    coerce_importance,
    new_id,
    now,
)
from sdc.db.connection import Database

_COLS = "id, key, content, type, source, importance, project, status, version, supersedes, created_at, updated_at, metadata"

# stopwords PT/EN comuns -- nao ajudam a discriminar relevancia
_STOPWORDS = {
    "a", "o", "as", "os", "de", "do", "da", "dos", "das", "e", "ou", "um", "uma",
    "no", "na", "em", "para", "por", "com", "que", "qual", "quais", "meu", "minha",
    "the", "of", "to", "in", "on", "is", "it", "and", "or", "a", "an", "my", "what",
}
_WORD_RE = __import__("re").compile(r"[a-z0-9À-ſ]+")


def _words(text: str) -> set[str]:
    return set(_WORD_RE.findall(text.lower()))


def _significant_terms(query: str) -> list[str]:
    terms = [t for t in _WORD_RE.findall(query.lower()) if len(t) > 2 and t not in _STOPWORDS]
    if terms:
        return terms
    # query so com termos curtos: usa o que tiver, sem descartar tudo
    return [t for t in _WORD_RE.findall(query.lower()) if t]


def _term_matches(term: str, words: set[str]) -> bool:
    if term in words:
        return True
    if len(term) >= 4:
        for w in words:
            if term in w or w in term:
                return True
            # prefixo comum >=5 chars: aproxima flexao/idioma
            # (projeto<->project, configuracao<->config, deploy<->deployment)
            if len(term) >= 5 and len(w) >= 5 and term[:5] == w[:5]:
                return True
    return False


def _row_to_memory(row) -> Memory:
    return Memory(
        id=row["id"],
        key=row["key"],
        content=row["content"],
        type=row["type"],
        source=row["source"],
        importance=coerce_importance(row["importance"]),
        project=row["project"],
        status=MemoryStatus(row["status"]),
        version=row["version"],
        supersedes=row["supersedes"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        metadata=json.loads(row["metadata"] or "{}"),
    )


class MemoryStore:
    def __init__(self, db: Database) -> None:
        self.db = db

    # -- escrita -----------------------------------------------------------

    def store(
        self,
        key: str,
        content: str,
        *,
        type: str = "note",
        source: str = "agent",
        importance: str | Importance = Importance.MEDIUM,
        project: str = "",
        metadata: dict | None = None,
    ) -> tuple[Memory, str]:
        """Retorna (memory, outcome) onde outcome in {'created','superseded','deduped'}."""
        imp = coerce_importance(importance)
        meta = metadata or {}
        prior = self.get_by_key(key, project)

        if prior is not None:
            same_content = prior.content == content
            same_meta = prior.metadata == meta
            if same_content and same_meta and prior.importance == imp and prior.type == type:
                return prior, "deduped"

        ts = now()
        version = (prior.version + 1) if prior else 1
        supersedes = prior.id if prior else None

        with self.db.lock:
            if prior is not None:
                self.db.conn.execute(
                    "UPDATE memories SET status = ?, updated_at = ? WHERE id = ?",
                    (MemoryStatus.SUPERSEDED.value, ts, prior.id),
                )
            mem = Memory(
                id=new_id("mem"),
                key=key,
                content=content,
                type=type,
                source=source,
                importance=imp,
                project=project,
                status=MemoryStatus.ACTIVE,
                version=version,
                supersedes=supersedes,
                created_at=ts,
                updated_at=ts,
                metadata=meta,
            )
            self.db.conn.execute(
                f"INSERT INTO memories ({_COLS}) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    mem.id, mem.key, mem.content, mem.type, mem.source, mem.importance.value,
                    mem.project, mem.status.value, mem.version, mem.supersedes,
                    mem.created_at, mem.updated_at,
                    json.dumps(mem.metadata, ensure_ascii=False),
                ),
            )
            self.db.conn.commit()
            self.db.bump()

        return mem, ("superseded" if prior else "created")

    def update(
        self,
        memory_id: str,
        *,
        content: str | None = None,
        importance: str | Importance | None = None,
        type: str | None = None,
        metadata: dict | None = None,
    ) -> tuple[Memory, str] | None:
        """Cria uma nova versao (supersede) a partir de uma memoria ACTIVE."""
        current = self.get(memory_id)
        if current is None or current.status != MemoryStatus.ACTIVE:
            return None
        return self.store(
            current.key,
            content if content is not None else current.content,
            type=type if type is not None else current.type,
            source=current.source,
            importance=importance if importance is not None else current.importance,
            project=current.project,
            metadata=metadata if metadata is not None else current.metadata,
        )

    def delete(self, memory_id: str) -> bool:
        """Soft-delete: marca DELETED, mantem a linha (auditoria)."""
        with self.db.lock:
            cur = self.db.conn.execute(
                "UPDATE memories SET status = ?, updated_at = ? WHERE id = ? AND status != ?",
                (MemoryStatus.DELETED.value, now(), memory_id, MemoryStatus.DELETED.value),
            )
            self.db.conn.commit()
            if cur.rowcount:
                self.db.bump()
            return cur.rowcount > 0

    # -- leitura ----------------------------------------------------------

    def get(self, memory_id: str) -> Memory | None:
        row = self.db.query_one(f"SELECT {_COLS} FROM memories WHERE id = ?", (memory_id,))
        return _row_to_memory(row) if row else None

    def get_by_key(self, key: str, project: str = "") -> Memory | None:
        row = self.db.query_one(
            f"SELECT {_COLS} FROM memories WHERE key = ? AND project = ? AND status = ?",
            (key, project, MemoryStatus.ACTIVE.value),
        )
        return _row_to_memory(row) if row else None

    def history(self, key: str, project: str = "") -> list[Memory]:
        rows = self.db.query_all(
            f"SELECT {_COLS} FROM memories WHERE key = ? AND project = ? ORDER BY version",
            (key, project),
        )
        return [_row_to_memory(r) for r in rows]

    def all_active(self, project: str | None = None) -> list[Memory]:
        if project is None:
            rows = self.db.query_all(
                f"SELECT {_COLS} FROM memories WHERE status = ? ORDER BY updated_at DESC",
                (MemoryStatus.ACTIVE.value,),
            )
        else:
            rows = self.db.query_all(
                f"SELECT {_COLS} FROM memories WHERE status = ? AND (project = ? OR project = '') "
                f"ORDER BY updated_at DESC",
                (MemoryStatus.ACTIVE.value, project),
            )
        return [_row_to_memory(r) for r in rows]

    def count_active(self, project: str | None = None) -> int:
        if project is None:
            row = self.db.query_one(
                "SELECT COUNT(*) FROM memories WHERE status = ?", (MemoryStatus.ACTIVE.value,)
            )
        else:
            row = self.db.query_one(
                "SELECT COUNT(*) FROM memories WHERE status = ? AND (project = ? OR project = '')",
                (MemoryStatus.ACTIVE.value, project),
            )
        return int(row[0]) if row else 0

    def search(self, query: str, *, limit: int = 5, project: str | None = None) -> list[tuple[Memory, float]]:
        """Busca por palavra-chave em key + content + type. Score simples e
        transparente: fracao de termos significativos presentes, com bonus
        para match na key e para importancia/recencia.

        Ignora stopwords/termos muito curtos (<=2 chars) para evitar
        falso-positivo por substring ('o' casando 'bolo')."""
        terms = _significant_terms(query)
        candidates = self.all_active(project)
        if not terms:
            return [(m, 0.0) for m in candidates][: max(1, limit)]

        scored = []
        newest = max((m.updated_at for m in candidates), default=now())
        oldest = min((m.updated_at for m in candidates), default=newest - 1)
        span = max(newest - oldest, 1.0)
        for m in candidates:
            key_words = _words(m.key)
            body_words = _words(f"{m.content} {m.type}")
            key_hits = sum(1 for t in terms if _term_matches(t, key_words))
            body_hits = sum(1 for t in terms if _term_matches(t, body_words))
            hits = min(key_hits + body_hits, len(terms))
            if hits == 0:
                continue
            base = hits / len(terms)
            key_bonus = 0.25 * (key_hits / len(terms))
            recency = 0.15 * ((m.updated_at - oldest) / span)
            imp = 0.10 * IMPORTANCE_WEIGHT[m.importance]
            scored.append((m, round(min(base + key_bonus + recency + imp, 1.0), 4)))
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[: max(1, limit)]
