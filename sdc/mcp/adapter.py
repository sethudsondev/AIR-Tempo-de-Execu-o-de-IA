"""
SecureData Central -- adapter: a ponte entre o MCP e o nucleo.

Regra de design (do AIR): este modulo NAO conhece nada de MCP. Recebe
str/int/dict, devolve dict. Toda a logica testavel mora aqui; server.py
so registra tools e delega. Assim o nucleo continua 100% usavel sem MCP.

Toda entrada passa por sdc.security.guard antes de tocar o banco.
Toda excecao vira um dict {"ok": False, "error": ...} -- nunca stacktrace
cru pro cliente.
"""
from __future__ import annotations

import logging

from sdc.config import Config
from sdc.context.engine import ContextEngine
from sdc.context.retrieval import Retriever
from sdc.core.types import coerce_importance
from sdc.db.connection import Database
from sdc.events.log import EventLog
from sdc.memory.store import MemoryStore
from sdc.security.guard import (
    ValidationError,
    clamp_limit,
    clean_identifier,
    clean_key,
    clean_metadata,
    clean_project,
    clean_text,
)
from sdc.world.state import WorldState

logger = logging.getLogger("sdc.adapter")


def _ok(**data) -> dict:
    return {"ok": True, **data}


def _err(message: str, *, code: str = "error") -> dict:
    return {"ok": False, "error": message, "code": code}


