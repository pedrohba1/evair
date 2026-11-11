#!/usr/bin/env bash
# Gera um certificado autossinado .pfx APENAS para o dry-run local.
# NÃO use este certificado contra a Sefin Nacional — a emissão real exige
# certificado ICP-Brasil (e-CNPJ) A1 do emissor habilitado.
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
mkdir -p "$DIR/certs"

cd "$DIR/certs"

# 1. par RSA + certificado autossinado (PEM)
openssl req -x509 -newkey rsa:2048 -sha256 -nodes \
  -keyout teste.key \
  -out teste.crt \
  -days 365 \
  -subj "/C=BR/O=EVAIR Teste/CN=EVAIR TESTE" \
  2>/dev/null

# 2. empacota em .pfx (senha "teste123")
openssl pkcs12 -export \
  -inkey teste.key -in teste.crt \
  -out certificado.pfx \
  -passout pass:teste123 \
  2>/dev/null

rm -f teste.key teste.crt

echo "Certificado de teste gerado em: $DIR/certs/certificado.pfx"
echo "Senha: teste123"
echo "Para usar no dry-run:"
echo "  python scripts/emitir_nfse_teste.py --cert-pfx certs/certificado.pfx --cert-senha teste123"
