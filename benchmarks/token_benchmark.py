"""
Benchmark: quanto de token o SDC economiza quando a memoria acumulada e
GRANDE e a maior parte NAO e relevante para o turno atual.

  A) "sem SDC"  -- reenviar TODA a memoria como texto a cada turno.
  B) "com SDC"  -- so o contexto minimo montado por sdc_get_context.

O ganho aparece quando (1) ha muita informacao acumulada e (2) so uma
fracao interessa a pergunta do turno. Com pouca memoria toda relevante,
o naive e mais barato -- e esperado, o benchmark deixa isso explicito.

Rode:  python benchmarks/token_benchmark.py [N_TURNOS]
"""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sdc.config import Config
from sdc.mcp.adapter import Adapter
from sdc.tokens import count_tokens

N = int(sys.argv[1]) if len(sys.argv) > 1 else 20

DB = Path(tempfile.gettempdir()) / "sdc_bench.db"


def clean():
    for p in DB.parent.glob("sdc_bench.db*"):
        try:
            p.unlink()
        except OSError:
            pass


clean()
cfg = Config()
cfg.db_path = DB
cfg.max_context_tokens = 500
cfg.ensure_storage_dir()
a = Adapter(cfg)

# Memoria de projeto real: notas LONGAS, varios topicos. A pergunta de
# cada turno e sempre sobre DEPLOY -- so ~1/6 da memoria interessa.
def note(topic: str, detail: str) -> str:
    return (
        f"[{topic}] {detail}. Contexto adicional registrado ao longo das "
        f"sessoes anteriores, com decisoes, alternativas descartadas e o "
        f"porque de cada escolha, do jeito que uma nota de projeto real "
        f"cresce -- varias linhas que so importam quando o assunto e {topic}."
    )

TOPICS = {
    "deploy": ["Docker com volume /data", "VPS sa-east-1, rollback por tag git", "healthcheck em /status", "blue-green por container"],
    "auth": ["JWT HS256 TTL 8h", "cookie HttpOnly SameSite Lax", "rate limit 6/10min", "reset por e-mail assinado"],
    "ui": ["paleta roxo/azul/dourado", "Poppins + Nunito", "tema claro e escuro", "drawer lateral no mobile"],
    "db": ["Postgres 17", "RLS ligado sem policy default", "migrations versionadas", "indice parcial p/ ativo"],
    "seo": ["sitemap.xml", "OG image 1200x630", "JSON-LD LocalBusiness", "canonical por pagina"],
    "billing": ["Asaas gateway", "webhook assinado", "3x sem juros", "conciliacao diaria"],
}
flat = [(t, i, note(t, txt)) for t, items in TOPICS.items() for i, txt in enumerate(items)]

naive_total = sdc_total = 0
for turn in range(1, N + 1):
    if turn <= len(flat):
        t, i, txt = flat[turn - 1]
        a.store_memory(f"{t}.fact{i}", txt, type=t, importance="medium")

    history = "\n".join(f"- {m['key']}: {m['content']}" for m in a.snapshot_memories()["memories"])
    naive_total += count_tokens(history)["tokens"]

    ctx = a.get_context("o que sei sobre o deploy do projeto", session_id="bench")
    sdc_total += ctx["tokens_used"]

saved = naive_total - sdc_total
pct = (saved / naive_total * 100) if naive_total else 0.0
print(f"turnos                : {N}")
print(f"metodo de contagem    : {count_tokens('x')['method']}")
print(f"memorias no fim        : {a.status()['memories_active']}")
print(f"tokens SEM SDC (soma)  : {naive_total}")
print(f"tokens COM SDC (soma)  : {sdc_total}")
print(f"economia              : {saved:+d} tokens ({pct:+.0f}%)")

a.close()
clean()
