#!/usr/bin/env python3
"""Emite uma NFS-e de teste no Sistema Nacional NFS-e (Sefin Nacional).

Etapa 1 do EVAIR: monta a DPS, valida contra o XSD oficial, assina (XMLDSig
SHA-256) e — com certificado + ambiente configurados — envia via POST /nfse.

Uso:
    # 1. Dry-run: monta, valida no XSD e assina com certificado de teste
    #    (não faz POST). É o modo padrão.
    python scripts/emitir_nfse_teste.py

    # 2. Emissão real (requer .env com NFS_E_CERT_PFX + senha e habilitação)
    python scripts/emitir_nfse_teste.py --emitir

    # 3. Gerar um certificado de teste local (autossinado, apenas para o dry-run)
    bash scripts/gerar_cert_teste.sh

A chave de acesso (50 dígitos) e o XML da NFS-e vêm na resposta do --emitir.
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import date

# Permite rodar a partir da raiz do repo sem instalar o pacote.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from evair.config import load_config
from evair.nfse import dps as dps_mod
from evair.nfse import sign as sign_mod
from evair.nfse import validate
from evair.nfse.models import (
    DPS, Prestador, RegimeTributario, Servico, Tomador, Valores,
)


def montar_dps(cfg) -> DPS:
    """Cenário fictício de teste — substitua pelos dados reais do emissor."""
    return DPS(
        ambiente=cfg.ambiente,
        serie="00001",
        n_dps="1",
        data_competencia=date(2026, 10, 1),
        cod_municipio_emissor=cfg.cod_municipio,
        prestador=Prestador(
            cnpj=cfg.cnpj,
            inscricao_municipal=cfg.inscricao_municipal,
            razao_social="EMPRESA PRESTADORA DE SERVICOS LTDA",
            telefone="34999990000",
            email="contato@prestador.com.br",
            regime=RegimeTributario(),
        ),
        tomador=Tomador(
            cnpj="99999999000191",
            razao_social="CLINICA ALFA LTDA",
            cod_municipio="3170206",  # Uberlândia/MG
            cep="38400000",
            logradouro="AVENIDA EXEMPLO",
            numero="100",
            bairro="CENTRO",
        ),
        servico=Servico(
            cod_trib_nacional="010301",
            cod_trib_municipal="700",
            descricao="Servicos de assessoria e desenvolvimento de sistemas de informacao.",
            cod_local_prestacao=cfg.cod_municipio,
        ),
        valores=Valores(v_serv="2500.00"),
    )


def main() -> int:
    ap = argparse.ArgumentParser(description="Emitir NFS-e de teste")
    ap.add_argument("--emitir", action="store_true",
                    help="Faz o POST real (requer certificado no .env)")
    ap.add_argument("--cert-pfx", default=None, help="Caminho do .pfx (opcional)")
    ap.add_argument("--cert-senha", default=None, help="Senha do .pfx")
    ap.add_argument("--saida", default=None, help="Grava o XML assinado num arquivo")
    args = ap.parse_args()

    cfg = load_config()
    dps = montar_dps(cfg)

    print("== 1. Montando a DPS ==")
    xml_nao_assinado = dps_mod.build_dps_xml(dps)
    print(xml_nao_assinado.decode("utf-8"))

    print("\n== 2. Validando contra o XSD oficial (pré-assinatura) ==")
    erros = validate.validate_dps_report(xml_nao_assinado)
    if erros:
        print("ERROS DE XSD:")
        for e in erros:
            print("  -", e)
        return 2
    print("OK: DPS estruturalmente válida.")

    print("\n== 3. Assinatura XMLDSig (SHA-256) ==")
    pfx = args.cert_pfx or (str(cfg.cert_pfx) if cfg.cert_pfx else None)
    senha = args.cert_senha or cfg.cert_senha
    if pfx and os.path.exists(pfx):
        bundle = sign_mod.load_pfx(pfx, senha or None)
    else:
        print(f"[AVISO] certificado não encontrado ({pfx or 'não configurado'}).")
        if args.emitir:
            print("Não dá para emitir sem certificado. Gere um de teste: "
                  "bash scripts/gerar_cert_teste.sh")
            return 3
        # Gera um certificado autossinado em memória, apenas p/ exercitar o fluxo.
        bundle = _cert_teste_em_memoria()

    xml_assinado = sign_mod.sign_dps(xml_nao_assinado, bundle)
    if args.saida:
        import pathlib
        pathlib.Path(args.saida).parent.mkdir(parents=True, exist_ok=True)
        with open(args.saida, "wb") as fh:
            fh.write(xml_assinado)
        print(f"XML assinado gravado em {args.saida}")

    print("\n== 4. Validando o XML assinado contra o XSD ==")
    erros2 = validate.validate_dps_report(xml_assinado)
    if erros2:
        print("ERROS DE XSD (pós-assinatura):")
        for e in erros2:
            print("  -", e)
        return 4
    print("OK: XML assinado válido.")

    print("\n== 5. Verificando a assinatura (auto-verificação) ==")
    if sign_mod.verify_dps_signature(xml_assinado, bundle.cert_pem):
        print("OK: assinatura verificada.")
    else:
        print("FALHA na verificação da assinatura.")
        return 5

    if not args.emitir:
        print("\nDry-run concluído. Para emitir de verdade: --emitir (com .env)")
        return 0

    print(f"\n== 6. Emitindo via POST {cfg.base_url}/nfse (mTLS) ==")
    from evair.nfse.client import SefinClient

    with SefinClient(cfg.base_url, bundle) as client:
        r = client.emitir(xml_assinado)

    if r.ok:
        print(f"OK: NFS-e autorizada.")
        print(f"  chaveAcesso: {r.chave_acesso}")
        print(f"  idDps      : {r.id_dps}")
        if r.nfse_xml:
            print("  XML da NFS-e (primeiros 400 bytes):")
            print(r.nfse_xml[:400].decode("utf-8", errors="replace"))
        return 0
    print("REJEITADA. Erros:")
    for e in r.erros:
        print("  -", e)
    return 6


def _cert_teste_em_memoria() -> sign_mod.CertBundle:
    """Gera um par RSA + certificado autossinado apenas para o dry-run."""
    import datetime

    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import NameOID

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
        .add_extension(
            x509.KeyUsage(
                digital_signature=True,
                content_commitment=False,
                key_encipherment=False,
                data_encipherment=False,
                key_agreement=False,
                key_cert_sign=False,
                crl_sign=False,
                encipher_only=False,
                decipher_only=False,
            ),
            critical=True,
        )
        .sign(key, hashes.SHA256())
    )
    import base64
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


if __name__ == "__main__":
    sys.exit(main())
