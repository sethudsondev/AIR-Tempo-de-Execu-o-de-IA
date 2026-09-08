"""
SecureData Central -- servidor MCP (unica parte que conhece o protocolo).

Camada FINA: registra tools/resources/prompt e delega para sdc.mcp.adapter,
onde a logica de verdade mora (100% testavel sem MCP).

stdio: stdout e o canal JSON-RPC. NENHUM print() vai para stdout -- todo
log vai para stderr via logging. Rodar:  python -m sdc.mcp.server
"""
from __future__ import annotations

import json
import logging
import sys

from mcp.server.mcpserver import MCPServer
from mcp.types import ToolAnnotations

from sdc import tokens
from sdc.config import load_config
from sdc.mcp.adapter import Adapter

config = load_config()

logging.basicConfig(
    level=getattr(logging, config.log_level, logging.INFO),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    stream=sys.stderr,   # nunca stdout
)
logger = logging.getLogger("sdc.mcp.server")

adapter = Adapter(config)

READ_ONLY = ToolAnnotations(read_only_hint=True, destructive_hint=False, idempotent_hint=True, open_world_hint=False)
WRITE = ToolAnnotations(read_only_hint=False, destructive_hint=False, idempotent_hint=False, open_world_hint=False)
WRITE_IDEMPOTENT = ToolAnnotations(read_only_hint=False, destructive_hint=False, idempotent_hint=True, open_world_hint=False)
DESTRUCTIVE = ToolAnnotations(read_only_hint=False, destructive_hint=True, idempotent_hint=False, open_world_hint=False)

server = MCPServer(
    name="securedata",
    title="SecureData Central -- Memoria e Contexto",
    description=(
        "Camada externa de memoria, estado e contexto persistente para agentes. "
        "Nao substitui o contexto interno do modelo: complementa consultando "
        "fatos persistidos (Memory), estado atual de entidades com historico "
        "(World State) e eventos, e reconstruindo contexto minimo sob demanda "
        "respeitando um orcamento de tokens. Fala apenas com um SQLite local; "
        "nao acessa rede nem le nenhum secret."
    ),
    instructions=(
        "Antes de reconstruir contexto do zero ou pedir algo que o usuario "
        "ja informou antes, chame sdc_search_context (barato) para ver se ja "
        "existe. Para o fluxo completo (relevancia + recencia + orcamento de "
        "tokens), chame sdc_get_context.\n\n"
        "Quando o usuario disser um fato duravel sobre o projeto/preferencia/"
        "decisao, grave com sdc_store_memory usando uma 'key' estavel (ex: "
        "project.name, user.tone). Mudou? sdc_update_memory cria versao nova "
        "sem perder a anterior.\n\n"
        "Estado de sistema que muda no tempo (status, versao, ambiente) vai "
        "em sdc_update_world_state -- ele guarda o valor anterior, quando "
        "mudou e a origem; consulte com sdc_get_world_state / sdc_world_history.\n\n"
        "Sempre que a sessao tiver um projeto identificavel, passe "
        "project=<nome> nas tools que aceitam -- sem isso o registro fica "
        "GLOBAL (visivel a qualquer projeto).\n\n"
        "sdc_delete_memory nao tem desfazer (soft-delete, mas sem tool de "
        "restauracao) -- confirme antes se a intencao nao for inequivoca. "
        "Toda contagem de token declara o 'method' (tiktoken ou heuristica) "
        "-- nao assuma mais precisao do que o metodo entrega."
    ),
    version="0.1.0",
)


# ============================ MEMORY ============================

@server.tool(title="Guardar memoria", annotations=WRITE)
def sdc_store_memory(
    key: str,
    content: str,
    type: str = "note",
    source: str = "agent",
    importance: str = "medium",
    project: str = "",
    metadata: dict | None = None,
) -> dict:
    """Grava um fato/informacao duravel. 'key' e a chave estavel (ex:
    project.name). Se ja existir memoria ativa nessa key+project com o
    MESMO conteudo, nada e criado (dedup). Se o conteudo for diferente, a
    versao antiga vira 'superseded' e a nova nasce com version+1.
    importance: low | medium | high | critical (usada pelo Context Engine)."""
    return adapter.store_memory(key, content, type=type, source=source,
                                importance=importance, project=project, metadata=metadata)


@server.tool(title="Buscar memoria por id ou key", annotations=READ_ONLY)
def sdc_get_memory(id: str = "", key: str = "", project: str = "") -> dict:
    """Recupera uma memoria. Informe 'id' OU 'key' (+ project opcional).
    Por key, retorna so a versao ativa."""
    return adapter.get_memory(id=id or None, key=key or None, project=project)


@server.tool(title="Pesquisar memorias", annotations=READ_ONLY)
def sdc_search_memory(query: str, limit: int = 5, project: str = "") -> dict:
    """Busca por palavra-chave em key + conteudo + tipo. Score transparente
    (fracao de termos + importancia + recencia). Retorna as mais relevantes."""
    return adapter.search_memory(query, limit=limit, project=project)


@server.tool(title="Atualizar memoria", annotations=WRITE)
def sdc_update_memory(id: str, content: str = "", importance: str = "", type: str = "") -> dict:
    """Cria uma nova versao (supersede) de uma memoria ATIVA. Campos vazios
    mantem o valor atual."""
    return adapter.update_memory(
        id,
        content=content or None,
        importance=importance or None,
        type=type or None,
    )


@server.tool(title="Excluir memoria (sem desfazer)", annotations=DESTRUCTIVE)
def sdc_delete_memory(id: str) -> dict:
    """Soft-delete: marca a memoria como 'deleted' (a linha continua no
    banco para auditoria), mas NAO ha tool de restauracao."""
    return adapter.delete_memory(id)


