"""
SecureData Central -- Context Retrieval.

Junta candidatos de 3 fontes para uma query:
  - Memory  (busca por palavra-chave, opcionalmente semantica)
  - World State (fatos atuais cujo entity/attribute/value casam a query)
  - Events  (acontecimentos recentes relevantes)

Devolve itens ja pontuados; a selecao final que respeita o orcamento de
token e do Context Engine (engine.py). Nao carrega "tudo" -- corta pelo
score aqui antes de o engine sequer olhar.

Busca semantica e OPCIONAL e desligada por padrao (SDC_ENABLE_SEMANTIC_SEARCH).
Sem o pacote ou sem a env var, cai para palavra-chave -- reportado no campo
'method' de cada candidato de memoria.
"""
from __future__ import annotations

from dataclasses import dataclass

from sdc.core.types import IMPORTANCE_WEIGHT, now
from sdc.events.log import EventLog
from sdc.memory.store import MemoryStore
from sdc.world.state import WorldState


@dataclass
class Candidate:
    kind: str          # "memory" | "world" | "event"
    ref_id: str
    label: str
    content: str
    score: float
    method: str
    created_at: float


from sdc.adapters import semantic_search


class Retriever:
    def __init__(
        self,
        memory: MemoryStore,
        world: WorldState,
        events: EventLog,
        *,
        enable_semantic: bool = False,
    ) -> None:
        self.memory = memory
        self.world = world
        self.events = events
        self.enable_semantic = enable_semantic

    def retrieve(self, query: str, *, limit: int = 12, project: str | None = None) -> list[Candidate]:
        out: list[Candidate] = []
        out.extend(self._from_memory(query, limit, project))
        out.extend(self._from_world(query, limit))
        out.extend(self._from_events(query, limit, project))
        out.sort(key=lambda c: c.score, reverse=True)
        return out[:limit]

    # -- fontes ---------------------------------------------------------

    def _from_memory(self, query: str, limit: int, project) -> list[Candidate]:
        method = "keyword"
        results = self.memory.search(query, limit=limit, project=project)

        if self.enable_semantic and query.strip():
            actives = self.memory.all_active(project)
            ranked = semantic_search.rank(
                query, [f"{m.key} {m.content}" for m in actives], limit=limit
            )
            if ranked:
                results = [(actives[i], score) for i, score in ranked]
                method = "semantic:all-MiniLM-L6-v2"

        cands = []
        for mem, base in results:
            imp = IMPORTANCE_WEIGHT[mem.importance]
            score = round(0.7 * base + 0.3 * imp, 4)
            cands.append(
                Candidate(
                    kind="memory",
                    ref_id=mem.id,
                    label=f"{mem.key} ({mem.type})",
                    content=mem.content,
                    score=score,
                    method=method,
                    created_at=mem.updated_at,
                )
            )
        return cands

    def _from_world(self, query: str, limit: int) -> list[Candidate]:
        terms = [t for t in query.lower().split() if t]
        cands = []
        for f in self.world.all_current():
            hay = f"{f.entity_type} {f.entity_id} {f.attribute} {f.value}".lower()
            hits = sum(1 for t in terms if t in hay) if terms else 0
            if terms and hits == 0:
                continue
            score = round(0.5 + 0.4 * (hits / max(len(terms), 1)), 4)
            cands.append(
                Candidate(
                    kind="world",
                    ref_id=f.id,
                    label=f"{f.entity_type}:{f.entity_id}.{f.attribute}",
                    content=f"{f.value}",
                    score=score,
                    method="world_current",
                    created_at=f.valid_from,
                )
            )
        cands.sort(key=lambda c: c.score, reverse=True)
        return cands[:limit]

    def _from_events(self, query: str, limit: int, project) -> list[Candidate]:
        terms = [t for t in query.lower().split() if t]
        recent = self.events.recent(limit=50, project=project)
        if not recent:
            return []
        newest = recent[0].timestamp
        oldest = recent[-1].timestamp
        span = max(newest - oldest, 1.0)
        cands = []
        for ev in recent:
            hay = f"{ev.event_type} {ev.entity_id} {ev.payload}".lower()
            hits = sum(1 for t in terms if t in hay) if terms else 0
            if terms and hits == 0:
                continue
            recency = (ev.timestamp - oldest) / span
            score = round(0.3 + 0.4 * recency + 0.3 * (hits / max(len(terms), 1)), 4)
            cands.append(
                Candidate(
                    kind="event",
                    ref_id=ev.id,
                    label=ev.event_type,
                    content=f"{ev.entity_id} {ev.payload}".strip(),
                    score=score,
                    method="event_recent",
                    created_at=ev.timestamp,
                )
            )
        cands.sort(key=lambda c: c.score, reverse=True)
        return cands[: max(3, limit // 2)]
