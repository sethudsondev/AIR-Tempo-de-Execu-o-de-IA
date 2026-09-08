"""SDK do SecureData Central.

    from sdc.sdk import Agent, MemoryAgent

- Agent       : fachada completa (tools, permissoes, planner, verification, model).
- MemoryAgent : enxuta -- so memoria/estado/contexto (sdc.agent).
"""
from sdc.agent import MemoryAgent
from sdc.sdk.agent import Agent

__all__ = ["Agent", "MemoryAgent"]
