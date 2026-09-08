"""
SecureData Central -- configuracao por variavel de ambiente.

Regra do projeto: NENHUM secret (API key, senha, token) e lido, usado ou
gravado aqui. Este servidor so fala com o SQLite local. Toda configuracao
sensivel de qualquer consumidor deve vir do ambiente dele, nunca daqui.
"""
from __future__ import annotations

import os
from pathlib import Path

# Raiz do projeto (pasta que contem sdc/, tests/, ...). O servidor MCP
# pode ser iniciado com qualquer cwd, entao caminhos default sao
# ancorados aqui, nao no diretorio de trabalho.
ROOT = Path(__file__).resolve().parent.parent


def _bool_env(name: str, default: bool) -> bool:
    val = os.environ.get(name)
    if val is None:
        return default
    return val.strip().lower() in ("1", "true", "yes", "on")


def _int_env(name: str, default: int) -> int:
    val = os.environ.get(name)
    if val is None or not val.strip():
        return default
    try:
        return max(0, int(val))
    except ValueError:
        return default


def _resolve_db_path() -> Path:
    """Ordem de precedencia:
      1. SDC_DB_PATH  (caminho direto)
      2. DATABASE_URL (aceita 'sqlite:///caminho' ou 'sqlite:////abs')
      3. default: <ROOT>/storage/securedata.db
    ':memory:' e repassado como esta (usado em teste)."""
    direct = os.environ.get("SDC_DB_PATH", "").strip()
    if direct:
        return Path(direct) if direct != ":memory:" else Path(":memory:")

    url = os.environ.get("DATABASE_URL", "").strip()
    if url.startswith("sqlite:"):
        raw = url.split("sqlite:", 1)[1].lstrip("/")
        # sqlite:////data/x.db -> /data/x.db ; sqlite:///data/x.db -> data/x.db
        if url.startswith("sqlite:////"):
            raw = "/" + raw
        if raw == "memory:" or raw == ":memory:":
            return Path(":memory:")
        return Path(raw)

    return ROOT / "storage" / "securedata.db"


class Config:
    """Le o ambiente uma vez, na construcao -- comportamento previsivel
    dentro de um mesmo processo."""

    def __init__(self) -> None:
        self.db_path: Path = _resolve_db_path()

        self.mcp_enabled: bool = _bool_env("SDC_MCP_ENABLED", _bool_env("MCP_ENABLED", True))
        self.log_level: str = os.environ.get(
            "SDC_LOG_LEVEL", os.environ.get("LOG_LEVEL", "INFO")
        ).strip().upper()

        # Orcamento de contexto do Context Engine.
        self.max_context_tokens: int = _int_env(
            "SDC_MAX_CONTEXT_TOKENS", _int_env("MAX_CONTEXT_TOKENS", 2000)
        )

        # Limites de validacao de entrada (seguranca).
        self.max_content_chars: int = _int_env("SDC_MAX_CONTENT_CHARS", 20_000)
        self.max_key_chars: int = _int_env("SDC_MAX_KEY_CHARS", 200)
        self.max_query_chars: int = _int_env("SDC_MAX_QUERY_CHARS", 1_000)
        self.max_metadata_bytes: int = _int_env("SDC_MAX_METADATA_BYTES", 8_192)
        self.default_search_limit: int = _int_env("SDC_DEFAULT_SEARCH_LIMIT", 5)
        self.max_search_limit: int = _int_env("SDC_MAX_SEARCH_LIMIT", 50)

        # Feature opcional, desligada por padrao.
        self.enable_semantic_search: bool = _bool_env("SDC_ENABLE_SEMANTIC_SEARCH", False)

    @property
    def is_memory_db(self) -> bool:
        return str(self.db_path) == ":memory:"

    def ensure_storage_dir(self) -> None:
        if self.is_memory_db:
            return
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

    def as_dict(self) -> dict:
        return {
            "db_path": str(self.db_path),
            "mcp_enabled": self.mcp_enabled,
            "log_level": self.log_level,
            "max_context_tokens": self.max_context_tokens,
            "max_content_chars": self.max_content_chars,
            "max_query_chars": self.max_query_chars,
            "default_search_limit": self.default_search_limit,
            "enable_semantic_search": self.enable_semantic_search,
        }


def load_config() -> Config:
    """Fabrica -- use em vez de instanciar Config() direto, para os testes
    conseguirem forcar o ambiente antes da leitura."""
    return Config()
