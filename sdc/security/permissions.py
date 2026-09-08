"""
SecureData Central -- permissao granular por capacidade.

Complementa sdc/security/guard.py (que valida FORMATO de entrada). Aqui e
"quem pode fazer o que, em qual escopo": um Grant concede uma Capability
a um principal (agente / tool / sessao), opcionalmente restrita a um
padrao de recurso (glob de path para FILESYSTEM, host para NETWORK...).

check() NEGA por padrao -- allowlist, nao denylist. O oposto do que causa
vazamento de escopo em producao.
"""
from __future__ import annotations

import fnmatch
from dataclasses import dataclass, field

from sdc.core.types import Capability, new_id, now


@dataclass(frozen=True)
class Grant:
    id: str
    principal: str
    capability: Capability
    resource: str | None = None   # None = qualquer recurso dessa capacidade
    created_at: float = field(default_factory=now)


class PermissionDenied(Exception):
    pass


class PermissionManager:
    def __init__(self) -> None:
        self._grants: list[Grant] = []

    def grant(self, principal: str, capability: Capability, resource: str | None = None) -> Grant:
        g = Grant(id=new_id("grant"), principal=principal, capability=capability, resource=resource)
        self._grants.append(g)
        return g

    def revoke(self, grant_id: str) -> None:
        self._grants = [g for g in self._grants if g.id != grant_id]

    def check(self, principal: str, capability: Capability, resource: str | None = None) -> bool:
        for g in self._grants:
            if g.principal != principal or g.capability != capability:
                continue
            if g.resource is None:
                return True
            if resource is not None and fnmatch.fnmatch(resource, g.resource):
                return True
        return False

    def require(self, principal: str, capability: Capability, resource: str | None = None) -> None:
        if not self.check(principal, capability, resource):
            scope = f" em '{resource}'" if resource else ""
            raise PermissionDenied(f"'{principal}' nao tem '{capability.value}'{scope}")

    def grants_for(self, principal: str) -> list[Grant]:
        return [g for g in self._grants if g.principal == principal]
