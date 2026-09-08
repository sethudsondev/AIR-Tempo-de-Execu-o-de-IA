"""
SecureData Central -- contagem de token honesta.

Se `tiktoken` estiver instalado (requirements-optional.txt), usa ele.
Senao, cai para a heuristica len(texto)//4. O metodo usado e SEMPRE
reportado no campo "method" da resposta -- nunca se afirma "tokens" sem
dizer como foram contados.

O primeiro carregamento do encoder pode ser lento; o servidor dispara
warm_async() no startup e count_tokens() nunca bloqueia esperando por ele.
"""
from __future__ import annotations

import threading

_ENCODING_NAME = "cl100k_base"
_encoder = None
_load_failed = False
_lock = threading.Lock()


def _get_encoder(blocking: bool):
    global _encoder, _load_failed
    if _encoder is not None or _load_failed:
        return _encoder
    acquired = _lock.acquire(blocking=blocking)
    if not acquired:
        return None
    try:
        if _encoder is not None or _load_failed:
            return _encoder
        try:
            import tiktoken

            _encoder = tiktoken.get_encoding(_ENCODING_NAME)
        except Exception:
            _load_failed = True
            _encoder = None
    finally:
        _lock.release()
    return _encoder


def warm_async() -> threading.Thread:
    t = threading.Thread(target=_get_encoder, args=(True,), daemon=True, name="sdc-tokenizer-warmup")
    t.start()
    return t


def count_tokens(text: str) -> dict:
    """Retorna {'tokens': int, 'method': str}."""
    if not text:
        return {"tokens": 0, "method": "empty"}
    enc = _get_encoder(blocking=False)
    if enc is not None:
        try:
            return {"tokens": len(enc.encode(text)), "method": f"tiktoken:{_ENCODING_NAME}"}
        except Exception:
            pass
    return {"tokens": max(1, len(text) // 4), "method": "heuristic_chars_div_4"}


def count(text: str) -> int:
    return count_tokens(text)["tokens"]
