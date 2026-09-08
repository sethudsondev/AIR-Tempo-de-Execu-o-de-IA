"""
Demo: o padrao de uso do MemoryAgent (SDK em processo, sem MCP).

Simula turnos de conversa mostrando QUANDO chamar cada operacao -- sem
LLM, so a mecanica.

Rode:  python examples/demo_agent.py
"""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sdc.agent import MemoryAgent
from sdc.config import Config

DB = Path(tempfile.gettempdir()) / "sdc_agent_demo.db"


def cleanup():
    for p in DB.parent.glob("sdc_agent_demo.db*"):
        try:
            p.unlink()
        except OSError:
            pass


cleanup()
cfg = Config()
cfg.db_path = DB
cfg.ensure_storage_dir()
agent = MemoryAgent(cfg)

print('turno 1  usuario: "Meu sistema se chama SecureData Central."')
agent.remember("project.name", "SecureData Central", type="project_information",
               importance="high", project="sdc")
agent.log_event("user.stated", payload={"about": "project.name"}, project="sdc")

print('turno 2  usuario: "Estamos em desenvolvimento ainda."')
agent.set_state("project", "sdc", "status", "development", source="user")

print('turno 3  usuario: "Continue o trabalho de ontem."')
ctx = agent.context("continuar o trabalho no projeto", project="sdc", session_id="dia-2")
print("  -> o agente consulta o contexto persistente ANTES de responder:\n")
print(ctx["context"])

print('\n(mais tarde) usuario: "Fomos para producao."')
r = agent.set_state("project", "sdc", "status", "production", source="deploy")
print("  status:", r["previous"]["value"], "->", r["fact"]["value"])
print("  historico:", [f["value"] for f in agent.state_history("project", "sdc", "status")["history"]])

agent._adapter.close()
cleanup()
