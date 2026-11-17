#!/usr/bin/env python3
"""Testa o handshake mTLS do servidor de login usando o .pfx real (senha via
config, sem expor). Conecta como cliente e imprime a resposta HTTP."""
from __future__ import annotations

import os
import socket
import ssl
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.serialization import pkcs12

from evair.config import load_config


def main() -> int:
    cfg = load_config()
    if not cfg.cert_pfx or not cfg.cert_pfx.exists():
        print("NFS_E_CERT_PFX não aponta para arquivo existente.")
        return 1

    data = Path(cfg.cert_pfx).read_bytes()
    senha = cfg.cert_senha or None
    key, leaf, additional = pkcs12.load_key_and_certificates(
        data, senha.encode() if senha else None
    )

    chain = [leaf] + list(additional or [])
    chain_path = key_path = None
    try:
        with tempfile.NamedTemporaryFile("wb", suffix=".pem", delete=False) as f:
            for c in chain:
                f.write(c.public_bytes(serialization.Encoding.PEM))
            chain_path = f.name
        with tempfile.NamedTemporaryFile("wb", suffix=".pem", delete=False) as f:
            f.write(
                key.private_bytes(
                    serialization.Encoding.PEM,
                    serialization.PrivateFormat.PKCS8,
                    serialization.NoEncryption(),
                )
            )
            key_path = f.name

        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        ctx.load_cert_chain(chain_path, key_path)
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE  # servidor é autossinado (dev)

        sock = socket.create_connection(("127.0.0.1", 8443), timeout=10)
        ssock = ctx.wrap_socket(sock, server_hostname="localhost")
        peer = ssock.getpeercert()
        print("server cert CN:", (peer or {}).get("subject"))

        ssock.sendall(
            b"GET /login HTTP/1.1\r\nHost: localhost\r\nConnection: close\r\n\r\n"
        )
        resp = b""
        while True:
            chunk = ssock.recv(4096)
            if not chunk:
                break
            resp += chunk
        ssock.close()
        print("--- resposta HTTP ---")
        print(resp.decode("utf-8", errors="replace"))
        return 0
    except ssl.SSLError as e:
        print("ERRO SSL:", e)
        return 2
    finally:
        for p in (chain_path, key_path):
            if p:
                try:
                    os.unlink(p)
                except OSError:
                    pass


if __name__ == "__main__":
    sys.exit(main())
