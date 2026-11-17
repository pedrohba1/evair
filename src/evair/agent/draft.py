"""Rascunho de nota extraído pelo LLM + mapeamento para o modelo DPS.

``DraftNota`` é o alvo de saída estruturada do LLM: só os campos de alto
nível que um humano informa em linguagem natural. ``to_dps`` preenche o
resto (prestador, regime, tributação, série) a partir da configuração do
emissor, reusando o modelo Pydantic da Etapa 1.

Atenção: o XSD exige o endereço do tomador (``endNac`` com cMun+CEP e os
irmãos xLgr/nro/xBairro) — por isso o rascunho também coleta esses campos.
"""
from __future__ import annotations

import json
import re
from datetime import date
from typing import Literal, cast

from pydantic import BaseModel, Field

from ..config import EmissorConfig
from ..nfse.models import (
    DPS, Prestador, RegimeTributario, Servico, Tomador, Valores,
)

# Código de serviço LC 116 usado quando o LLM não resolve um específico.
# Deve ser tratado como "a confirmar" — não como um padrão seguro.
COD_TRIB_NACIONAL_PADRAO = "010301"


class DraftNota(BaseModel):
    """Rascunho de alto nível. Campos obrigatórios ficam vazios se faltarem."""

    tomador_cnpj: str = Field(default="", description="CNPJ do tomador, 14 dígitos")
    tomador_razao_social: str = Field(default="", description="Razão social do tomador")
    tomador_cod_municipio: str = Field(default="", description="IBGE do tomador (7 díg.)")
    tomador_cep: str = Field(default="", description="CEP do tomador (8 díg.)")
    tomador_logradouro: str = Field(default="", description="Logradouro do tomador")
    tomador_numero: str = Field(default="", description="Número do endereço")
    tomador_bairro: str = Field(default="", description="Bairro do tomador")
    descricao_servico: str = Field(default="", description="Descrição do serviço")
    cod_trib_nacional: str | None = Field(default=None, description="Código LC 116 (6 díg.)")
    valor_servico: str = Field(default="", description="Valor do serviço, ex. 2500.00")
    data_competencia: str = Field(default="", description="AAAA-MM-DD")


def normalizar_valor(valor: str) -> str:
    """Normaliza uma string de valor para o formato decimal "####.##".

    Aceita "2500", "2500.00", "R$ 2.500,00", "2.500,50", "2500,5", etc.
    """
    if not valor:
        return ""
    s = valor.strip().upper().replace("R$", "")
    # Milhares com ponto, decimais com vírgula (padrão BR).
    if "," in s:
        s = s.replace(".", "").replace(",", ".")
    # Remove qualquer símbolo restante, mantendo dígitos e ponto.
    s = re.sub(r"[^0-9.]", "", s)
    if not s:
        return ""
    try:
        n = float(s)
    except ValueError:
        return ""
    return f"{n:.2f}"


def _so_digitos(s: str | None) -> str:
    """Remove tudo que não for dígito (CNPJ, CEP etc. vêm formatados)."""
    return re.sub(r"\D", "", s or "")


def campos_faltando(draft: DraftNota) -> list[str]:
    """Devolve perguntas em pt-BR para os campos obrigatórios ausentes."""
    perguntas: list[str] = []
    if not draft.tomador_cnpj:
        perguntas.append("Qual é o CNPJ do tomador do serviço?")
    if not draft.tomador_razao_social:
        perguntas.append("Qual é a razão social do tomador?")
    if not draft.descricao_servico:
        perguntas.append("Qual é a descrição do serviço prestado?")
    if not normalizar_valor(draft.valor_servico):
        perguntas.append("Qual é o valor do serviço?")
    if not draft.data_competencia:
        perguntas.append("Qual é a data de competência (AAAA-MM-DD)?")
    if not draft.tomador_cod_municipio:
        perguntas.append("Qual é o município (código IBGE) do tomador?")
    if not draft.tomador_cep:
        perguntas.append("Qual é o CEP do endereço do tomador?")
    if not draft.tomador_logradouro:
        perguntas.append("Qual é o logradouro (rua/avenida) do tomador?")
    if not draft.tomador_numero:
        perguntas.append("Qual é o número do endereço do tomador?")
    if not draft.tomador_bairro:
        perguntas.append("Qual é o bairro do tomador?")
    return perguntas


