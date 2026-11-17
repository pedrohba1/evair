"""Estado do grafo do agente.

O estado é um dict simples (TypedDict). As mensagens são guardadas como
dicts ``{"role": "user"|"assistant", "content": str}`` — sem objetos do
langchain, para simplificar a serialização através do interrupt/resume.

``messages`` usa um reducer de acumulação: cada mensagem nova de uma mesma
``thread_id`` é SOMADA às anteriores (contexto da conversa) em vez de
substituí-las — sem isso o LLM só enxergaria a última mensagem.
"""
from __future__ import annotations

from typing import Annotated, Any, TypedDict


def _acumular_mensagens(existentes: list, novas: list) -> list:
    """Reducer: anexa as mensagens novas às já existentes (contexto)."""
    return list(existentes or []) + list(novas or [])


class AgentState(TypedDict, total=False):
    messages: Annotated[list[dict[str, str]], _acumular_mensagens]
    # Rascunho da nota extraído pelo LLM (dict serializável do DraftNota).
    draft: dict[str, Any] | None
    # Perguntas ao usuário quando faltam campos obrigatórios.
    perguntas: list[str]
    # Preenchido no nó de aprovação (interrupt) com o resultado do resume.
    aprovado: bool | None
    feedback: str | None
    # Resultado da emissão (dict serializável).
    resultado: dict[str, Any] | None
    erro: str | None
