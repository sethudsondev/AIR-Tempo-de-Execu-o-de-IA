"""
SecureData Central -- EventBus: notificacao pub/sub EM PROCESSO.

DIFERENTE do log persistente (sdc/events/log.py): aquele e fato historico
duravel no SQLite; este e coordenacao efemera em tempo real -- ex: o
Planner assina 'task.failed' para replanejar; a Verification assina
'action.finished'. Um e armazenamento, o outro e coordenacao.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Callable

Handler = Callable[[str, dict], None]


@dataclass
class EventBus:
    _subs: dict[str, list[Handler]] = field(default_factory=lambda: defaultdict(list))

    def subscribe(self, topic: str, handler: Handler) -> None:
        self._subs[topic].append(handler)

    def unsubscribe(self, topic: str, handler: Handler) -> None:
        subs = self._subs.get(topic)   # .get: nao cria entrada vazia para topic desconhecido
        if subs and handler in subs:
            subs.remove(handler)

    def publish(self, topic: str, payload: dict) -> None:
        for h in list(self._subs.get(topic, [])):
            h(topic, payload)
        for h in list(self._subs.get("*", [])):
            h(topic, payload)
