"""
SecureData Central -- adapter de busca semantica (OPCIONAL, desligado por
padrao).

Adota tech madura (sentence-transformers) em vez de reimplementar
embeddings. Sem o pacote instalado OU sem SDC_ENABLE_SEMANTIC_SEARCH=true,
o retrieval (sdc/context/retrieval.py) usa so palavra-chave -- reportado
no campo 'method' de cada candidato.

O primeiro import de sentence_transformers e pesado; is_available() nao o
dispara -- so o primeiro rank() de verdade.
"""
from __future__ import annotations

_model = None
_tried = False
MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"


def is_available() -> bool:
    try:
        import sentence_transformers  # noqa: F401
        import numpy  # noqa: F401
        return True
    except ImportError:
        return False


def _get_model():
    global _model, _tried
    if _tried:
        return _model
    _tried = True
    try:
        from sentence_transformers import SentenceTransformer
        _model = SentenceTransformer(MODEL_NAME)
    except Exception:
        _model = None
    return _model


def rank(query: str, documents: list[str], *, limit: int, min_score: float = 0.15) -> list[tuple[int, float]]:
    """Retorna [(indice_do_documento, score)] ordenado por score desc.
    Lista vazia se o modelo nao estiver disponivel -- quem chama cai para
    palavra-chave."""
    model = _get_model()
    if model is None or not documents or not query.strip():
        return []
    import numpy as np

    q = model.encode([query], normalize_embeddings=True)
    d = model.encode(documents, normalize_embeddings=True)
    sims = (d @ q.T).ravel()
    order = np.argsort(-sims)[:limit]
    return [(int(i), float(sims[i])) for i in order if sims[i] >= min_score]
