"""Testes do agente EVAIR (Etapa 2) — sem rede, sem LLM real.

Cobre:
  1. o pipeline determinístico (DraftNota -> DPS -> XML -> validação XSD ->
     assinatura -> verificação), com certificado gerado em memória;
  2. o fluxo do grafo LangGraph (interpretar -> interrupt -> emitir) usando
     um LLM fake e uma emissão fake.
"""
from __future__ import annotations

import base64
import datetime
import json

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from langgraph.types import Command

from evair.agent.draft import DraftNota, to_dps
from evair.agent.graph import build_graph
from evair.config import EmissorConfig
from evair.nfse import dps as dps_mod
from evair.nfse import sign as sign_mod


def _cfg() -> EmissorConfig:
    return EmissorConfig(
        ambiente=2,
        cnpj="39982868000170",
        inscricao_municipal=None,
        cod_municipio="3170206",
        ver_aplic="EVAIR_TESTE",
        cert_pfx=None,
        cert_senha="",
        url_homologacao="https://sefin.producaorestrita.nfse.gov.br/SefinNacional",
        url_producao="https://sefin.nfse.gov.br/SefinNacional",
    )


def _cert_teste() -> sign_mod.CertBundle:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "EVAIR TESTE")])
    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(days=1))
        .not_valid_after(now + datetime.timedelta(days=365))
        .sign(key, hashes.SHA256())
    )
    return sign_mod.CertBundle(
        key_pem=key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        ),
        cert_pem=cert.public_bytes(serialization.Encoding.PEM),
        cert_der_b64=base64.b64encode(
            cert.public_bytes(serialization.Encoding.DER)
        ).decode(),
    )


def _draft() -> DraftNota:
    return DraftNota(
        tomador_cnpj="99999999000191",
        tomador_razao_social="CLINICA ALFA LTDA",
        tomador_cod_municipio="3170206",
        tomador_cep="38400000",
        tomador_logradouro="AVENIDA EXEMPLO",
        tomador_numero="100",
        tomador_bairro="CENTRO",
        descricao_servico="Suporte tecnico de outubro.",
        cod_trib_nacional="010301",
        valor_servico="2500.00",
        data_competencia="2026-10-01",
    )


class _FakeResp:
    def __init__(self, content):
        self.content = content


class _FakeLLM:
    def __init__(self, draft: DraftNota):
        self._draft = draft

    def invoke(self, _prompt):
        # O grafo chama extrair_draft -> llm.invoke -> resp.content (JSON).
        return _FakeResp(json.dumps(self._draft.model_dump()))


def test_pipeline_deterministico():
    cfg = _cfg()
    draft = _draft()
    dps = to_dps(draft, cfg)

    xml = dps_mod.build_dps_xml(dps)

    # NT 009 release 1: finNFSe obrigatório no infDPS, após tpEmit e antes de
    # cLocEmi (o XSD público v1.01 ainda não reflete isso).
    texto = xml.decode("utf-8")
    assert "finNFSe" in texto
    assert texto.index("tpEmit") < texto.index("finNFSe") < texto.index("cLocEmi")

    bundle = _cert_teste()
    xml_assinado = sign_mod.sign_dps(xml, bundle)
    assert sign_mod.verify_dps_signature(xml_assinado, bundle.cert_pem) is True


def test_to_dps_normaliza_campos_formatados():
    """CNPJ/CEP com pontuação (ex. do LLM) devem virar só dígitos."""
    cfg = _cfg()
    draft = _draft()
    draft.tomador_cnpj = "12.345.678/0001-95"
    draft.tomador_cep = "38400-100"
    dps = to_dps(draft, cfg)
    assert dps.tomador.cnpj == "12345678000195"
    assert dps.tomador.cep == "38400100"


def test_id_dps_usa_tpinsc_cnpj():
    """Id da DPS deve usar tpInsc=2 para CNPJ (regra Sefin: 1=CPF, 2=CNPJ)."""
    cfg = _cfg()
    dps = to_dps(_draft(), cfg)
    xml = dps_mod.build_dps_xml(dps).decode()
    idd = xml.split('Id="')[1].split('"')[0]
    # DPS + cMun(7) + tpInsc(1) + inscrição(14) + série(5) + nDPS(15)
    assert idd[3:10] == "3170206"
    assert idd[10] == "2", "tpInsc deve ser 2 (CNPJ), não 1 (CPF)"
    assert idd[11:25] == "39982868000170"
    assert len(idd) == 45


