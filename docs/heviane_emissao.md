# Emissão

Aqui está a especificação completa da requisição HTTP REST para envio ao Sefin Nacional.

---

## 1. Definição do Endpoint e Cabeçalhos HTTP

* **Método:** `POST`
* **Ambiente (Homologação / Produção Restrita):**
`[https://sefin.producaorestrita.nfse.gov.br/API/SefinNacional/nfse](https://sefin.producaorestrita.nfse.gov.br/API/SefinNacional/nfse)`
* **Ambiente (Produção):**
`[https://sefin.nfse.gov.br/API/SefinNacional/nfse](https://sefin.nfse.gov.br/API/SefinNacional/nfse)`
* **Autenticação de Transporte:** **mTLS (TLS 1.2+)** utilizando o Certificado Digital A1 da empresa emitente ou procurador.
* **Headers obrigatórios:**
```http
POST /API/SefinNacional/nfse HTTP/1.1
Host: sefin.producaorestrita.nfse.gov.br
Content-Type: application/json; charset=utf-8
Accept: application/json
```

---

## 2. Formato do Payload JSON de Envio

A API do Sefin Nacional espera um objeto JSON com o campo `dpsXmlGZipB64` (ou serialização padrão do XML da `<DPS>` assinada compactado em GZIP e convertido em Base64, evitando quebras de encoding e caracteres especiais na transmissão):

```json
{
  "dpsXmlGZipB64": "H4sICAAAAAAC/3htbF9hc3NpbmFkby54bWwAzVbRbtswDH33VwTdB..."
}
```

> **Regra do XML contido no Base64:** O conteúdo desse XML deve ser **estritamente a raiz `<DPS>**` com o seu bloco `<infDPS Id="...">` assinado. Não envie `<NFSe>` nem `<infNFSe>`.

---

## 3. XML da `<DPS>` que deve ser assinado e serializado

Abaixo está a estrutura do XML assinado da DPS (com dados genéricos para testes):

```xml
<?xml version="1.0" encoding="UTF-8"?>
<DPS xmlns="http://www.sped.fazenda.gov.br/nfse" versao="1.00">
  <infDPS Id="DPS320520020000000000019100001000000000000001">
    <tpAmb>2</tpAmb>
    <dhEmi>2026-11-02T17:00:00-03:00</dhEmi>
    <verAplic>ERP_v1.00</verAplic>
    <serie>00001</serie>
    <nDPS>1</nDPS>
    <dCompet>2026-11-02</dCompet>
    <tpEmit>1</tpEmit>
    <cLocEmi>3205200</cLocEmi>
    <prest>
      <CNPJ>00000000000191</CNPJ>
      <IM>12345</IM>
      <xNome>EMPRESA PRESTADORA DE SERVICOS LTDA</xNome>
      <fone>27999998888</fone>
      <email>contato@prestadordeexemplo.com.br</email>
      <regTrib>
        <opSimpNac>1</opSimpNac>
        <regApTribSN>1</regApTribSN>
        <regEspTrib>0</regEspTrib>
      </regTrib>
    </prest>
    <toma>
      <CNPJ>99999999000191</CNPJ>
      <xNome>TOMADOR DE SERVICOS TESTE LTDA</xNome>
      <end>
        <endNac>
          <cMun>3205309</cMun>
          <CEP>29010000</CEP>
        </endNac>
        <xLgr>AVENIDA EXEMPLO</xLgr>
        <nro>100</nro>
        <xBairro>CENTRO</xBairro>
      </end>
    </toma>
    <serv>
      <locPrest>
        <cLocPrestacao>3205200</cLocPrestacao>
      </locPrest>
      <cServ>
        <cTribNac>010301</cTribNac>
        <cTribMun>700</cTribMun>
        <xDescServ>Servicos de assessoria e desenvolvimento de sistemas de informacao.</xDescServ>
      </cServ>
    </serv>
    <valores>
      <vServPrest>
        <vServ>100.00</vServ>
      </vServPrest>
      <trib>
        <tribMun>
          <tribISSQN>1</tribISSQN>
          <tpRetISSQN>2</tpRetISSQN>
          <pAliq>2.50</pAliq>
        </tribMun>
        <tribFed>
          <piscofins>
            <CST>07</CST>
            <vBCPisCofins>0.00</vBCPisCofins>
            <pAliqPis>0.00</pAliqPis>
            <pAliqCofins>0.00</pAliqCofins>
            <vPis>0.00</vPis>
            <vCofins>0.00</vCofins>
            <tpRetPisCofins>2</tpRetPisCofins>
          </piscofins>
        </tribFed>
        <totTrib>
          <indTotTrib>0</indTotTrib>
        </totTrib>
      </trib>
    </valores>
  </infDPS>
  <!-- Assinatura digital da tag infDPS via XMLDSig com SHA-256 e Enveloped Signature -->
  <Signature xmlns="http://www.w3.org/2000/09/xmldsig#">
    <SignedInfo>
      <CanonicalizationMethod Algorithm="http://www.w3.org/2001/10/xml-exc-c14n#"/>
      <SignatureMethod Algorithm="http://www.w3.org/2001/04/xmldsig-more#rsa-sha256"/>
      <Reference URI="#DPS320520020000000000019100001000000000000001">
        <Transforms>
          <Transform Algorithm="http://www.w3.org/2000/09/xmldsig#enveloped-signature"/>
          <Transform Algorithm="http://www.w3.org/2001/10/xml-exc-c14n#"/>
        </Transforms>
        <DigestMethod Algorithm="http://www.w3.org/2001/04/xmlenc#sha256"/>
        <DigestValue>...</DigestValue>
      </Reference>
    </SignedInfo>
    <SignatureValue>...</SignatureValue>
    <KeyInfo>
      <X509Data>
        <X509Certificate>...</X509Certificate>
      </X509Data>
    </KeyInfo>
  </Signature>
</DPS>
```

---

## 4. Exemplo de Resposta do Sefin Nacional (HTTP 200 OK)

Quando autorizada, a resposta síncrona retorna o JSON contendo o XML completo da NFS-e autorizada (codificado em Base64/GZIP):

```json
{
  "tipoAmbiente": 2,
  "versaoAplicativo": "SefinNacional_v1.0.0",
  "dataHoraProcessamento": "2026-11-02T17:00:02-03:00",
  "codigoStatus": 100,
  "motivoStatus": "NFS-e gerada com sucesso",
  "chaveAcesso": "32052002601000000000019100001000000000000001123456",
  "nfseXmlGZipB64": "H4sICAAAAAAC/3htbF9hdXRvcml6YWRv..."
}
```

* **`chaveAcesso`:** Aqui vem a chave definitiva de **50 dígitos numéricos**.
* Ao decodificar `nfseXmlGZipB64`, você obtém o XML completo `<NFSe>` assinado pela autoridade geradora com o grupo totalizador e os dados oficiais para armazenamento no seu banco de dados e impressão do DANFSe.
