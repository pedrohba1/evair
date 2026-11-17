"""Agente LangGraph do EVAIR (Etapa 2).

Fluxo: interpreta o pedido em linguagem natural -> monta um rascunho da DPS
-> pausa para aprovação humana (interrupt) -> emite via Sefin Nacional.

A chave privada nunca entra no estado do grafo; é injetada por um provider
apenas no nó de emissão, sob demanda.
"""
