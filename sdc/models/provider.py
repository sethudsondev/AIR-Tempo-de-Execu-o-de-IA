"""
SecureData Central -- abstracao de model provider.

O SDC nao chama LLM para funcionar (memoria/estado/contexto sao puros
SQLite). Este modulo existe so para o SDK (`sdc.sdk.Agent`) conseguir
montar um prompt com o contexto reconstruido e completar. Providers:

  - EchoProvider  -- sem dependencia, deterministico, para teste/demo.
  - LiteLLMProvider -- opcional; 100+ backends (OpenAI, Anthropic, Ollama
    local...). Import TARDIO de proposito; se litellm nao estiver
    instalado, levanta erro claro so quando alguem tentar usar.

NENHUMA chave de API e lida aqui -- quem instanciar um provider remoto
passa a config pelo ambiente do proprio processo (padrao do litellm).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass
class Completion:
    text: str
    model: str
    method: str


class ModelProvider(Protocol):
    def complete(self, prompt: str, *, model: str = "default", max_tokens: int = 512) -> Completion: ...


class EchoProvider:
    """Devolve um resumo deterministico do prompt -- util para testar o
    fluxo (o contexto certo chegou?) sem custo nem rede."""

    def complete(self, prompt: str, *, model: str = "default", max_tokens: int = 512) -> Completion:
        # ecoa o prompt (contexto + pergunta) para dar para verificar num
        # teste que o contexto certo chegou -- nao e um "modelo" de verdade.
        snippet = prompt.strip()
        if len(snippet) > 600:
            snippet = snippet[:600] + " ..."
        return Completion(
            text=f"[echo] contexto+pergunta recebidos ({len(prompt)} chars):\n{snippet}",
            model="echo",
            method="echo",
        )


class LiteLLMProvider:
    def __init__(self, default_model: str = "gpt-4o-mini") -> None:
        self.default_model = default_model

    def complete(self, prompt: str, *, model: str = "default", max_tokens: int = 512) -> Completion:
        try:
            import litellm
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError(
                "LiteLLMProvider requer 'pip install litellm' (nao esta em requirements.txt)"
            ) from exc
        chosen = self.default_model if model == "default" else model
        resp = litellm.completion(
            model=chosen,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=max_tokens,
        )
        return Completion(text=resp["choices"][0]["message"]["content"], model=chosen, method="litellm")
