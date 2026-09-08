"""
SecureData Central -- Verification Engine.

Decide se uma acao teve sucesso SEMANTICO, nao so mecanico (a chamada nao
lancou excecao != a acao funcionou).

Default e uma heuristica fraca DE PROPOSITO (erro explicito -> FAILED;
output vazio -> UNKNOWN; resto -> OK). O valor real vem de registrar
verificadores especificos por tool que checam efeito observavel de
verdade (ex: "o world state mudou como esperado?"). Padrao
Reason-Act-VERIFY-Observe.
"""
from __future__ import annotations

from typing import Callable

from sdc.core.types import ActionResult, Verification, VerificationOutcome, new_id

Verifier = Callable[[ActionResult], "tuple[VerificationOutcome, str]"]


def default_heuristic_verifier(result: ActionResult) -> tuple[VerificationOutcome, str]:
    if result.error:
        return VerificationOutcome.FAILED, f"erro reportado pela acao: {result.error}"
    if result.output is None or result.output == "":
        return VerificationOutcome.UNKNOWN, "sem erro, mas sem output verificavel"
    return VerificationOutcome.OK, "sem erro e com output (heuristica fraca -- registre um verificador especifico)"


def expect_substring(text: str) -> Verifier:
    """Verificador simples: OK se `text` aparece no output (str)."""
    def _v(result: ActionResult) -> tuple[VerificationOutcome, str]:
        if result.error:
            return VerificationOutcome.FAILED, result.error
        if isinstance(result.output, str) and text in result.output:
            return VerificationOutcome.OK, f"output contem '{text}'"
        return VerificationOutcome.FAILED, f"output nao contem '{text}'"
    return _v


class VerificationEngine:
    def __init__(self) -> None:
        self._verifiers: dict[str, Verifier] = {}

    def register(self, tool_name: str, verifier: Verifier) -> None:
        self._verifiers[tool_name] = verifier

    def verify(self, result: ActionResult) -> Verification:
        verifier = self._verifiers.get(result.tool_name, default_heuristic_verifier)
        outcome, detail = verifier(result)
        return Verification(id=new_id("ver"), action_result_id=result.id, outcome=outcome, detail=detail)