@server.tool(title="Historico de uma memoria", annotations=READ_ONLY)
def sdc_memory_history(key: str, project: str = "") -> dict:
    """Todas as versoes (inclusive superseded/deleted) de uma key -- para
    ver como uma informacao evoluiu."""
    return adapter.memory_history(key, project=project)


# ========================= WORLD STATE =========================

@server.tool(title="Atualizar estado do mundo", annotations=WRITE_IDEMPOTENT)
def sdc_update_world_state(
    entity_type: str, entity_id: str, attribute: str, value: str, source: str = "agent"
) -> dict:
    """Define (entity_type, entity_id, attribute) = value. Se o valor mudou,
    o anterior e FECHADO (valid_until = agora) e uma linha nova e aberta --
    o historico fica preservado. Reenviar o mesmo valor e no-op."""
    return adapter.update_world_state(entity_type, entity_id, attribute, value, source=source)


@server.tool(title="Consultar estado do mundo", annotations=READ_ONLY)
def sdc_get_world_state(entity_type: str, entity_id: str, attribute: str = "") -> dict:
    """Sem 'attribute': devolve todos os atributos atuais da entidade.
    Com 'attribute': devolve o valor atual + o valor anterior (se houve mudanca)."""
    return adapter.get_world_state(entity_type, entity_id, attribute or None)


@server.tool(title="Historico de um atributo", annotations=READ_ONLY)
def sdc_world_history(entity_type: str, entity_id: str, attribute: str) -> dict:
    """Linha do tempo completa de um atributo: cada valor, de quando ate
    quando valeu, e a origem."""
    return adapter.world_history(entity_type, entity_id, attribute)


# ============================ EVENTS ============================

@server.tool(title="Registrar evento", annotations=WRITE)
def sdc_record_event(
    event_type: str, entity_id: str = "", payload: dict | None = None,
    project: str = "", source: str = "agent",
) -> dict:
    """Anota um acontecimento no log append-only (ex: deploy, incidente,
    decisao). Consulte com sdc_recent_changes."""
    return adapter.record_event(event_type, entity_id=entity_id, payload=payload,
                                project=project, source=source)


@server.tool(title="Mudancas recentes", annotations=READ_ONLY)
def sdc_recent_changes(limit: int = 20, event_type: str = "", project: str = "") -> dict:
    """Ultimos eventos (memoria criada/atualizada, estado mudou, eventos
    manuais), mais novos primeiro. Responde 'o que mudou recentemente'."""
    return adapter.recent_changes(limit=limit, event_type=event_type or None, project=project)


# =========================== CONTEXT ===========================

@server.tool(title="Buscar contexto relevante", annotations=READ_ONLY)
def sdc_search_context(query: str, limit: int = 5, project: str = "") -> dict:
    """Retrieval cru: candidatos de Memory + World State + Events pontuados
    para a query, sem montar contexto nem cortar por token. Use para
    descobrir SE existe algo relevante antes de sdc_get_context."""
    return adapter.search_context(query, limit=limit, project=project)


@server.tool(title="Reconstruir contexto (com orcamento de tokens)", annotations=READ_ONLY)
def sdc_get_context(
    query: str, max_tokens: int = 0, project: str = "", session_id: str = "default"
) -> dict:
    """Fluxo completo: retrieval -> ranking (relevancia, recencia,
    importancia, continuidade da sessao) -> corte pelo orcamento de tokens
    -> texto compacto + referencias + contabilidade honesta de token.
    max_tokens=0 usa o padrao do servidor (SDC_MAX_CONTEXT_TOKENS)."""
    return adapter.get_context(query, max_tokens=max_tokens or None, project=project, session_id=session_id)


@server.tool(title="Status do servidor", annotations=READ_ONLY)
def sdc_status() -> dict:
    """Diagnostico: caminho do banco, migrations aplicadas, contagens,
    configuracao efetiva. Nenhum secret e exposto."""
    return adapter.status()


# ========================== RESOURCES ==========================

@server.resource("sdc://memory/active", name="Memorias ativas", mime_type="application/json")
def resource_memories() -> str:
    return json.dumps(adapter.snapshot_memories(), ensure_ascii=False, indent=2)


@server.resource("sdc://world/state", name="Estado do mundo + eventos recentes", mime_type="application/json")
def resource_world() -> str:
    return json.dumps(adapter.snapshot_world(), ensure_ascii=False, indent=2)


# =========================== PROMPT ============================

@server.prompt(name="reconstruct_context")
def reconstruct_context(query: str) -> str:
    return (
        f"Preciso retomar o contexto sobre: {query}\n\n"
        "1. Chame sdc_get_context com essa consulta (e project=<nome> se houver).\n"
        "2. Use 'context' como base; 'references' mostra a origem de cada item.\n"
        "3. Recencia ja resolve conflito -- o valor mais novo de uma key/atributo "
        "e o que vale. sdc_world_history / sdc_memory_history mostram o anterior "
        "se precisar entender a evolucao.\n"
        "4. Se faltar algo, sdc_search_memory / sdc_recent_changes antes de "
        "perguntar de novo ao usuario."
    )


def main() -> None:
    if not config.mcp_enabled:
        logger.warning("SDC_MCP_ENABLED=false -- encerrando sem iniciar o servidor.")
        return
    tokens.warm_async()  # carrega o tokenizer em background, nunca bloqueia
    logger.info("SecureData Central MCP -- storage=%s", config.db_path)
    server.run(transport="stdio")


if __name__ == "__main__":
    main()
