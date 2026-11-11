"""Validação do XML da DPS contra o XSD oficial do Sistema Nacional NFS-e.

Dois quirks do XSD oficial exigem normalização antes da validação local:

1. **``\\d`` não suportado pelo libxml2** — por isso usamos ``xmlschema``
   (pure-Python), que implementa o regex do XML Schema 1.0 corretamente.

2. **``^``/``$`` literais** — no regex do XML Schema, ``^`` e ``$`` são
   caracteres literais (não âncoras, como em Perl/Python); a correspondência
   já é sempre sobre a string inteira. O XSD oficial escreve os patterns como
   ``^0{0,4}\\d{1,5}$`` pretendendo âncoras. Removemos os ``^``/``$``
   redundantes do início/fim de cada ``<xs:pattern value="...">`` para a
   validação local reproduzir o comportamento esperado (o mesmo dos emissores
   de referência, que usam ``serie=00001``). Isto afeta apenas a validação
   local; o XML emitido continua idêntico ao padrão.
"""
from __future__ import annotations

import re
from pathlib import Path

import xmlschema

SCHEMA_DIR = Path(__file__).resolve().parent.parent.parent.parent / "schemas" / "Schemas"
VERSION = "1.01"
DPS_XSD = SCHEMA_DIR / VERSION / "DPS_v1.01.xsd"

_PATTERN_ATTR = re.compile(r'(<xs:pattern\b[^>]*?\bvalue=")([^"]*)(")')

_schema: xmlschema.XMLSchema | None = None
_tmpdir = None  # mantém o TemporaryDirectory vivo enquanto o schema estiver em uso


def _strip_anchors(text: str) -> str:
    """Remove ^ no início e $ no fim de cada value= de <xs:pattern .../>."""

    def repl(m: re.Match) -> str:
        val = m.group(2)
        if val.startswith("^"):
            val = val[1:]
        if val.endswith("$"):
            val = val[:-1]
        return m.group(1) + val + m.group(3)

    return _PATTERN_ATTR.sub(repl, text)


def _load_schema() -> xmlschema.XMLSchema:
    global _schema, _tmpdir
    if _schema is None:
        if not DPS_XSD.exists():
            raise FileNotFoundError(
                f"XSD não encontrado em {DPS_XSD}. "
                "Baixe NFSe-ESQUEMAS_XSD-v1.01 em schemas/Schemas/."
            )
        # Normaliza todos os XSD do diretório (o DPS inclui tiposComplexos
        # que inclui tiposSimples — os patterns moram lá).
        from tempfile import TemporaryDirectory

        _tmpdir = TemporaryDirectory(prefix="evair_xsd_")
        dest = Path(_tmpdir.name)
        for src in SCHEMA_DIR.glob(f"{VERSION}/*.xsd"):
            text = src.read_text(encoding="utf-8")
            (dest / src.name).write_text(_strip_anchors(text), encoding="utf-8")
        _schema = xmlschema.XMLSchema(str(dest / "DPS_v1.01.xsd"))
    return _schema


def validate_dps(dps_xml: bytes) -> None:
    """Valida o XML contra o XSD. Levanta em caso de falha."""
    _load_schema().validate(dps_xml)


def validate_dps_report(dps_xml: bytes) -> list[str]:
    """Retorna lista de erros de validação (vazia se válida)."""
    erros: list[str] = []
    for e in _load_schema().iter_errors(dps_xml):
        erros.append(str(e))
    return erros
