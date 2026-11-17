"""Configuração do emissor, lida de variáveis de ambiente.

A chave privada do certificado fica apenas aqui (carregada sob demanda),
fora do prompt e dos checkpoints do grafo.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def _load_dotenv(path: str = ".env") -> None:
    """Carrega um arquivo .env simples (KEY=VALUE) se ainda não estiver no ambiente.

    Variáveis já exportadas no shell têm precedência (não são sobrescritas).
    """
    p = Path(path)
    if not p.exists():
        return
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


@dataclass(frozen=True)
class EmissorConfig:
    ambiente: int  # 1=produção, 2=homologação
    cnpj: str
    inscricao_municipal: str | None
    cod_municipio: str  # IBGE, 7 dígitos
    ver_aplic: str
    cert_pfx: Path | None
    cert_senha: str
    url_homologacao: str
    url_producao: str

    @property
    def base_url(self) -> str:
        return self.url_producao if self.ambiente == 1 else self.url_homologacao

    @property
    def tipo_ambiente(self) -> int:
        return self.ambiente


def load_config() -> EmissorConfig:
    _load_dotenv()
    cnpj = _env("NFS_E_CNPJ", "39982868000170")
    im = _env("NFS_E_INSCRICAO_MUNICIPAL") or None
    pfx = _env("NFS_E_CERT_PFX")
    return EmissorConfig(
        ambiente=int(_env("NFS_E_AMBIENTE", "2")),
        cnpj=cnpj,
        inscricao_municipal=im,
        cod_municipio=_env("NFS_E_COD_MUNICIPIO", "3170206"),
        ver_aplic=_env("NFS_E_VER_APLIC", "EVAIR_0.1.0"),
        cert_pfx=Path(pfx) if pfx else None,
        cert_senha=_env("NFS_E_CERT_SENHA"),
        url_homologacao=_env(
            "NFS_E_URL_HOMOLOGACAO",
            "https://sefin.producaorestrita.nfse.gov.br/SefinNacional",
        ),
        url_producao=_env(
            "NFS_E_URL_PRODUCAO", "https://sefin.nfse.gov.br/SefinNacional"
        ),
    )
