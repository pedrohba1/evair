"""Factory do modelo LLM usado pelo agente.

Um único provider (OpenAI-compatible) cobre Ollama local, ollama-cloud,
OpenAI e DeepSeek — basta apontar base_url/model/api_key via variáveis de
ambiente. Isso evita dependências de provider específico por escolha.
"""
from __future__ import annotations

import os
from functools import lru_cache


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


@lru_cache(maxsize=1)
def get_llm():
    """Retorna um ChatModel configurável por ambiente.

    Variáveis:
      EV_LLM_BASE_URL   (default http://localhost:11434/v1)
      EV_LLM_MODEL      (default "qwen2.5")
      EV_LLM_API_KEY    (default "ollama")
      EV_LLM_TEMPERATURE(default "0")
    """
    from langchain_openai import ChatOpenAI

    return ChatOpenAI(
        model=_env("EV_LLM_MODEL", "qwen2.5"),
        base_url=_env("EV_LLM_BASE_URL", "http://localhost:11434/v1"),
        api_key=_env("EV_LLM_API_KEY", "ollama"),
        temperature=float(_env("EV_LLM_TEMPERATURE", "0")),
    )
