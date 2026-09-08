"""
Demo: persistencia entre "sessoes".

1. Sessao A grava uma memoria + um estado de mundo num arquivo SQLite.
2. Sessao B abre O MESMO arquivo (adapter novo) e recupera tudo so
   consultando -- sem receber nada de historico.

Rode:  python examples/demo_mcp.py
"""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sdc.config import Config
from sdc.mcp.adapter import Adapter

DB = Path(tempfile.gettempdir()) / "sdc_demo.db"


def cleanup():
    for p in DB.parent.glob("sdc_demo.db*"):
        try:
            p.unlink()
        except OSError:
            pass


def adapter_for(path: Path) -> Adapter:
    cfg = Config()
    cfg.db_path = path
    cfg.ensure_storage_dir()
    return Adapter(cfg)


cleanup()

print("== SESSAO A: grava ==")
a = adapter_for(DB)
print(" store_memory :", a.store_memory("project.name", "SecureData Central",
                                        type="project_information", importance="high")["outcome"])
print(" world_state  :", a.update_world_state("project", "securedata-central", "status",
                                              "development", source="briefing")["outcome"])
print(" event        :", a.record_event("kickoff", entity_id="project:securedata-central",
                                        payload={"fase": "1"})["ok"])
a.close()

print("\n== SESSAO B: abre o MESMO arquivo e consulta ==")
b = adapter_for(DB)
print(" nome do projeto :", b.get_memory(key="project.name")["memory"]["content"])
print(" status atual    :", b.get_world_state("project", "securedata-central", "status")["current"]["value"])
ctx = b.get_context("qual o nome e o status do projeto SecureData", session_id="sess-b")
print(f"\n contexto reconstruido ({ctx['tokens_used']} tokens, {ctx['token_method']}):")
print(ctx["context"])
print("\n referencias:", [r["label"] for r in ctx["references"]])
b.close()

cleanup()
