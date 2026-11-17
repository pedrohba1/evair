#!/usr/bin/env python3
"""Servidor de login mTLS do EVAIR (janela NATIVA de seleção de certificado).

Quando o navegador acessa este servidor por HTTPS, o handshake TLS solicita um
certificado de cliente (mTLS). Isso dispara a janela nativa do sistema
operacional para escolher o certificado — o mesmo fluxo do Emissor Nacional
(botão "Entrar com certificado digital" -> certificado.nfse.gov.br).

Ao concluir o handshake, este servidor:
  1. extrai a identidade (CN/CNPJ/CPF) do certificado apresentado;
  2. registra o login no backend local (POST /login/cert);
  3. redireciona o navegador de volta para o app (que confirma via /login/status).

A chave privada NUNCA passa por aqui: o mTLS apenas prova a posse dela, e este
servidor só enxerga o certificado PÚBLICO do cliente.

Variáveis de ambiente (opcionais):
  EVAIR_MTLS_HOST        host de escuta (default 0.0.0.0)
  EVAIR_MTLS_PORT        porta HTTPS (default 8443)
  EVAIR_BACKEND_URL      backend FastAPI (default http://127.0.0.1:8321)
  EVAIR_FRONTEND_URL     destino pós-login (default http://localhost:5173/)
"""
from __future__ import annotations

import datetime
import http.server
import ipaddress
import json
import os
import re
import ssl
import urllib.request
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

HOST = os.environ.get("EVAIR_MTLS_HOST", "0.0.0.0")
PORT = int(os.environ.get("EVAIR_MTLS_PORT", "8443"))
BACKEND_URL = os.environ.get("EVAIR_BACKEND_URL", "http://127.0.0.1:8321")
FRONTEND_URL = os.environ.get("EVAIR_FRONTEND_URL", "http://localhost:5173/")

ROOT = Path(__file__).resolve().parent.parent
CA_BUNDLE = ROOT / "certs" / "ca_icp_bundle.pem"
SERVER_CERT = ROOT / "certs" / "mtls_server.crt"
SERVER_KEY = ROOT / "certs" / "mtls_server.key"


def _ensure_server_cert() -> None:
    """Gera um certificado de servidor autossinado (localhost) se não existir."""
    if SERVER_CERT.exists() and SERVER_KEY.exists():
        return
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "localhost")])
    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(days=1))
        .not_valid_after(now + datetime.timedelta(days=3650))
        .add_extension(
            x509.SubjectAlternativeName(
                [x509.DNSName("localhost"), x509.IPAddress(ipaddress.ip_address("127.0.0.1"))]
            ),
            critical=False,
        )
        .sign(key, hashes.SHA256())
    )
    SERVER_CERT.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    SERVER_KEY.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    SERVER_KEY.chmod(0o600)
    print(f"[mtls] certificado de servidor gerado em {SERVER_CERT}")


def _parse_peer_cert(der: bytes) -> dict[str, str | None]:
    cert = x509.load_der_x509_certificate(der)
    subject = cert.subject.rfc4514_string()
    cn_attrs = cert.subject.get_attributes_for_oid(NameOID.COMMON_NAME)
    cn = str(cn_attrs[0].value) if cn_attrs else None
    m = re.search(r"\d{14}", subject)
    return {
        "subject": subject,
        "cn": cn,
        "cnpj": m.group(0) if m else None,
        "valido_ate": cert.not_valid_after_utc.isoformat(),
    }


class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802
        # Com CERT_REQUIRED, este handler só roda após um mTLS bem-sucedido.
        der = self.connection.getpeercert(binary_form=True)
        if not der:
            self.send_error(401, "certificado de cliente ausente")
            return

        info = _parse_peer_cert(der)
        print(f"[mtls] login via certificado: cn={info['cn']} cnpj={info['cnpj']}")

        try:
            req = urllib.request.Request(
                BACKEND_URL + "/login/cert",
                data=json.dumps(info).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            urllib.request.urlopen(req, timeout=5)
        except Exception as exc:  # backend fora do ar: ainda redireciona
            print(f"[mtls] aviso: falha ao registrar no backend: {exc}")

        self.send_response(302)
        self.send_header("Location", FRONTEND_URL)
        self.end_headers()

    def log_message(self, format: str, *args) -> None:  # noqa: N802 — silencioso
        pass


def main() -> None:
    if not CA_BUNDLE.exists():
        raise SystemExit(
            f"bundle de CAs ausente: {CA_BUNDLE}\n"
            "Gere com: .venv/bin/python scripts/inspect_chain.py"
        )
    _ensure_server_cert()

    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.load_cert_chain(str(SERVER_CERT), str(SERVER_KEY))
    ctx.load_verify_locations(cafile=str(CA_BUNDLE))
    ctx.verify_mode = ssl.CERT_REQUIRED  # exige + valida o certificado do cliente

    httpd = http.server.ThreadingHTTPServer((HOST, PORT), Handler)
    httpd.socket = ctx.wrap_socket(httpd.socket, server_side=True)
    print(f"[mtls] login mTLS em https://{HOST}:{PORT} -> redireciona para {FRONTEND_URL}")
    httpd.serve_forever()


if __name__ == "__main__":
    main()
