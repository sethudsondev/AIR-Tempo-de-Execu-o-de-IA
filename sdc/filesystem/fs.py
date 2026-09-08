"""
SecureData Central -- operacoes de arquivo (casca fina).

Pensado para registrar como tools via sdc/tools/registry.py, que aplica
Capability.FILESYSTEM por caminho. Aqui ha um confinamento adicional
opcional a um diretorio-raiz -- defesa em profundidade, nao substitui a
checagem de capacidade.
"""
from __future__ import annotations

from pathlib import Path


class FsError(Exception):
    pass


def _resolved(path: str, root: str | Path | None) -> Path:
    p = Path(path).expanduser().resolve()
    if root is not None:
        r = Path(root).expanduser().resolve()
        if r not in p.parents and p != r:
            raise FsError(f"caminho fora da raiz permitida ({root}): {path}")
    return p


def read_file(path: str, *, root: str | Path | None = None, max_bytes: int = 1_000_000) -> str:
    p = _resolved(path, root)
    data = p.read_bytes()
    if len(data) > max_bytes:
        raise FsError(f"arquivo maior que o limite ({max_bytes} bytes)")
    return data.decode("utf-8", errors="replace")


def write_file(path: str, content: str, *, root: str | Path | None = None) -> str:
    p = _resolved(path, root)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return f"escrito {len(content)} chars em {p}"


def list_dir(path: str, *, root: str | Path | None = None) -> str:
    p = _resolved(path, root)
    return "\n".join(sorted(e.name + ("/" if e.is_dir() else "") for e in p.iterdir()))
