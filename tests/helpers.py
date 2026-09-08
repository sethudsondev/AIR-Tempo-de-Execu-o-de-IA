"""Utilitarios compartilhados pelos testes."""
from __future__ import annotations

import sys
from pathlib import Path

# Garante que 'import sdc...' funcione rodando os testes direto.
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sdc.db.connection import Database  # noqa: E402


def fresh_db() -> Database:
    """Banco SQLite em memoria, ja migrado."""
    return Database(":memory:")
