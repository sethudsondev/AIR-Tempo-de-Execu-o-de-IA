# Changelog

## 0.1.0 -- 2026-09-08

Primeira versao. Camada de memoria/estado/contexto persistente via MCP + SQLite.

- SQLite com migrations versionadas (`schema_migrations`).
- Memory: store/get/search/update/delete, recencia por supersede, dedup, historico.
- World State: entity/attr/value com versionamento temporal (valid_from/valid_until).
- Events: log append-only.
- Context Engine: retrieval de 3 fontes + ranking + orcamento de tokens + handles.
- Servidor MCP (stdio): 14 tools, 2 resources, 1 prompt, ToolAnnotations honestas.
- SDK em processo: `MemoryAgent`.
- Seguranca: validacao/limites, SQL 100% parametrizado, sem secrets, erros estruturados.
- Docker: imagem + volume /data persistente.
- 72 testes (unittest), todos passando so com requirements.txt.
