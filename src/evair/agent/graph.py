"""Grafo do agente: interpreta -> aprova (interrupt) -> emite.

Nós:
  interpretar  — chama o LLM para extrair um DraftNota da conversa.
  revisar      — pausa com interrupt() para o humano aprovar/rejeitar.
  emitir       — converte o rascunho em DPS e emite via Sefin Nacional.
  responder    — nó terminal que só normaliza a saída.

Fluxo de controle:
  START -> interpretar
  interpretar -> (faltam campos) -> END (devolve perguntas)
  interpretar -> (draft completo) -> revisar
  revisar (interrupt) -> aprovado? -> emitir -> END
                       -> rejeitado? -> interpretar (com feedback)

O grafo é compilado com um MemorySaver (em memória, sem persistência em
disco), chaveado por ``thread_id`` fornecido pelo frontend — coerente com a
regra "nada salvo no backend; tudo no navegador".
"""
from __future__ import annotations

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt

from ..config import EmissorConfig
from ..emissao import emitir as emitir_dps
from .draft import DraftNota, campos_faltando, extrair_draft, normalizar_valor, to_dps
from .llm import get_llm
from .state import AgentState


def _interpretar(state: AgentState) -> dict:
    llm = get_llm()
    texto = "\n".join(
        f"{m['role']}: {m['content']}" for m in state.get("messages", [])
    )
    draft = extrair_draft(llm, texto)
    draft.valor_servico = normalizar_valor(draft.valor_servico)
    return {
        "draft": draft.model_dump(),
        "perguntas": campos_faltando(draft),
        "aprovado": None,
        "resultado": None,
        "erro": None,
    }


def _revisar(state: AgentState) -> dict:
    """Pausa e espera a decisão humana (aprovado=True/False + feedback)."""
    decisao = interrupt({"draft": state.get("draft")})
    aprovado = bool(decisao.get("aprovado"))
    update: dict = {"aprovado": aprovado, "feedback": decisao.get("feedback")}
    if not aprovado:
        # Anexa o feedback como mensagem do usuário (o reducer acumula) para a
        # re-extração levar em conta o que mudou.
        fb = decisao.get("feedback") or "Revise o rascunho."
        update["messages"] = [{"role": "user", "content": f"[revisão] {fb}"}]
    return update


def _emitir(state: AgentState, cfg: EmissorConfig, bundle_provider) -> dict:
    draft = DraftNota(**(state.get("draft") or {}))
    try:
        dps = to_dps(draft, cfg)
        bundle = bundle_provider()
        resultado = emitir_dps(dps, cfg, bundle)
    except Exception as exc:  # pragma: no cover - tratamento defensivo
        # to_dps também fica aqui: campo formatado/ausente vira erro limpo,
        # em vez de derrubar a requisição (500 -> "Failed to fetch").
        return {"resultado": None, "erro": f"falha ao montar/emitir: {exc}"}
    if not resultado.get("ok"):
        return {"resultado": None, "erro": str(resultado.get("erros"))}
    return {"resultado": resultado, "erro": None}


def _responder(state: AgentState) -> dict:
    return {}


def _rota_apos_interpretar(state: AgentState) -> str:
    if state.get("perguntas"):
        return "end"
    return "revisar"


def _rota_apos_revisar(state: AgentState) -> str:
    if state.get("aprovado"):
        return "emitir"
    # Rejeição: volta a interpretar com o feedback anexado (feito em _revisar).
    return "interpretar"


def build_graph(cfg: EmissorConfig, bundle_provider):
    """Compila o grafo com o MemorySaver (estado em memória)."""
    g = StateGraph(AgentState)

    g.add_node("interpretar", _interpretar)
    g.add_node("revisar", _revisar)
    g.add_node("emitir", lambda s: _emitir(s, cfg, bundle_provider))
    g.add_node("responder", _responder)

    g.add_edge(START, "interpretar")
    g.add_conditional_edges(
        "interpretar", _rota_apos_interpretar,
        {"end": END, "revisar": "revisar"},
    )
    g.add_conditional_edges(
        "revisar", _rota_apos_revisar,
        {"emitir": "emitir", "interpretar": "interpretar"},
    )
    g.add_edge("emitir", "responder")
    g.add_edge("responder", END)

    return g.compile(checkpointer=MemorySaver())


__all__ = ["build_graph", "Command"]