def to_dps(draft: DraftNota, cfg: EmissorConfig, *, n_dps: str = "1",
           serie: str = "00001") -> DPS:
    """Converte o rascunho em DPS completa usando a configuração do emissor."""
    cod_trib = draft.cod_trib_nacional or COD_TRIB_NACIONAL_PADRAO
    valor = normalizar_valor(draft.valor_servico) or "0.00"
    return DPS(
        ambiente=cast(Literal[1, 2], cfg.ambiente),
        serie=serie,
        n_dps=n_dps,
        data_competencia=date.fromisoformat(draft.data_competencia),
        cod_municipio_emissor=cfg.cod_municipio,
        prestador=Prestador(
            cnpj=cfg.cnpj,
            inscricao_municipal=cfg.inscricao_municipal,
            regime=RegimeTributario(),
        ),
        tomador=Tomador(
            cnpj=_so_digitos(draft.tomador_cnpj),
            razao_social=draft.tomador_razao_social,
            cod_municipio=_so_digitos(draft.tomador_cod_municipio) or None,
            cep=_so_digitos(draft.tomador_cep) or None,
            logradouro=draft.tomador_logradouro or None,
            numero=draft.tomador_numero or None,
            bairro=draft.tomador_bairro or None,
        ),
        servico=Servico(
            cod_trib_nacional=cod_trib,
            descricao=draft.descricao_servico,
            cod_local_prestacao=cfg.cod_municipio,
        ),
        valores=Valores(v_serv=valor),
    )


def _extrair_json(texto: str) -> dict:
    """Extrai o primeiro objeto JSON de uma resposta (tolerante a markdown)."""
    t = texto.strip()
    # remove fences ```json ... ```
    if t.startswith("```"):
        t = re.sub(r"^```[a-zA-Z]*\s*", "", t)
        t = re.sub(r"\s*```$", "", t)
    inicio = t.find("{")
    fim = t.rfind("}")
    if inicio == -1 or fim == -1 or fim < inicio:
        raise ValueError("resposta do modelo não contém um objeto JSON")
    return json.loads(t[inicio : fim + 1])


def extrair_draft(llm, conversa: str) -> DraftNota:
    """Pede ao LLM um JSON com o rascunho e valida via Pydantic.

    Não usa ``with_structured_output`` porque o endpoint OpenAI-compatível do
    ollama-cloud não honra ``response_format``/function-calling; pedimos JSON
    explícito e parseamos de forma tolerante. Se o modelo não devolver JSON
    utilizável, retorna um DraftNota vazio (o agente então pergunta tudo).
    """
    exemplo = json.dumps(
        {
            "tomador_cnpj": "", "tomador_razao_social": "",
            "tomador_cod_municipio": "", "tomador_cep": "",
            "tomador_logradouro": "", "tomador_numero": "", "tomador_bairro": "",
            "descricao_servico": "", "cod_trib_nacional": None,
            "valor_servico": "", "data_competencia": "",
        },
        ensure_ascii=False,
    )
    prompt = (
        "Você extrai os dados de uma nota fiscal de serviço (NFS-e) de uma "
        "conversa em português.\n"
        "Responda APENAS com um objeto JSON válido, exatamente neste formato "
        "(sem texto antes ou depois):\n"
        f"{exemplo}\n\n"
        "Preencha os campos que conseguir inferir. Deixe string vazia ('') ou "
        "null no que não souber. valor_servico em decimal simples "
        "(ex. '2500.00'). data_competencia em AAAA-MM-DD. Não invente CNPJ, "
        "razão social, valores nem datas.\n\n"
        f"Conversa:\n{conversa}"
    )
    resp = llm.invoke(prompt)
    texto = resp.content if hasattr(resp, "content") else str(resp)
    try:
        data = _extrair_json(texto)
        return DraftNota.model_validate(data)
    except Exception:
        # Degradação graciosa: rascunho vazio -> o agente pergunta tudo.
        return DraftNota()
