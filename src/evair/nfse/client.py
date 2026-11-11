"""Cliente mTLS para a API da Sefin Nacional (Sistema Nacional NFS-e).

- POST /nfse  -> envia a DPS (gzip+base64) e recebe a NFS-e autorizada
- GET  /dps/{id} -> recupera a chave de acesso a partir do Id da DPS
- HEAD /dps/{id} -> verifica se a NFS-e já foi gerada (evita nota em dobro)

A autenticação é mTLS com o certificado ICP-Brasil A1 do emissor — sem OAuth.
"""
from __future__ import annotations

import base64
import gzip
import json
from dataclasses import dataclass, field

import httpx

from .sign import CertBundle


@dataclass
class EmitirResultado:
    """Resultado da emissão (sucesso ou rejeição)."""

    ok: bool
    status_code: int
    chave_acesso: str | None = None
    id_dps: str | None = None
    nfse_xml: bytes | None = None  # XML da NFS-e autorizada (descompactado)
    erros: list[dict] = field(default_factory=list)
    raw: dict | None = None


def _gzip_b64(xml_bytes: bytes) -> str:
    return base64.b64encode(gzip.compress(xml_bytes)).decode()


def _gunzip_b64(b64: str) -> bytes:
    return gzip.decompress(base64.b64decode(b64))


class SefinClient:
    def __init__(self, base_url: str, bundle: CertBundle, timeout: float = 60.0):
        self.base_url = base_url.rstrip("/")
        self._bundle = bundle
        self._client = httpx.Client(
            timeout=timeout,
            cert=(
                # httpx aceita caminhos ou bytes PEM. Usamos bytes do cert p/ não
                # depender de arquivos temporários.
                _pem_to_certfile(bundle),
                _pem_to_keyfile(bundle),
            ),
            headers={"Content-Type": "application/json; charset=utf-8",
                     "Accept": "application/json"},
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "SefinClient":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def emitir(self, dps_signed_xml: bytes) -> EmitirResultado:
        """Envia a DPS assinada e devolve a NFS-e autorizada (ou os erros)."""
        payload = json.dumps({"dpsXmlGZipB64": _gzip_b64(dps_signed_xml)})
        resp = self._client.post(f"{self.base_url}/nfse", content=payload)
        return self._parse_emitir(resp)

    def consultar_por_id(self, id_dps: str) -> EmitirResultado:
        """GET /dps/{id} -> chave de acesso (se o cert for ator da nota)."""
        resp = self._client.get(f"{self.base_url}/dps/{id_dps}")
        return self._parse_emitir(resp)

    def existe(self, id_dps: str) -> bool:
        """HEAD /dps/{id} -> True se a NFS-e correspondente já foi gerada."""
        resp = self._client.head(f"{self.base_url}/dps/{id_dps}")
        return resp.status_code == 200

    @staticmethod
    def _parse_emitir(resp: httpx.Response) -> EmitirResultado:
        if resp.status_code in (200, 201):
            data = resp.json()
            nfse_b64 = data.get("nfseXmlGZipB64")
            nfse_xml = _gunzip_b64(nfse_b64) if nfse_b64 else None
            return EmitirResultado(
                ok=True,
                status_code=resp.status_code,
                chave_acesso=data.get("chaveAcesso"),
                id_dps=data.get("idDps"),
                nfse_xml=nfse_xml,
                raw=data,
            )
        # Rejeição: a Sefin devolve um JSON com a lista de erros.
        try:
            body = resp.json()
        except Exception:
            body = {"erros": [{"Codigo": str(resp.status_code),
                               "Descricao": resp.text}]}
        erros = body.get("erros", []) or []
        return EmitirResultado(
            ok=False, status_code=resp.status_code, erros=erros, raw=body
        )


def _pem_to_certfile(bundle: CertBundle) -> bytes:
    return bundle.cert_pem


def _pem_to_keyfile(bundle: CertBundle) -> bytes:
    return bundle.key_pem
