"""Testa o fluxo de emissão recebendo o .pfx do front-end (via /chat/resume).

Cobre:
  1. o .pfx (base64) + senha enviados na aprovação chegam decodificados ao
     carregador de chave (ContextVar por requisição -> bundle_provider);
  2. a emissão sem .pfx falha com erro limpo (não 500).
Sem rede, sem LLM real.
"""
from __future__ import annotations

import base64
import json

from starlette.testclient import TestClient

from evair.api import create_app
from evair.agent.draft import DraftNota
from evair.nfse.sign import CertBundle


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


class _FakeLLM:
    def invoke(self, _prompt):
        return type("R", (), {"content": json.dumps(_draft().model_dump())})()


def _client(monkeypatch, carregados: dict) -> TestClient:
    monkeypatch.setattr("evair.agent.graph.get_llm", lambda: _FakeLLM())
    monkeypatch.setattr(
        "evair.agent.graph.emitir_dps",
        lambda _dps, _cfg, _bundle: {
            "ok": True, "chave_acesso": "0" * 50, "id_dps": "DPS" + "0" * 42,
        },
    )

    def fake_load_pfx_bytes(data: bytes, senha: str | None) -> CertBundle:
        carregados["data"] = data
        carregados["senha"] = senha
        return CertBundle(key_pem=b"", cert_pem=b"", cert_der_b64="")

    monkeypatch.setattr("evair.api.load_pfx_bytes", fake_load_pfx_bytes)
    return TestClient(create_app())


def test_emissao_recebe_pfx_do_frontend(monkeypatch):
    carregados: dict = {}
    client = _client(monkeypatch, carregados)

    r1 = client.post("/chat", json={"thread_id": "t1", "message": "Nota de 2500"})
    assert r1.status_code == 200
    assert r1.json()["status"] == "aguardando_aprovacao"

    pfx_bytes = b"\x30\x82\x01\x02fake-pfx\x03\x04"
    pfx_b64 = base64.b64encode(pfx_bytes).decode()

    r2 = client.post(
        "/chat/resume",
        json={
            "thread_id": "t1",
            "aprovado": True,
            "feedback": None,
            "pfx_base64": pfx_b64,
            "senha": "senha-teste",
        },
    )
    assert r2.status_code == 200
    body = r2.json()
    assert body["status"] == "concluido"
    assert body["resultado"]["ok"] is True

    # O .pfx chegou decodificado ao carregador de chave, junto com a senha.
    assert carregados["data"] == pfx_bytes
    assert carregados["senha"] == "senha-teste"


def test_emissao_sem_pfx_falha_limpo(monkeypatch):
    carregados: dict = {}
    client = _client(monkeypatch, carregados)

    client.post("/chat", json={"thread_id": "t2", "message": "Nota de 2500"})

    # Aprova SEM enviar o .pfx -> erro limpo (não 500), sem tocar a chave.
    r2 = client.post(
        "/chat/resume",
        json={"thread_id": "t2", "aprovado": True, "feedback": None},
    )
    assert r2.status_code == 200
    body = r2.json()
    assert body["status"] == "concluido"
    assert body["resultado"] is None
    assert "certificado de assinatura" in (body["erro"] or "")
    assert "data" not in carregados  # a chave nunca foi carregada
