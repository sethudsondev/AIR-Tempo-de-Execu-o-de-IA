# Arquitetura — SecureData Central

## Camadas (fluxo)

```
Cliente MCP (Claude Code / Cursor)
        │  stdio (JSON-RPC)
        ▼
sdc/mcp/server.py      ← ÚNICO módulo que conhece o protocolo MCP
        │  str / int / dict
        ▼
sdc/mcp/adapter.py     ← validação (guard) + orquestração + tratamento de erro
        │
        ├──────────────┬───────────────┬──────────────┐
        ▼              ▼               ▼              ▼
 sdc/memory/     sdc/world/      sdc/events/    sdc/context/
  store.py        state.py         log.py        retrieval.py + engine.py
        │              │               │              │
        └──────────────┴───────────────┴──────────────┘
                       ▼
                sdc/db/connection.py  (+ migrations.py)
                       ▼
                   SQLite (1 arquivo)
```

`sdc/agent.py` (`MemoryAgent`) é uma fachada alternativa: usa o **mesmo
adapter** em processo, sem MCP, para backends que embutem o SDC direto.

## Responsabilidade de cada módulo

| Módulo | Responsabilidade | Não faz |
|---|---|---|
| `config.py` | ler env uma vez; resolver caminho do banco | ler qualquer secret |
| `core/types.py` | dataclasses (`Memory`, `WorldFact`, `ContextRef`, `Event`) | I/O |
| `db/connection.py` | conexão SQLite (WAL, FK, lock), helpers parametrizados | lógica de domínio |
| `db/migrations.py` | migrations versionadas + `schema_migrations` | — |
| `memory/store.py` | fatos discretos, recência por supersede, dedup, busca | estado temporal |
| `world/state.py` | estado de entidade versionado (`valid_from`/`valid_until`) | preferências/fatos soltos |
| `events/log.py` | log append-only | edição/remoção |
| `context/retrieval.py` | candidatos pontuados de Memory + World + Events | cortar por token |
| `context/engine.py` | ranking + orçamento de tokens + handles (`put`/`get`) | acessar o banco de domínio direto (usa o retriever) |
| `security/guard.py` | validação/sanitização de entrada | "escapar SQL" (isso é papel do placeholder) |
| `tokens.py` | contagem honesta (tiktoken ou heurística, sempre com `method`) | — |
| `mcp/adapter.py` | validar → chamar núcleo → `{ok, ...}` / `{ok:false, error, code}` | conhecer MCP |
| `mcp/server.py` | registrar tools/resources/prompt, `run(stdio)` | lógica de domínio |
| `security/permissions.py` | capability grants, allowlist/deny-by-default | validar formato (é o `guard.py`) |
| `events/bus.py` | pub/sub **efêmero** em processo (coordenação) | persistir (é o `events/log.py`) |
| `verification/engine.py` | sucesso **semântico** de uma ação (OK/FAILED/**UNKNOWN**) | executar a ação |
| `planner/planner.py` | executar grafo de tasks com dependência + verificação por passo | resolver planejamento automático |
| `tools/registry.py` | tool call → checa capacidade → roteia output grande p/ Context Engine | protocolo de tool (é MCP) |
| `models/provider.py` | abstração de LLM (`EchoProvider`, `LiteLLMProvider` opcional) | ser chamado pelo núcleo (só o SDK usa) |
| `filesystem/fs.py`, `process/proc.py` | operações de arquivo/comando (casca fina) — confinamento + allowlist | isolamento real (seria um adapter de sandbox) |
| `adapters/semantic_search.py` | embeddings via `sentence-transformers` (opt-in) | ligar por padrão |
| `sdk/agent.py` | fachada `Agent` que fia tudo | — |

## Decisões-chave

### Recência (Memory)
`(key, project)` tem no máximo **uma** linha `active` (índice único
parcial `uq_mem_active_key`). `store()` com conteúdo diferente marca a
anterior `superseded` e insere `version+1` com `supersedes` apontando
para a antiga. `history(key)` devolve tudo, em ordem de versão. Não há
sobrescrita destrutiva — dá para auditar a evolução.

### Versionamento temporal (World State)
Cada `(entity_type, entity_id, attribute)` é uma sequência de linhas.
A vigente tem `valid_until IS NULL`. `set()` com valor novo faz
`UPDATE ... SET valid_until = agora` na vigente e `INSERT` da nova.
`previous()` = penúltima por `version`. Responde: valor atual, valor
anterior, quando mudou, qual a origem.

### Context Engine — orçamento de tokens
`build(query, max_tokens, session_id)`:
1. `retriever.retrieve()` → candidatos de 3 fontes, já pontuados.
2. bônus leve para memórias já usadas nesta `session_id` (continuidade —
   lido de `context_refs`).
3. loop guloso por score: renderiza cada candidato, conta tokens; se
   estoura, tenta versão compacta; se ainda estoura e já há itens, descarta
   (`dropped_for_budget++`); se é o primeiro item, trunca para caber.
4. grava `context_refs (session_id, memory_id, relevance)` para as
   memórias que entraram.
5. retorna texto + `references` estruturado + contabilidade honesta
   (`tokens_used`, `token_method`, `budget`, `candidates_considered`,
   `dropped_for_budget`).

### Sessões
`context_refs` amarra `session_id → memory_id`. Não transforma conversa
em memória permanente automaticamente — só o que passa por
`sdc_store_memory` / `sdc_update_world_state` / `sdc_record_event` persiste.
A "memória de sessão" é justamente o rastro em `context_refs` + o
histórico de eventos daquele período.

### Contagem de token honesta
`tokens.count_tokens()` devolve `{"tokens", "method"}`. Com `tiktoken`
instalado: `tiktoken:cl100k_base`. Sem: `heuristic_chars_div_4`. Nunca se
afirma "tokens" sem dizer como foram contados. Warmup em background no
startup; `count_tokens` nunca bloqueia esperando o encoder.

### Isolamento por `project`
`project=""` = global (aparece em qualquer busca). `project="x"` ao
gravar escopa; ao buscar, considera `x` **mais** os globais. Evita
contaminação cross-projeto num storage compartilhado.

## O que veio do AIR (conceito) vs. específico daqui (implementação)

| Do AIR (arquitetura/ideia) | Específico deste projeto |
|---|---|
| Camadas separadas: World State ≠ Memory ≠ Context | Schema do briefing (`memories`/`world_state`/`context_refs`/`events` com as colunas pedidas) |
| Split `adapter.py` (sem MCP) / `server.py` (só MCP) | `MemoryAgent` (SDK em processo) |
| Recência por supersede, soft-delete | Índice único parcial garantindo 1 ativa por key |
| `ToolAnnotations` honestas, `instructions` do servidor | World State com `valid_from`/`valid_until` (AIR usa entity/relation/event) |
| Contagem de token com `method` reportado, warmup async | `context_refs` por `session_id` |
| Isolamento por `project` | Migrations versionadas com `schema_migrations` |
| Dependência mínima (`mcp`), extras opcionais com fallback | `tiktoken` no lugar de `transformers` para contagem (mais leve) |
| Nenhum secret no servidor MCP | `DATABASE_URL` estilo `sqlite:///` além de `SDC_DB_PATH` |

Não foi copiado código do AIR — o `mcp_server/` do AIR é Python com a
mesma família de SDK, mas as classes de domínio, o schema e o Context
Engine aqui foram escritos para o schema deste briefing.

## Paridade de módulos com o AIR

O `sdc/` cobre a mesma superfície do AIR:

| AIR | SecureData Central |
|---|---|
| `world/state.py` | `sdc/world/state.py` (temporal em vez de grafo) |
| `memory/store.py` | `sdc/memory/store.py` |
| `context/engine.py` | `sdc/context/engine.py` + `sdc/context/retrieval.py` |
| `events/bus.py` | `sdc/events/bus.py` |
| (`world.event`) | `sdc/events/log.py` (log durável separado) |
| `security/permissions.py` | `sdc/security/permissions.py` (+ `guard.py` p/ input) |
| `verification/engine.py` | `sdc/verification/engine.py` |
| `planner/planner.py` | `sdc/planner/planner.py` |
| `tools/registry.py` | `sdc/tools/registry.py` |
| `models/provider.py` | `sdc/models/provider.py` |
| `filesystem/fs.py`, `process/proc.py` | idem (com allowlist mais estrita) |
| `adapters/semantic_search.py` | `sdc/adapters/semantic_search.py` |
| `mcp_server/{server,adapter,config,tokens}.py` | `sdc/mcp/{server,adapter}.py`, `sdc/config.py`, `sdc/tokens.py` |
| `sdk/agent.py` | `sdc/sdk/agent.py` (+ `sdc/agent.py` = `MemoryAgent` enxuto) |
| `kakeya_index.py` (índice de bisseção) | **não portado** — busca linear é suficiente no volume esperado; ponto de otimização futuro |
| `benchmarks/`, `scripts/install_mcp.py`, `.github/workflows` | idem |
