"""
SecureData Central -- tipos de dado compartilhados.

Segue o schema pedido no briefing, com a disciplina de design do AIR:
Memory e World State sao camadas SEPARADAS (nao "tudo memoria pra RAG").
  - Memory  = fatos/informacoes discretas com recencia e importancia.
  - World   = estado atual de entidades, com versionamento temporal.
  - Context = o que foi selecionado para reconstruir contexto de sessao.
  - Event   = acontecimentos relevantes (log append-only).
"""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def now() -> float:
    return time.time()


# ---------------------------------------------------------------------------
# Memory
# ---------------------------------------------------------------------------

class MemoryStatus(str, Enum):
    ACTIVE = "active"
    SUPERSEDED = "superseded"   # substituida por versao mais nova (recencia)
    DELETED = "deleted"         # soft-delete


class Importance(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


IMPORTANCE_WEIGHT = {
    Importance.LOW: 0.25,
    Importance.MEDIUM: 0.5,
    Importance.HIGH: 0.8,
    Importance.CRITICAL: 1.0,
}


@dataclass(frozen=True)
class Memory:
    id: str
    key: str                       # ex: "project.name", "user.tone"
    content: str
    type: str = "note"             # project_information | preference | decision | fact | note ...
    source: str = "agent"          # quem/como foi registrado
    importance: Importance = Importance.MEDIUM
    project: str = ""              # "" = global; senao, escopo de isolamento
    status: MemoryStatus = MemoryStatus.ACTIVE
    version: int = 1
    supersedes: str | None = None
    created_at: float = field(default_factory=now)
    updated_at: float = field(default_factory=now)
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "key": self.key,
            "content": self.content,
            "type": self.type,
            "source": self.source,
            "importance": self.importance.value,
            "project": self.project,
            "status": self.status.value,
            "version": self.version,
            "supersedes": self.supersedes,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "metadata": self.metadata,
        }


# ---------------------------------------------------------------------------
# World State -- entidade / atributo / valor, versionado no tempo
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class WorldFact:
    id: str
    entity_type: str               # ex: "project", "service", "user"
    entity_id: str                 # ex: "securedata-central"
    attribute: str                 # ex: "status", "version"
    value: str                     # ex: "development"
    version: int = 1
    valid_from: float = field(default_factory=now)
    valid_until: float | None = None   # None = ainda vigente
    source: str = "agent"
    updated_at: float = field(default_factory=now)

    @property
    def is_current(self) -> bool:
        return self.valid_until is None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "entity_type": self.entity_type,
            "entity_id": self.entity_id,
            "attribute": self.attribute,
            "value": self.value,
            "version": self.version,
            "valid_from": self.valid_from,
            "valid_until": self.valid_until,
            "source": self.source,
            "updated_at": self.updated_at,
            "is_current": self.is_current,
        }


# ---------------------------------------------------------------------------
# Context -- registro do que foi usado para reconstruir contexto
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ContextRef:
    id: str
    session_id: str
    memory_id: str
    relevance: float
    created_at: float = field(default_factory=now)
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "session_id": self.session_id,
            "memory_id": self.memory_id,
            "relevance": self.relevance,
            "created_at": self.created_at,
            "metadata": self.metadata,
        }


# ---------------------------------------------------------------------------
# Event -- log append-only
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Event:
    id: str
    event_type: str                # ex: "memory.created", "world.changed", "deploy"
    entity_id: str = ""            # entidade afetada, se houver
    payload: dict = field(default_factory=dict)
    project: str = ""
    source: str = "agent"
    timestamp: float = field(default_factory=now)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "event_type": self.event_type,
            "entity_id": self.entity_id,
            "payload": self.payload,
            "project": self.project,
            "source": self.source,
            "timestamp": self.timestamp,
        }


def coerce_importance(value: str | Importance | None, default: Importance = Importance.MEDIUM) -> Importance:
    if value is None:
        return default
    if isinstance(value, Importance):
        return value
    try:
        return Importance(str(value).strip().lower())
    except ValueError:
        return default


# ---------------------------------------------------------------------------
# Runtime: capability / goal / task / action / verification
# (mesma familia de tipos do AIR -- necessarios para Planner, Verification,
#  Tool Registry e Permissions)
# ---------------------------------------------------------------------------

class Capability(str, Enum):
    READ = "read"
    WRITE = "write"
    EXECUTE = "execute"
    NETWORK = "network"
    DATABASE = "database"
    FILESYSTEM = "filesystem"


class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"


@dataclass
class Task:
    id: str
    goal_id: str
    description: str
    status: TaskStatus = TaskStatus.PENDING
    depends_on: list[str] = field(default_factory=list)
    result: "ActionResult | None" = None


@dataclass
class Goal:
    id: str
    description: str
    tasks: list[Task] = field(default_factory=list)
    created_at: float = field(default_factory=now)


class VerificationOutcome(str, Enum):
    OK = "ok"
    FAILED = "failed"
    UNKNOWN = "unknown"   # nao deu para verificar com confianca -- honesto, nao finge sucesso


@dataclass
class ActionResult:
    id: str
    tool_name: str
    args: dict
    output: object
    error: str | None = None
    started_at: float = field(default_factory=now)
    finished_at: float | None = None


@dataclass
class Verification:
    id: str
    action_result_id: str
    outcome: VerificationOutcome
    detail: str = ""
    checked_at: float = field(default_factory=now)
