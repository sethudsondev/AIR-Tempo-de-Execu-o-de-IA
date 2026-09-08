"""
SecureData Central -- SDK: fachada para usar a camada de memoria/contexto
EM PROCESSO, sem MCP (para backends que embutem o SDC direto em vez de
falar por stdio). Mesma logica do adapter, API mais direta.

    from sdc.agent import MemoryAgent
    agent = MemoryAgent()                       # usa SDC_DB_PATH / DATABASE_URL
    agent.remember("project.name", "SecureData Central", importance="high")
    agent.set_state("project", "sdc", "status", "development")
    ctx = agent.context("continue o trabalho de ontem", session_id="sess-42")
    print(ctx["context"])
"""
from __future__ import annotations

from sdc.config import Config, load_config
from sdc.db.connection import Database
from sdc.mcp.adapter import Adapter


class MemoryAgent:
    def __init__(self, config: Config | None = None, *, db: Database | None = None) -> None:
        self._adapter = Adapter(config or load_config(), db=db)

    # -- memory --
    def remember(self, key: str, content: str, **kw) -> dict:
        return self._adapter.store_memory(key, content, **kw)

    def recall(self, key: str, project: str = "") -> dict:
        return self._adapter.get_memory(key=key, project=project)

    def search(self, query: str, limit: int = 5, project: str = "") -> dict:
        return self._adapter.search_memory(query, limit=limit, project=project)

    def revise(self, memory_id: str, **kw) -> dict:
        return self._adapter.update_memory(memory_id, **kw)

    def forget(self, memory_id: str) -> dict:
        return self._adapter.delete_memory(memory_id)

    def history(self, key: str, project: str = "") -> dict:
        return self._adapter.memory_history(key, project=project)

    # -- world state --
    def set_state(self, entity_type: str, entity_id: str, attribute: str, value: str, source: str = "agent") -> dict:
        return self._adapter.update_world_state(entity_type, entity_id, attribute, value, source=source)

    def get_state(self, entity_type: str, entity_id: str, attribute: str | None = None) -> dict:
        return self._adapter.get_world_state(entity_type, entity_id, attribute)

    def state_history(self, entity_type: str, entity_id: str, attribute: str) -> dict:
        return self._adapter.world_history(entity_type, entity_id, attribute)

    # -- events --
    def log_event(self, event_type: str, **kw) -> dict:
        return self._adapter.record_event(event_type, **kw)

    def recent_changes(self, limit: int = 20, **kw) -> dict:
        return self._adapter.recent_changes(limit=limit, **kw)

    # -- context --
    def context(self, query: str, *, max_tokens: int | None = None, project: str = "", session_id: str = "default") -> dict:
        return self._adapter.get_context(query, max_tokens=max_tokens, project=project, session_id=session_id)

    def search_context(self, query: str, limit: int = 5, project: str = "") -> dict:
        return self._adapter.search_context(query, limit=limit, project=project)

    def status(self) -> dict:
        return self._adapter.status()
