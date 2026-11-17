"""Pipeline de emissão: DPS -> XML -> validação XSD -> assinatura -> mTLS.

Reusa o módulo nfse da Etapa 1 e expõe uma função única chamada pelo nó de
emissão do agente. A chave privada (``CertBundle``) é passada por parâmetro,
nunca armazenada em estado.
"""
from __future__ import annotations

from typing import Any

from .config import EmissorConfig
from .nfse import dps as dps_mod
from .nfse import sign as sign_mod
from .nfse import validate
from .nfse.client import SefinClient
from .nfse.models import DPS
from .nfse.sign import CertBundle


def emitir(dps: DPS, cfg: EmissorConfig, bundle: CertBundle) -> dict[str, Any]:
    """Monta, valida, assina e emite a DPS. Retorna um dict serializável."""
    xml = dps_mod.build_dps_xml(dps)

    # O XSD local v1.01 é pré-NT-009 (não conhece finNFSe no infDPS), então a
    # validação local NÃO bloqueia aqui — a Sefin é a fonte de verdade e devolve
    # E1235 apontando o elemento exato fora de lugar. (ver references/nt009)
    avisos_xsd = validate.validate_dps_report(xml)

    xml_assinado = sign_mod.sign_dps(xml, bundle)
    if not sign_mod.verify_dps_signature(xml_assinado, bundle.cert_pem):
        return {"ok": False, "etapa": "assinatura", "erros": ["auto-verificação falhou"]}

    with SefinClient(cfg.base_url, bundle) as client:
        r = client.emitir(xml_assinado)

    if r.ok:
        return {
            "ok": True,
            "chave_acesso": r.chave_acesso,
            "id_dps": r.id_dps,
            "avisos_xsd": avisos_xsd,
        }
    return {
        "ok": False,
        "etapa": "emissao",
        "erros": r.erros,
        "status_code": r.status_code,
        "avisos_xsd": avisos_xsd,
    }
