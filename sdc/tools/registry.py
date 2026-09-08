"""
SecureData Central -- Tool Registry.

O protocolo de tool e MCP (nao se reimplementa). O que este modulo
adiciona: o FIO que liga tool call a (1) permissao por capacidade e
(2) Context Engine -- o retorno grande de uma tool NUNCA volta cru,
entra no ContextEngine e volta so um handle + preview. E aqui que o
principio "nao reenviar informacao estruturada como token repetido"
vira mecanismo.

call() SEMPRE devolve ActionResult, nunca levanta -- inclusive quando a
permissao e negada (a tool continua nao rodando; so muda como quem chama
fica sabendo: de excecao para ActionResult.error).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from sdc.context.engine import INLINE_THRESHOLD_CHARS, ContextEngine
from sdc.core.types import ActionResult, Capability, new_id, now
from sdc.security.permissions import PermissionManager


@dataclass
class ToolSpec:
    name: str
    fn: Callable[..., object]
    required_capability: Capability | None = None
    resource_arg: str | None = None   # kwarg que vira o 'resource' checado


class ToolRegistry:
    def __init__(self, permissions: PermissionManager, context: ContextEngine) -> None:
        self._tools: dict[str, ToolSpec] = {}
        self.permissions = permissions
        self.context = context

    def register(
        self,
        name: str,
        fn: Callable[..., object],
        required_capability: Capability | None = None,
        resource_arg: str | None = None,
    ) -> None:
        self._tools[name] = ToolSpec(name, fn, required_capability, resource_arg)

    def names(self) -> list[str]:
        return sorted(self._tools)

    def call(self, principal: str, tool_name: str, **kwargs) -> ActionResult:
        started = now()
        spec = self._tools.get(tool_name)
        if spec is None:
            return ActionResult(id=new_id("act"), tool_name=tool_name, args=kwargs,
                                output=None, error=f"tool desconhecida: {tool_name}",
                                started_at=started, finished_at=now())

        try:
            if spec.required_capability is not None:
                resource = kwargs.get(spec.resource_arg) if spec.resource_arg else None
                self.permissions.require(principal, spec.required_capability, resource)
            raw = spec.fn(**kwargs)
            error = None
        except Exception as exc:   # PermissionDenied inclusa
            raw = None
            error = str(exc)

        output = raw
        if isinstance(raw, str) and len(raw) > INLINE_THRESHOLD_CHARS:
            hid = self.context.put(raw, kind="tool_output", label=f"resultado de {tool_name}")
            output = {"handle": hid, "preview": self.context.handles.summarize(hid)}

        return ActionResult(id=new_id("act"), tool_name=tool_name, args=kwargs,
                            output=output, error=error, started_at=started, finished_at=now())
