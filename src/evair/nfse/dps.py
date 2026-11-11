"""Construção do XML da DPS (sem assinatura) a partir do modelo.

Leiaute conforme Anexo I / XSD v1.01 do Sistema Nacional NFS-e.
Namespace padrão ``http://www.sped.fazenda.gov.br/nfse`` **sem prefixo**
(o prefixo é rejeitado pela Sefin Nacional — erro E1228).
"""
from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from lxml import etree

from .models import DPS

NS_NFSE = "http://www.sped.fazenda.gov.br/nfse"
NS_DSIG = "http://www.w3.org/2000/09/xmldsig#"

_BR = ZoneInfo("America/Sao_Paulo")


def _q(tag: str) -> str:
    """Qualifica uma tag no namespace padrão da NFS-e (sem prefixo)."""
    return f"{{{NS_NFSE}}}{tag}"


def build_id_dps(cod_municipio: str, tp_inscricao: str, inscricao: str,
                 serie: str, n_dps: str) -> str:
    """Id da DPS (45 posições): DPS + cMun(7) + tpInsc(1) + insc(14) + série(5) + nDPS(15)."""
    return (
        "DPS"
        + cod_municipio.rjust(7, "0")
        + tp_inscricao
        + inscricao.rjust(14, "0")
        + serie.rjust(5, "0")
        + n_dps.rjust(15, "0")
    )


def _fmt_dhemi(dt: datetime) -> str:
    """dhEmi no formato AAAA-MM-DDThh:mm:ssTZD (TZD = ±hh:mm)."""
    dt = dt.astimezone(_BR)
    base = dt.strftime("%Y-%m-%dT%H:%M:%S")
    offset = dt.strftime("%z")  # ex. "-0300"
    offset = offset[:3] + ":" + offset[3:]  # ex. "-03:00"
    return base + offset


def _sub(parent: etree._Element, tag: str, text: str | None = None) -> etree._Element:
    el = etree.SubElement(parent, _q(tag))
    if text is not None:
        el.text = text
    return el


def build_dps_xml(dps: DPS, *, now: datetime | None = None) -> bytes:
    """Gera o XML da DPS (ainda sem <Signature>). Retorna bytes UTF-8."""
    now = now or datetime.now(timezone.utc)
    dh_emi = dps.data_emissao or now

    root = etree.Element(_q("DPS"), nsmap={None: NS_NFSE})
    root.set("versao", "1.00")

    inf = etree.SubElement(root, _q("infDPS"))
    inf.set("Id", build_id_dps(
        dps.cod_municipio_emissor,
        "1",  # prestador CNPJ
        dps.prestador.cnpj,
        dps.serie,
        dps.n_dps,
    ))

    _sub(inf, "tpAmb", str(dps.ambiente))
    _sub(inf, "dhEmi", _fmt_dhemi(dh_emi))
    _sub(inf, "verAplic", "EVAIR_0.1.0")
    _sub(inf, "serie", dps.serie)
    _sub(inf, "nDPS", dps.n_dps)
    _sub(inf, "dCompet", dps.data_competencia.isoformat())
    _sub(inf, "tpEmit", dps.tp_emitente)
    _sub(inf, "cLocEmi", dps.cod_municipio_emissor)

    # ---- prestador ----
    prest = etree.SubElement(inf, _q("prest"))
    _sub(prest, "CNPJ", dps.prestador.cnpj)
    if dps.prestador.inscricao_municipal:
        _sub(prest, "IM", dps.prestador.inscricao_municipal)
    if dps.prestador.razao_social:
        _sub(prest, "xNome", dps.prestador.razao_social)
    if dps.prestador.telefone:
        _sub(prest, "fone", dps.prestador.telefone)
    if dps.prestador.email:
        _sub(prest, "email", dps.prestador.email)
    reg = etree.SubElement(prest, _q("regTrib"))
    _sub(reg, "opSimpNac", dps.prestador.regime.op_simples_nacional)
    if dps.prestador.regime.reg_ap_trib_sn is not None:
        _sub(reg, "regApTribSN", dps.prestador.regime.reg_ap_trib_sn)
    _sub(reg, "regEspTrib", dps.prestador.regime.reg_esp_trib)

    # ---- tomador (opcional) ----
    if dps.tomador:
        toma = etree.SubElement(inf, _q("toma"))
        _sub(toma, "CNPJ", dps.tomador.cnpj)
        _sub(toma, "xNome", dps.tomador.razao_social)
        end = etree.SubElement(toma, _q("end"))
        end_nac = etree.SubElement(end, _q("endNac"))
        if dps.tomador.cod_municipio:
            _sub(end_nac, "cMun", dps.tomador.cod_municipio)
        if dps.tomador.cep:
            _sub(end_nac, "CEP", dps.tomador.cep)
        if dps.tomador.logradouro:
            _sub(end, "xLgr", dps.tomador.logradouro)
        if dps.tomador.numero:
            _sub(end, "nro", dps.tomador.numero)
        if dps.tomador.bairro:
            _sub(end, "xBairro", dps.tomador.bairro)

    # ---- serviço ----
    serv = etree.SubElement(inf, _q("serv"))
    loc = etree.SubElement(serv, _q("locPrest"))
    _sub(loc, "cLocPrestacao", dps.servico.cod_local_prestacao)
    cserv = etree.SubElement(serv, _q("cServ"))
    _sub(cserv, "cTribNac", dps.servico.cod_trib_nacional)
    if dps.servico.cod_trib_municipal:
        _sub(cserv, "cTribMun", dps.servico.cod_trib_municipal)
    _sub(cserv, "xDescServ", dps.servico.descricao)
    if dps.servico.cod_nbs:
        _sub(cserv, "cNBS", dps.servico.cod_nbs)

    # ---- valores ----
    vals = etree.SubElement(inf, _q("valores"))
    vsp = etree.SubElement(vals, _q("vServPrest"))
    _sub(vsp, "vServ", dps.valores.v_serv)
    trib = etree.SubElement(vals, _q("trib"))
    tm = etree.SubElement(trib, _q("tribMun"))
    _sub(tm, "tribISSQN", dps.valores.tributos.municipal.trib_issqn)
    _sub(tm, "tpRetISSQN", dps.valores.tributos.municipal.tp_ret_issqn)
    _sub(tm, "pAliq", dps.valores.tributos.municipal.p_aliq)
    tf = etree.SubElement(trib, _q("tribFed"))
    pc = etree.SubElement(tf, _q("piscofins"))
    p = dps.valores.tributos.piscofins
    _sub(pc, "CST", p.cst)
    _sub(pc, "vBCPisCofins", p.v_bc_pis_cofins)
    _sub(pc, "pAliqPis", p.p_aliq_pis)
    _sub(pc, "pAliqCofins", p.p_aliq_cofins)
    _sub(pc, "vPis", p.v_pis)
    _sub(pc, "vCofins", p.v_cofins)
    _sub(pc, "tpRetPisCofins", p.tp_ret_pis_cofins)
    tt = etree.SubElement(trib, _q("totTrib"))
    _sub(tt, "indTotTrib", dps.valores.tributos.ind_tot_trib)

    return etree.tostring(
        root,
        xml_declaration=True,
        encoding="UTF-8",
        pretty_print=False,
    )
