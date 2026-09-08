"""
SecureData Central -- SDK: fachada Agent que junta TODAS as pecas
(world, memory, events, context, tools, permissions, verification,
planner, event bus, model provider) numa unica classe.

Para uso mais simples de so memoria/estado/contexto, ver
sdc.agent.MemoryAgent (mais enxuto).
"""
from __future__ import annotations

from pathlib import Path

from sdc.context.engine import ContextEngine
from sdc.context.retrieval import Retriever
from sdc.core.types import Capability
from sdc.db.connection import Database
from sdc.events.bus import EventBus
from sdc.events.log import EventLog
from sdc.memory.store import MemoryStore
from sdc.models.provider import EchoProvider, ModelProvider
from sdc.planner.planner import Planner
from sdc.security.permissions import PermissionManager
from sdc.tools.registry import ToolRegistry
from sdc.verification.engine import VerificationEngine
from sdc.world.state import WorldState


class Agent:
    def __init__(
        self,
        name: str = "agent:main",
        *,
        db_path: str | Path = ":memory:",
        model: ModelProvider | None = None,
        max_context_tokens: int = 2000,
        enable_semantic: bool = False,
    ) -> None:
        self.name = name
        self.model = model or EchoProvider()

        self.db = Database(db_path)
        self.memory = MemoryStore(self.db)
        self.world = WorldState(self.db)
        self.events_log = EventLog(self.db)

        self.retriever = Retriever(self.memory, self.world, self.events_log, enable_semantic=enable_semantic)
        self.context = ContextEngine(self.db, self.retriever, max_context_tokens=max_context_tokens)

        self.permissions = PermissionManager()
        self.verification = VerificationEngine()
        self.tools = ToolRegistry(self.permissions, self.context)
        self.planner = Planner(self.verification)
        self.bus = EventBus()

    # -- permissoes --
    def grant(self, capability: Capability, resource: str | None = None) -> None:
        self.permissions.grant(self.name, capability, resource)

    # -- memoria (atalhos) --
    def remember(self, key: str, content: str, **kw):
        m, outcome = self.memory.store(key, content, **kw)
        return m

    def recall(self, key: str, project: str = "") -> str | None:
        m = self.memory.get_by_key(key, project)
        return m.content if m else None

    # -- estado --
    def set_state(self, entity_type: str, entity_id: str, attribute: str, value: str, source: str = "agent"):
        fact, _ = self.world.set(entity_type, entity_id, attribute, value, source=source)
        return fact

    def get_state(self, entity_type: str, entity_id: str, attribute: str) -> str | None:
        f = self.world.get(entity_type, entity_id, attribute)
        return f.value if f else None

    # -- tools --
    def register_tool(self, name, fn, capability: Capability | None = None, resource_arg: str | None = None):
        self.tools.register(name, fn, required_capability=capability, resource_arg=resource_arg)

    def call_tool(self, tool_name: str, **kwargs):
        result = self.tools.call(self.name, tool_name, **kwargs)
        self.bus.publish("action.finished", {"tool": tool_name, "result": result})
        return result

    # -- contexto + LLM --
    def context_for(self, query: str, *, project: str = "", session_id: str = "default", max_tokens: int | None = None) -> str:
        return self.context.build(query, max_tokens=max_tokens, project=project or None, session_id=session_id).text

    def ask(self, question: str, *, project: str = "", session_id: str = "default", max_tokens: int = 512) -> str:
        ctx = self.context_for(question, project=project, session_id=session_id)
        prompt = f"{ctx}\n\nPergunta: {question}\nResposta:" if ctx else f"Pergunta: {question}\nResposta:"
        return self.model.complete(prompt, max_tokens=max_tokens).text

    def close(self) -> None:
        try:
            self.db.close()
        except Exception:  # noqa: BLE001
            pass
