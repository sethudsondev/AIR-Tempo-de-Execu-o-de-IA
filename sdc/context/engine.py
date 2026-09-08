"""
SecureData Central -- Context Engine.

Principio (do briefing): informacao persistente e estruturada NAO deve ser
reenviada inteira como tokens a cada interacao. Duas responsabilidades:

1. HANDLES (put/get/render) -- output grande de tool vira um id curto;
   so o resumo vai pro prompt. Igual ao AIR.

2. BUILD -- monta o contexto minimo para uma query:
     retrieval -> ranking (relevancia, recencia, importancia, estado
     atual, sessao) -> corte por ORCAMENTO DE TOKENS -> texto compacto
     + referencias estruturadas + contabilidade honesta de token.

Registra em context_refs quais memorias entraram, com relevancia e
session_id, para auditoria e para o proximo build da mesma sessao
priorizar o que ja foi usado.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field

from sdc.context.retrieval import Candidate, Retriever
from sdc.core.types import ContextRef, new_id, now
from sdc.db.connection import Database
from sdc.tokens import count_tokens

INLINE_THRESHOLD_CHARS = 200
SUMMARY_CHARS = 140


def _truncate_to_tokens(text: str, max_tokens: int) -> str:
    """Corta o texto ate caber no orcamento. Usa a contagem real
    (count_tokens) num loop de bisseccao rapida sobre caracteres."""
    if count_tokens(text)["tokens"] <= max_tokens:
        return text
    lo, hi = 0, len(text)
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if count_tokens(text[:mid] + " ...")["tokens"] <= max_tokens:
            lo = mid
        else:
            hi = mid - 1
    return (text[:lo].rstrip() + " ...") if lo > 0 else ""


# --------------------------------------------------------------------------
# Handles para output grande
# --------------------------------------------------------------------------

@dataclass
class Handle:
    id: str
    kind: str
    label: str
    content: str
    pinned: bool = False
    created_at: float = field(default_factory=now)

    @property
    def size(self) -> int:
        return len(self.content)


class HandleStore:
    def __init__(self) -> None:
        self._items: dict[str, Handle] = {}

    def put(self, content: str, *, kind: str, label: str, pinned: bool = False) -> str:
        h = Handle(id=new_id("ctx"), kind=kind, label=label, content=content, pinned=pinned)
        self._items[h.id] = h
        return h.id

    def get(self, handle_id: str) -> str:
        h = self._items.get(handle_id)
        if h is None:
            raise KeyError(f"handle desconhecido: {handle_id}")
        return h.content

    def delete(self, handle_id: str) -> bool:
        return self._items.pop(handle_id, None) is not None

    def summarize(self, handle_id: str) -> str:
        h = self._items.get(handle_id)
        if h is None:
            return ""
        if h.size <= SUMMARY_CHARS:
            return h.content
        head = h.content[:SUMMARY_CHARS].rsplit(" ", 1)[0]
        return f"{head}... ({h.size} chars, use get('{h.id}'))"

    def render(self, handle_ids: list[str] | None = None) -> str:
        ids = handle_ids if handle_ids is not None else list(self._items)
        lines = []
        for hid in ids:
            h = self._items.get(hid)
            if h is None:
                continue
            if h.pinned or h.size <= INLINE_THRESHOLD_CHARS:
                lines.append(h.content)
            else:
                lines.append(f"[{h.kind}:{h.id}] {h.label} -- {self.summarize(hid)}")
        return "\n\n".join(lines)


# --------------------------------------------------------------------------
# Build de contexto
# --------------------------------------------------------------------------

@dataclass
class ContextResult:
    text: str
    references: list[dict]
    tokens_used: int
    token_method: str
    budget: int
    candidates_considered: int
    dropped_for_budget: int


class ContextEngine:
    def __init__(self, db: Database, retriever: Retriever, *, max_context_tokens: int = 2000) -> None:
        self.db = db
        self.retriever = retriever
        self.max_context_tokens = max_context_tokens
        self.handles = HandleStore()

    # -- handles (delega) --
    def put(self, content: str, *, kind: str, label: str, pinned: bool = False) -> str:
        return self.handles.put(content, kind=kind, label=label, pinned=pinned)

    def get(self, handle_id: str) -> str:
        return self.handles.get(handle_id)

    # -- build --

    def build(
        self,
        query: str,
        *,
        max_tokens: int | None = None,
        project: str | None = None,
        session_id: str = "default",
    ) -> ContextResult:
        budget = max_tokens if max_tokens and max_tokens > 0 else self.max_context_tokens

        candidates = self.retriever.retrieve(query, limit=20, project=project)
        used_in_session = self._session_memory_ids(session_id)

        # bonus leve para o que ja foi usado nesta sessao (continuidade)
        for c in candidates:
            if c.kind == "memory" and c.ref_id in used_in_session:
                c.score = round(min(c.score + 0.05, 1.0), 4)
        candidates.sort(key=lambda c: c.score, reverse=True)

        lines: list[str] = []
        refs: list[dict] = []
        running = 0
        method = "heuristic_chars_div_4"
        dropped = 0

        for c in candidates:
            rendered = self._render_candidate(c)
            tk = count_tokens(rendered)
            method = tk["method"]
            if running + tk["tokens"] > budget:
                # 1. tenta versao compacta
                rendered = self._render_candidate(c, compact=True)
                tk = count_tokens(rendered)
                if running + tk["tokens"] > budget:
                    if lines:
                        dropped += 1
                        continue
                    # 2. primeiro item e ainda nao cabe: trunca pra caber
                    rendered = _truncate_to_tokens(rendered, budget)
                    tk = count_tokens(rendered)
                    if tk["tokens"] > budget:
                        dropped += 1
                        continue
            lines.append(rendered)
            running += tk["tokens"]
            refs.append({"kind": c.kind, "id": c.ref_id, "label": c.label, "relevance": c.score, "method": c.method})
            if c.kind == "memory":
                self._record_ref(session_id, c.ref_id, c.score)

        text = "\n".join(lines)
        return ContextResult(
            text=text,
            references=refs,
            tokens_used=running,
            token_method=method,
            budget=budget,
            candidates_considered=len(candidates),
            dropped_for_budget=dropped,
        )

    # -- helpers --

    @staticmethod
    def _render_candidate(c: Candidate, *, compact: bool = False) -> str:
        body = c.content
        if compact and len(body) > SUMMARY_CHARS:
            body = body[:SUMMARY_CHARS].rsplit(" ", 1)[0] + "..."
        tag = {"memory": "MEM", "world": "STATE", "event": "EVENT"}.get(c.kind, c.kind.upper())
        return f"[{tag}] {c.label}: {body}"

    def _session_memory_ids(self, session_id: str) -> set[str]:
        rows = self.db.query_all(
            "SELECT DISTINCT memory_id FROM context_refs WHERE session_id = ?", (session_id,)
        )
        return {r["memory_id"] for r in rows}

    def _record_ref(self, session_id: str, memory_id: str, relevance: float) -> None:
        ref = ContextRef(
            id=new_id("cref"),
            session_id=session_id,
            memory_id=memory_id,
            relevance=relevance,
        )
        with self.db.lock:
            self.db.conn.execute(
                "INSERT INTO context_refs (id, session_id, memory_id, relevance, created_at, metadata) "
                "VALUES (?,?,?,?,?,?)",
                (ref.id, ref.session_id, ref.memory_id, ref.relevance, ref.created_at, json.dumps({})),
            )
            self.db.conn.commit()
