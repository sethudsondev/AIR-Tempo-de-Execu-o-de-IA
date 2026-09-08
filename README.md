# SecureData Central

Camada de **memoria + estado + contexto persistente** para agentes/LLM,
exposta por **MCP** (Model Context Protocol) sobre **SQLite**.

Princípio (do briefing, inspirado no projeto [AIR](https://github.com/tvost2/air)):

> Informação persistente e estruturada **não** deve ser reenviada como
> tokens ao LLM a cada interação.

O agente consulta o que precisa quando precisa, em vez de receber todo o
histórico de novo. Três camadas **separadas de propósito**:

| Camada | O que guarda | Exemplo |
|---|---|---|
| **Memory** | fatos/decisões/preferências discretas, com recência e importância | `project.name = "SecureData Central"` |
| **World State** | estado atual de entidades, **versionado no tempo** | `project:sdc.status: development → production` (com histórico) |
| **Events** | log append-only de acontecimentos | `deploy`, `incidente`, `user.stated` |

O **Context Engine** junta tudo e monta o contexto mínimo para uma
consulta, respeitando um **orçamento de tokens**.

---

## Instalação

```bash
git clone https://github.com/sethudsondev/securedatacentral.git
cd securedatacentral
pip install -r requirements.txt        # só o pacote 'mcp'
```

Opcional (cada bloco liga uma feature, ver `requirements-optional.txt`):

```bash
pip install -r requirements-optional.txt   # tiktoken, busca semântica, pytest
```

## Rodar

```bash
# testes (72, só precisam do requirements.txt)
python -m unittest discover -s tests -p "test_*.py"

# demos
python examples/demo_mcp.py     # persistência entre "sessões"
python examples/demo_agent.py   # padrão de uso do SDK em processo

# servidor MCP (stdio) — normalmente iniciado pelo cliente, não à mão
python -m sdc.mcp.server
```

## Configurar no Claude Code / Cursor

`.mcp.json` (já incluído):

```json
{
  "mcpServers": {
    "securedata": {
      "command": "python",
      "args": ["-m", "sdc.mcp.server"],
      "env": { "SDC_DB_PATH": "storage/securedata.db", "SDC_MAX_CONTEXT_TOKENS": "2000" }
    }
  }
}
```

## Configuração (env)

Todas opcionais — ver `.env.example`.

| Variável | Default | O que faz |
|---|---|---|
| `SDC_DB_PATH` / `DATABASE_URL` | `./storage/securedata.db` | caminho do SQLite (`DATABASE_URL` aceita `sqlite:////data/x.db`) |
| `SDC_MCP_ENABLED` | `true` | liga/desliga o servidor MCP |
| `SDC_MAX_CONTEXT_TOKENS` | `2000` | orçamento do Context Engine |
| `SDC_LOG_LEVEL` | `INFO` | log (vai para **stderr**) |
| `SDC_MAX_CONTENT_CHARS` | `20000` | limite de tamanho de conteúdo |
| `SDC_MAX_QUERY_CHARS` | `1000` | limite de tamanho de query |
| `SDC_MAX_METADATA_BYTES` | `8192` | limite do JSON de metadata |
| `SDC_ENABLE_SEMANTIC_SEARCH` | `false` | busca semântica (requer pacote opcional) |

**Nenhum secret é lido, usado ou gravado.** O servidor só fala com o
SQLite local — não acessa rede.

---

## Ferramentas MCP

| Tool | Tipo | O que faz |
|---|---|---|
| `sdc_store_memory(key, content, type, source, importance, project, metadata)` | write | grava um fato; dedup por conteúdo; supersede na mudança |
| `sdc_get_memory(id \| key, project)` | read | recupera uma memória (versão ativa por key) |
| `sdc_search_memory(query, limit, project)` | read | busca por palavra-chave (score transparente) |
| `sdc_update_memory(id, content, importance, type)` | write | cria nova versão (supersede) |
| `sdc_delete_memory(id)` | **destructive** | soft-delete (sem tool de restauração) |
| `sdc_memory_history(key, project)` | read | todas as versões de uma key |
| `sdc_update_world_state(entity_type, entity_id, attribute, value, source)` | write | define estado; fecha o valor anterior e abre um novo |
| `sdc_get_world_state(entity_type, entity_id, attribute?)` | read | valor atual (+ anterior); ou todos os atributos da entidade |
| `sdc_world_history(entity_type, entity_id, attribute)` | read | linha do tempo de um atributo |
| `sdc_record_event(event_type, entity_id, payload, project, source)` | write | anota um acontecimento |
| `sdc_recent_changes(limit, event_type, project)` | read | "o que mudou recentemente" |
| `sdc_search_context(query, limit, project)` | read | retrieval cru (Memory + World + Events pontuados) |
| `sdc_get_context(query, max_tokens, project, session_id)` | read | contexto mínimo montado, respeitando orçamento de tokens |
| `sdc_status()` | read | diagnóstico (sem expor secrets) |

**Resources:** `sdc://memory/active`, `sdc://world/state`
**Prompt:** `reconstruct_context`

### Exemplos de chamada

```jsonc
// "Meu sistema se chama SecureData Central."
sdc_store_memory({ "key": "project.name", "content": "SecureData Central",
                   "type": "project_information", "importance": "high" })

// "Fomos para produção."
sdc_update_world_state({ "entity_type": "project", "entity_id": "sdc",
                         "attribute": "status", "value": "production", "source": "deploy" })
// -> { ok: true, outcome: "changed", previous: { value: "development", ... } }

// "Continue o trabalho de ontem."
sdc_get_context({ "query": "continuar o trabalho no projeto sdc",
                  "project": "sdc", "session_id": "dia-2", "max_tokens": 1500 })
```

---

## Banco SQLite

Um arquivo, quatro tabelas + `schema_migrations`. Migrations versionadas
em `sdc/db/migrations.py` (idempotentes; nunca editar as antigas).

| Tabela | Colunas principais |
|---|---|
| `memories` | id, key, content, type, source, importance, project, **status**, **version**, supersedes, created_at, updated_at, metadata |
| `world_state` | id, entity_type, entity_id, attribute, value, version, **valid_from**, **valid_until**, source, updated_at |
| `context_refs` | id, session_id, memory_id, relevance, created_at, metadata |
| `events` | id, event_type, entity_id, payload, project, source, timestamp |

- **Recência (Memory):** 1 linha `active` por `(key, project)` (índice único parcial). Mudar = a antiga vira `superseded`, a nova nasce com `version+1`.
- **Versionamento temporal (World State):** mudar um valor fecha a linha atual (`valid_until = agora`) e abre outra. A linha vigente é a de `valid_until IS NULL`.

---

## Docker

```bash
docker compose build
docker compose --profile test run --rm sdc-tests    # roda os 72 testes
```

O banco fica no volume `sdc_data` montado em `/data` — o container pode
ser recriado sem perder nada (`SDC_DB_PATH=/data/securedata.db`).

---

## Segurança

- **Toda** entrada passa por `sdc/security/guard.py`: limites de tamanho, charset da `key`, metadata JSON válida e dentro do limite de bytes, `limit` sempre "clampado".
- **SQL injection:** toda query usa placeholders parametrizados — nunca concatenação. Teste dedicado (`tests/test_security.py`) grava `"'; DROP TABLE memories; --"` como dado e confirma que a tabela continua de pé.
- Erros nunca vazam stacktrace nem detalhe de SQLite para o cliente — viram `{ ok: false, error, code }`.
- **Nenhum secret no código nem em `.env.example`.** O servidor não acessa rede.
- Isolamento por `project`: registro sem `project` é global; com `project` fica escopado.
- Anotações MCP honestas (`destructive_hint` em `sdc_delete_memory`, `read_only_hint` nas de leitura) para o cliente decidir se pede confirmação.

---

## Arquitetura

Ver [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — inclui o que veio do
AIR (arquitetura em camadas, adapter/server separados, recência por
supersede, contagem de token honesta, isolamento por `project`,
`ToolAnnotations`) e o que é específico deste projeto (schema do briefing,
World State com `valid_from`/`valid_until`, `context_refs` por sessão,
migrations versionadas, `MemoryAgent` SDK).

## Testes

```
python -m unittest discover -s tests -p "test_*.py"
```

72 testes: `test_db`, `test_memory`, `test_world_state`, `test_events`,
`test_context`, `test_adapter`, `test_mcp`, `test_persistence`,
`test_security`. Todos só precisam do `requirements.txt`.

## Troubleshooting

| Sintoma | Causa provável | Solução |
|---|---|---|
| `ModuleNotFoundError: No module named 'sdc'` | rodando de fora da raiz | `cd` na raiz do repo, ou `pip install -e .` |
| `ModuleNotFoundError: No module named 'mcp'` | dependência não instalada | `pip install -r requirements.txt` |
| cliente MCP não conecta | `command`/`cwd` errados no `.mcp.json` | usar caminho absoluto do `python` e do repo |
| token_method sempre `heuristic_chars_div_4` | `tiktoken` não instalado | opcional; `pip install tiktoken` para contagem exata |
| dados sumiram ao recriar o container | `SDC_DB_PATH` fora do volume | apontar para `/data/...` (volume `sdc_data`) |
