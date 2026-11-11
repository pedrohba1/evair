"""Emissão de NFS-e no Sistema Nacional (Sefin Nacional).

Fluxo da Etapa 1:
  DPS (modelo) -> XML assinado (XMLDSig SHA-256) -> gzip+base64 -> POST /nfse (mTLS)
"""