class Adapter:
    def __init__(self, config: Config, *, db: Database | None = None) -> None:
        self.config = config
        if db is not None:
            self.db = db
        else:
            config.ensure_storage_dir()
            self.db = Database(config.db_path)
        self.memory = MemoryStore(self.db)
        self.world = WorldState(self.db)
        self.events = EventLog(self.db)
        self.retriever = Retriever(
            self.memory, self.world, self.events,
            enable_semantic=config.enable_semantic_search,
        )
        self.context = ContextEngine(
            self.db, self.retriever, max_context_tokens=config.max_context_tokens
        )
        logger.info("adapter pronto (db=%s)", config.db_path)

    def close(self) -> None:
        """Fecha a conexao com o banco. Chame ao descartar um Adapter de
        vida curta (testes, jobs) para liberar o arquivo no Windows."""
        try:
            self.db.close()
        except Exception:  # noqa: BLE001
            pass

    # -- wrapper de erro ------------------------------------------------

    def _guarded(self, fn, *args, **kwargs) -> dict:
        try:
            return fn(*args, **kwargs)
        except ValidationError as exc:
            return _err(str(exc), code="validation")
        except KeyError as exc:
            return _err(str(exc), code="not_found")
        except Exception as exc:  # noqa: BLE001 -- nunca vaza stacktrace pro cliente
            logger.exception("erro em %s", getattr(fn, "__name__", fn))
            return _err("erro interno ao processar a requisicao", code="internal")

    # =================================================================
    # MEMORY
    # =================================================================

    def store_memory(self, key, content, type="note", source="agent", importance="medium", project="", metadata=None) -> dict:
        return self._guarded(self._store_memory, key, content, type, source, importance, project, metadata)

    def _store_memory(self, key, content, type, source, importance, project, metadata) -> dict:
        c = self.config
        key = clean_key(key, max_chars=c.max_key_chars)
        content = clean_text(content, field="content", max_chars=c.max_content_chars)
        type = clean_identifier(type or "note", field="type", max_chars=60)
        source = clean_text(source or "agent", field="source", max_chars=120, allow_empty=True) or "agent"
        project = clean_project(project)
        meta = clean_metadata(metadata, max_bytes=c.max_metadata_bytes)
        imp = coerce_importance(importance)

        mem, outcome = self.memory.store(
            key, content, type=type, source=source, importance=imp, project=project, metadata=meta
        )
        if outcome != "deduped":
            self.events.record(
                "memory.created" if outcome == "created" else "memory.updated",
                entity_id=mem.id, payload={"key": key, "version": mem.version}, project=project,
            )
        return _ok(outcome=outcome, memory=mem.to_dict())

    def get_memory(self, id=None, key=None, project="") -> dict:
        return self._guarded(self._get_memory, id, key, project)

    def _get_memory(self, id, key, project) -> dict:
        if id:
            mem = self.memory.get(clean_identifier(id, field="id"))
        elif key:
            mem = self.memory.get_by_key(clean_key(key, max_chars=self.config.max_key_chars), clean_project(project))
        else:
            raise ValidationError("informe 'id' ou 'key'")
        if mem is None:
            return _err("memoria nao encontrada", code="not_found")
        return _ok(memory=mem.to_dict())

    def search_memory(self, query, limit=None, project="") -> dict:
        return self._guarded(self._search_memory, query, limit, project)

    def _search_memory(self, query, limit, project) -> dict:
        c = self.config
        query = clean_text(query, field="query", max_chars=c.max_query_chars)
        limit = clamp_limit(limit, default=c.default_search_limit, maximum=c.max_search_limit)
        project = clean_project(project) or None
        results = self.memory.search(query, limit=limit, project=project)
        return _ok(
            count=len(results),
            results=[{"memory": m.to_dict(), "score": s} for m, s in results],
            method="keyword",
        )

    def update_memory(self, id, content=None, importance=None, type=None, metadata=None) -> dict:
        return self._guarded(self._update_memory, id, content, importance, type, metadata)

    def _update_memory(self, id, content, importance, type, metadata) -> dict:
        c = self.config
        id = clean_identifier(id, field="id")
        if content is not None:
            content = clean_text(content, field="content", max_chars=c.max_content_chars)
        if type is not None:
            type = clean_identifier(type, field="type", max_chars=60)
        if metadata is not None:
            metadata = clean_metadata(metadata, max_bytes=c.max_metadata_bytes)
        imp = coerce_importance(importance) if importance is not None else None

        res = self.memory.update(id, content=content, importance=imp, type=type, metadata=metadata)
        if res is None:
            return _err("memoria nao encontrada ou nao esta ativa", code="not_found")
        mem, outcome = res
        self.events.record("memory.updated", entity_id=mem.id, payload={"key": mem.key, "version": mem.version}, project=mem.project)
        return _ok(outcome=outcome, memory=mem.to_dict())

    def delete_memory(self, id) -> dict:
        return self._guarded(self._delete_memory, id)

    def _delete_memory(self, id) -> dict:
        id = clean_identifier(id, field="id")
        mem = self.memory.get(id)
        ok = self.memory.delete(id)
        if not ok:
            return _err("memoria nao encontrada ou ja excluida", code="not_found")
        self.events.record("memory.deleted", entity_id=id, payload={"key": mem.key if mem else None},
                           project=mem.project if mem else "")
        return _ok(deleted=id)

    def memory_history(self, key, project="") -> dict:
        return self._guarded(self._memory_history, key, project)

    def _memory_history(self, key, project) -> dict:
        key = clean_key(key, max_chars=self.config.max_key_chars)
        versions = self.memory.history(key, clean_project(project))
        return _ok(key=key, count=len(versions), versions=[m.to_dict() for m in versions])

    # =================================================================
    # WORLD STATE
    # =================================================================

    def update_world_state(self, entity_type, entity_id, attribute, value, source="agent") -> dict:
        return self._guarded(self._update_world_state, entity_type, entity_id, attribute, value, source)

    def _update_world_state(self, entity_type, entity_id, attribute, value, source) -> dict:
        entity_type = clean_identifier(entity_type, field="entity_type", max_chars=80)
        entity_id = clean_identifier(entity_id, field="entity_id", max_chars=200)
        attribute = clean_identifier(attribute, field="attribute", max_chars=80)
        value = clean_text(value, field="value", max_chars=self.config.max_content_chars, allow_empty=True)
        source = clean_text(source or "agent", field="source", max_chars=120, allow_empty=True) or "agent"

        fact, outcome = self.world.set(entity_type, entity_id, attribute, value, source=source)
        prev = self.world.previous(entity_type, entity_id, attribute) if outcome == "changed" else None
        if outcome != "unchanged":
            self.events.record(
                "world.changed",
                entity_id=f"{entity_type}:{entity_id}",
                payload={"attribute": attribute, "value": value,
                         "previous": prev.value if prev else None},
            )
        return _ok(
            outcome=outcome,
            fact=fact.to_dict(),
            previous=prev.to_dict() if prev else None,
        )

    def get_world_state(self, entity_type, entity_id, attribute=None) -> dict:
        return self._guarded(self._get_world_state, entity_type, entity_id, attribute)

    def _get_world_state(self, entity_type, entity_id, attribute) -> dict:
        entity_type = clean_identifier(entity_type, field="entity_type", max_chars=80)
        entity_id = clean_identifier(entity_id, field="entity_id", max_chars=200)
        if attribute:
            attribute = clean_identifier(attribute, field="attribute", max_chars=80)
            fact = self.world.get(entity_type, entity_id, attribute)
            if fact is None:
                return _err("atributo nao encontrado para essa entidade", code="not_found")
            prev = self.world.previous(entity_type, entity_id, attribute)
            return _ok(current=fact.to_dict(), previous=prev.to_dict() if prev else None)
        attrs = self.world.get_entity(entity_type, entity_id)
        if not attrs:
            return _err("entidade sem estado registrado", code="not_found")
        return _ok(
            entity_type=entity_type, entity_id=entity_id,
            state={k: v.to_dict() for k, v in attrs.items()},
        )

    def world_history(self, entity_type, entity_id, attribute) -> dict:
        return self._guarded(self._world_history, entity_type, entity_id, attribute)

    def _world_history(self, entity_type, entity_id, attribute) -> dict:
        entity_type = clean_identifier(entity_type, field="entity_type", max_chars=80)
        entity_id = clean_identifier(entity_id, field="entity_id", max_chars=200)
        attribute = clean_identifier(attribute, field="attribute", max_chars=80)
        hist = self.world.history(entity_type, entity_id, attribute)
        return _ok(count=len(hist), history=[f.to_dict() for f in hist])

    # =================================================================
    # EVENTS
    # =================================================================

    def record_event(self, event_type, entity_id="", payload=None, project="", source="agent") -> dict:
        return self._guarded(self._record_event, event_type, entity_id, payload, project, source)

    def _record_event(self, event_type, entity_id, payload, project, source) -> dict:
        event_type = clean_identifier(event_type, field="event_type", max_chars=80)
        entity_id = clean_text(entity_id or "", field="entity_id", max_chars=200, allow_empty=True)
        payload = clean_metadata(payload, max_bytes=self.config.max_metadata_bytes)
        project = clean_project(project)
        source = clean_text(source or "agent", field="source", max_chars=120, allow_empty=True) or "agent"
        ev = self.events.record(event_type, entity_id=entity_id, payload=payload, project=project, source=source)
        return _ok(event=ev.to_dict())

    def recent_changes(self, limit=None, event_type=None, project="") -> dict:
        return self._guarded(self._recent_changes, limit, event_type, project)

    def _recent_changes(self, limit, event_type, project) -> dict:
        limit = clamp_limit(limit, default=20, maximum=200)
        if event_type:
            event_type = clean_identifier(event_type, field="event_type", max_chars=80)
        project = clean_project(project) or None
        evs = self.events.recent(limit=limit, event_type=event_type, project=project)
        return _ok(count=len(evs), events=[e.to_dict() for e in evs])

    # =================================================================
    # CONTEXT
    # =================================================================

    def search_context(self, query, limit=None, project="") -> dict:
        return self._guarded(self._search_context, query, limit, project)

    def _search_context(self, query, limit, project) -> dict:
        c = self.config
        query = clean_text(query, field="query", max_chars=c.max_query_chars)
        limit = clamp_limit(limit, default=c.default_search_limit, maximum=c.max_search_limit)
        project = clean_project(project) or None
        cands = self.retriever.retrieve(query, limit=limit, project=project)
        return _ok(
            count=len(cands),
            results=[
                {"kind": x.kind, "id": x.ref_id, "label": x.label,
                 "content": x.content, "score": x.score, "method": x.method}
                for x in cands
            ],
        )

    def get_context(self, query, max_tokens=None, project="", session_id="default") -> dict:
        return self._guarded(self._get_context, query, max_tokens, project, session_id)

    def _get_context(self, query, max_tokens, project, session_id) -> dict:
        c = self.config
        query = clean_text(query, field="query", max_chars=c.max_query_chars)
        project = clean_project(project) or None
        session_id = clean_identifier(session_id or "default", field="session_id", max_chars=120)
        mt = None
        if max_tokens not in (None, ""):
            try:
                mt = max(1, min(int(max_tokens), 32_000))
            except (TypeError, ValueError):
                mt = None
        res = self.context.build(query, max_tokens=mt, project=project, session_id=session_id)
        return _ok(
            context=res.text,
            references=res.references,
            tokens_used=res.tokens_used,
            token_method=res.token_method,
            budget=res.budget,
            candidates_considered=res.candidates_considered,
            dropped_for_budget=res.dropped_for_budget,
        )

    # =================================================================
    # STATUS / RESOURCES
    # =================================================================

    def status(self) -> dict:
        return _ok(
            db_path=str(self.config.db_path),
            migrations=list(getattr(self.db, "applied_migrations", [])),
            memories_active=self.memory.count_active(),
            world_facts_current=self.world.count_current(),
            events_total=self.events.count(),
            config=self.config.as_dict(),
        )

    def snapshot_memories(self) -> dict:
        return _ok(memories=[m.to_dict() for m in self.memory.all_active()])

    def snapshot_world(self) -> dict:
        return _ok(
            world=[f.to_dict() for f in self.world.all_current()],
            recent_events=[e.to_dict() for e in self.events.recent(limit=20)],
        )
