#!/usr/bin/env python3
"""Extrai a cadeia do certificado do .pfx (sem expor a senha) para montar o
bundle de CAs usado pelo servidor de login mTLS (janela nativa do navegador).

Só grava os certificados PÚBLICOS (folha + intermediárias). A chave privada
não é tocada nem serializada.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from cryptography import x509
from cryptography.hazmat.primitives.serialization import Encoding, pkcs12
from cryptography.x509.oid import NameOID

from evair.config import load_config


def main() -> int:
    cfg = load_config()
    pfx = cfg.cert_pfx
    if not pfx or not pfx.exists():
        print("NFS_E_CERT_PFX não aponta para um arquivo existente:", pfx)
        return 1

    data = pfx.read_bytes()
    senha = cfg.cert_senha or None
    key, leaf, additional = pkcs12.load_key_and_certificates(
        data, senha.encode() if senha else None
    )

    def cn(c: x509.Certificate) -> str:
        attrs = c.subject.get_attributes_for_oid(NameOID.COMMON_NAME)
        return str(attrs[0].value) if attrs else c.subject.rfc4514_string()

    print("=== FOLHA (certificado do emissor) ===")
    print("  CN:", cn(leaf))
    print("  issuer:", leaf.issuer.rfc4514_string())

    chain = [leaf] + list(additional or [])
    print(f"\n=== CADEIA ({len(chain)} certificados) ===")
    for i, c in enumerate(chain):
        tag = "folha" if i == 0 else "intermediária/raiz"
        print(f"  [{i}] {tag}: CN={cn(c)}")
        print(f"      issuer={c.issuer.rfc4514_string()}")

    # Grava as CA intermediárias/raiz (sem a folha) como bundle de confiança.
    cas = [c for c in chain[1:]]
    out = os.path.join(os.path.dirname(pfx), "ca_icp_bundle.pem")
    with open(out, "wb") as fh:
        for c in cas:
            fh.write(c.public_bytes(Encoding.PEM))
    print(f"\nGravou {len(cas)} CA(s) em {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