def test_tributacao_nao_optante():
    """Não optante: totTrib usa pTotTrib (não indTotTrib), pAliq omitida,
    tpRetISSQN=1 (não retido). Regras E0617/E0713."""
    cfg = _cfg()
    dps = to_dps(_draft(), cfg)
    xml = dps_mod.build_dps_xml(dps).decode()
    # pAliq não deve ser informado (não optante + município ativo → E0617)
    assert "pAliq>" not in xml.replace("pAliqPis", "").replace("pAliqCofins", "")
    assert "pAliqPis" in xml  # PIS/COFINS mantêm seus campos
    # totTrib usa pTotTrib, não indTotTrib (E0713)
    assert "<totTrib><pTotTrib>" in xml or "pTotTribFed" in xml
    assert "indTotTrib" not in xml
    assert "pTotTribSN" not in xml
    # tpRetISSQN = 1 (não retido)
    assert "<tpRetISSQN>1</tpRetISSQN>" in xml


def test_grafo_fluxo_aprovacao(monkeypatch):
    cfg = _cfg()
    draft = _draft()

    monkeypatch.setattr("evair.agent.graph.get_llm", lambda: _FakeLLM(draft))
    # Emissão fake: nunca toca a rede nem precisa de certificado.
    monkeypatch.setattr(
        "evair.agent.graph.emitir_dps",
        lambda _dps, _cfg, _bundle: {
            "ok": True, "chave_acesso": "0" * 50, "id_dps": "DPS" + "0" * 42,
        },
    )

    graph = build_graph(cfg, bundle_provider=lambda: _cert_teste())
    tid = {"configurable": {"thread_id": "t1"}}

    # 1. mensagem inicial -> pausa no interrupt (aguardando aprovação).
    r1 = graph.invoke(
        {"messages": [{"role": "user", "content": "Nota de 2500 p/ Clinica Alfa"}]},
        config=tid,
    )
    snap1 = graph.get_state(tid)
    assert snap1.next, "deveria pausar aguardando aprovação"
    assert snap1.values["draft"]["tomador_razao_social"] == "CLINICA ALFA LTDA"

    # 2. aprovação -> emite e conclui.
    r2 = graph.invoke(
        Command(resume={"aprovado": True, "feedback": None}), config=tid
    )
    snap2 = graph.get_state(tid)
    assert not snap2.next, "deveria concluir após aprovação"
    assert r2["resultado"]["ok"] is True


def test_grafo_pede_dados_faltando(monkeypatch):
    cfg = _cfg()
    # Draft incompleto (sem valor e sem tomador) -> deve devolver perguntas.
    incompleto = DraftNota(descricao_servico="Suporte tecnico", data_competencia="2026-10-01")

    monkeypatch.setattr("evair.agent.graph.get_llm", lambda: _FakeLLM(incompleto))

    graph = build_graph(cfg, bundle_provider=lambda: _cert_teste())
    tid = {"configurable": {"thread_id": "t2"}}

    r = graph.invoke(
        {"messages": [{"role": "user", "content": "Nota de suporte"}]},
        config=tid,
    )
    snap = graph.get_state(tid)
    assert not snap.next, "não deve pausar para aprovação se faltam campos"
    assert r["perguntas"], "deveria listar perguntas sobre os campos ausentes"


def test_contexto_acumula_entre_mensagens(monkeypatch):
    """Uma 2ª mensagem na mesma thread deve ser interpretada com o contexto da 1ª."""
    cfg = _cfg()
    draft = _draft()

    capturados: list[str] = []

    class _FakeLLMCaptura(_FakeLLM):
        def invoke(self, prompt):
            capturados.append(prompt)
            return super().invoke(prompt)

    monkeypatch.setattr("evair.agent.graph.get_llm", lambda: _FakeLLMCaptura(draft))
    monkeypatch.setattr(
        "evair.agent.graph.emitir_dps",
        lambda _dps, _cfg, _bundle: {"ok": True, "chave_acesso": "0" * 50, "id_dps": "DPS" + "0" * 42},
    )

    graph = build_graph(cfg, bundle_provider=lambda: _cert_teste())
    tid = {"configurable": {"thread_id": "ctx1"}}

    graph.invoke(
        {"messages": [{"role": "user", "content": "Nota da Clínica Alfa"}]},
        config=tid,
    )
    graph.invoke(Command(resume={"aprovado": True, "feedback": None}), config=tid)
    graph.invoke(
        {"messages": [{"role": "user", "content": "o valor agora é 3000"}]},
        config=tid,
    )

    # A última extração (3ª chamada ao LLM) deve enxergar as DUAS mensagens.
    ultimo = capturados[-1]
    assert "Clínica Alfa" in ultimo, "contexto da 1ª mensagem sumiu"
    assert "o valor agora é 3000" in ultimo
