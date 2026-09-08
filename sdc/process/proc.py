"""
SecureData Central -- execucao de comando (casca fina).

Mais restrito que o equivalente do AIR de proposito: SEM shell=True e com
ALLOWLIST de binarios. Adequado para comandos locais confiaveis do proprio
runtime -- NAO para rodar codigo arbitrario gerado por LLM (para isso, um
adapter de sandbox de verdade). A seguranca de "quem pode executar" vem
de sdc/tools/registry.py + Capability.EXECUTE.
"""
from __future__ import annotations

import shlex
import subprocess

DEFAULT_ALLOWLIST = frozenset({"git", "python", "python3", "pytest", "ls", "cat", "echo", "node", "npm"})


class ProcError(Exception):
    pass


def run_command(
    command: str | list[str],
    *,
    timeout: float = 30.0,
    allowlist: frozenset[str] | set[str] = DEFAULT_ALLOWLIST,
    cwd: str | None = None,
) -> str:
    argv = shlex.split(command) if isinstance(command, str) else list(command)
    if not argv:
        raise ProcError("comando vazio")
    binary = argv[0].rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
    if binary not in allowlist:
        raise ProcError(f"binario nao permitido: {binary} (allowlist: {sorted(allowlist)})")
    try:
        result = subprocess.run(  # noqa: S603 -- argv, sem shell
            argv, capture_output=True, text=True, timeout=timeout, cwd=cwd, check=False
        )
    except subprocess.TimeoutExpired as exc:
        raise ProcError(f"comando excedeu {timeout}s") from exc
    if result.returncode != 0:
        raise ProcError(f"codigo {result.returncode}: {result.stderr.strip()[:500]}")
    return result.stdout
