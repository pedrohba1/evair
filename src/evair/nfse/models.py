"""Modelos Pydantic da DPS (Declaração de Prestação de Serviços).

Espelham o leiaute do Anexo I / XSD v1.01 do Sistema Nacional NFS-e.
Nomes de campo em português, alinhados ao XML, para minimizar erro de
tradução. O campo ``n_dps`` guarda o número "cru" (sem zero à esquerda);
o Id da DPS é montado com ``n_dps`` zerado à esquerda em 15 posições.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field

# ---- Constantes / códigos ----

AMBIENTE_PRODUCAO = 1
AMBIENTE_HOMOLOGACAO = 2

# Tipo de inscrição federal no Id da DPS (regra oficial Sefin/ADN):
#   1 = CPF, 2 = CNPJ  (atenção: ordem diferente da NF-e!)
TP_INSCRICAO_CPF = "1"
TP_INSCRICAO_CNPJ = "2"


class RegimeTributario(BaseModel):
    """Regimes de tributação do prestador (grupo ``regTrib``)."""

    op_simples_nacional: Literal["1", "2", "3"] = "1"  # 1=Não Optante, 2=MEI, 3=ME/EPP
    # regApTribSN: só preencher quando opSimpNac = 3 (ME/EPP).
    reg_ap_trib_sn: Literal["1", "2", "3"] | None = None
    reg_esp_trib: str = "0"  # 0 = Nenhum


class Prestador(BaseModel):
    cnpj: str = Field(min_length=14, max_length=14)
    inscricao_municipal: str | None = None
    razao_social: str | None = None
    telefone: str | None = None
    email: str | None = None
    regime: RegimeTributario = Field(default_factory=RegimeTributario)


class Tomador(BaseModel):
    """Tomador do serviço. Para o MVP, CNPJ obrigatório (pode evoluir p/ CPF/NIF)."""

    cnpj: str = Field(min_length=14, max_length=14)
    razao_social: str
    cod_municipio: str | None = None  # IBGE do tomador (se nacional)
    cep: str | None = None
    logradouro: str | None = None
    numero: str | None = None
    bairro: str | None = None


class Servico(BaseModel):
    cod_trib_nacional: str = Field(min_length=6, max_length=6)  # cTribNac (LC 116)
    cod_trib_municipal: str | None = None  # cTribMun (opcional)
    descricao: str = Field(min_length=1, max_length=2000)  # xDescServ
    cod_nbs: str | None = None
    cod_local_prestacao: str  # IBGE do município onde o serviço foi prestado


class TributacaoMunicipal(BaseModel):
    trib_issqn: str = "1"
    # 1 = não retido (prestador recolhe); 2 = retido pelo tomador; 3 = intermediário
    tp_ret_issqn: str = "1"
    # Alíquota % (0-1 casas). Omitir (None) quando o prestador é não optante
    # do Simples e o município de incidência está ATIVO no ADN (regra E0617).
    p_aliq: str | None = None


class Piscofins(BaseModel):
    cst: str = "07"
    v_bc_pis_cofins: str = "0.00"
    p_aliq_pis: str = "0.00"
    p_aliq_cofins: str = "0.00"
    v_pis: str = "0.00"
    v_cofins: str = "0.00"
    tp_ret_pis_cofins: str = "2"


class Tributacao(BaseModel):
    municipal: TributacaoMunicipal = Field(default_factory=TributacaoMunicipal)
    piscofins: Piscofins = Field(default_factory=Piscofins)
    # Percentuais aproximados do total de tributos (Lei 12.741/2012).
    # Para NÃO optante do Simples (opSimpNac=1), o grupo totTrib usa pTotTrib —
    # a regra E0713 proíbe indTotTrib/pTotTribSN. Ajuste p/ percentuais reais.
    p_tot_trib_fed: str = "0.00"
    p_tot_trib_est: str = "0.00"
    p_tot_trib_mun: str = "0.00"


class Valores(BaseModel):
    v_serv: str  # valor do serviço, ex. "2500.00"
    tributos: Tributacao = Field(default_factory=Tributacao)


class DPS(BaseModel):
    """Rascunho da DPS — o que o agente monta e o usuário revisa/aprova."""

    ambiente: Literal[1, 2] = AMBIENTE_HOMOLOGACAO
    data_emissao: datetime | None = None  # dhEmi; se None, usa "agora"
    serie: str = "00001"  # 5 dígitos (API usa 00001..49999)
    n_dps: str  # número cru, sem zero à esquerda (ex. "1")
    data_competencia: date  # dCompet (AAAA-MM-DD)
    tp_emitente: str = "1"  # 1 = prestador
    fin_nfse: str = "0"  # finalidade: 0=regular, 1=crédito, 2=débito (NT 009)
    ind_dest: str = "0"  # destinatário: 0=o próprio tomador, 1=outro (NT 009)
    cod_municipio_emissor: str  # IBGE do município emissor (conveniado)
    prestador: Prestador
    tomador: Tomador | None = None
    servico: Servico
    valores: Valores
