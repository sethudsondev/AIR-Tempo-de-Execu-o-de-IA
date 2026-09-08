"""
SecureData Central -- validacao e sanitizacao de entrada.

Responsabilidades:
  - limites de tamanho (conteudo, chave, query, metadata);
  - metadata precisa ser JSON-serializavel e dentro do limite de bytes;
  - normalizacao de string (strip, colapsa espaco, remove controle);
  - clamp de limites numericos.

O que NAO e responsabilidade daqui (feito na camada de dados):
  - SQL injection -- toda query usa placeholders parametrizados, nunca
    concatenacao. Este modulo nao "escapa SQL" porque isso seria o
    padrao errado.
"""
from __future__ import annotations

import json
import re

_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_WS_RUN = re.compile(r"[ \t]{2,}")


class ValidationError(ValueError):
    """Entrada invalida -- vira erro estruturado na resposta da tool."""


def clean_text(value: object, *, field: str, max_chars: int, allow_empty: bool = False) -> str:
    if value is None:
        value = ""
    if not isinstance(value, (str, int, float, bool)):
        raise ValidationError(f"{field}: tipo invalido ({type(value).__name__}), esperado texto")
    text = str(value)
    text = _CONTROL_CHARS.sub("", text)
    text = text.replace("\r\n", "\n").strip()
    text = _WS_RUN.sub(" ", text)
    if not text and not allow_empty:
        raise ValidationError(f"{field}: obrigatorio")
    if len(text) > max_chars:
        raise ValidationError(f"{field}: excede o limite de {max_chars} caracteres (tem {len(text)})")
    return text


def clean_key(value: object, *, max_chars: int) -> str:
    key = clean_text(value, field="key", max_chars=max_chars)
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.\-:/ ]*", key):
        raise ValidationError(
            "key: use letras, numeros e . _ - : / (deve comecar com letra ou numero)"
        )
    return key


def clean_identifier(value: object, *, field: str, max_chars: int = 200) -> str:
    ident = clean_text(value, field=field, max_chars=max_chars)
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.\-:/]*", ident):
        raise ValidationError(f"{field}: use letras, numeros e . _ - : /")
    return ident


def clean_metadata(value: object, *, max_bytes: int) -> dict:
    if value is None or value == "":
        return {}
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError as exc:
            raise ValidationError(f"metadata: JSON invalido ({exc.msg})")
    if not isinstance(value, dict):
        raise ValidationError("metadata: precisa ser um objeto/dicionario")
    try:
        encoded = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    except (TypeError, ValueError) as exc:
        raise ValidationError(f"metadata: nao e serializavel ({exc})")
    if len(encoded.encode("utf-8")) > max_bytes:
        raise ValidationError(f"metadata: excede {max_bytes} bytes")
    return value


def clamp_limit(value: object, *, default: int, maximum: int) -> int:
    if value is None or value == "":
        return default
    try:
        n = int(value)
    except (TypeError, ValueError):
        return default
    return max(1, min(n, maximum))


def clean_project(value: object) -> str:
    if value is None or value == "":
        return ""
    proj = clean_text(value, field="project", max_chars=120, allow_empty=True)
    if proj and not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.\- ]*", proj):
        raise ValidationError("project: use letras, numeros e . _ - espaco")
    return proj
