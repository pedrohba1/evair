# EVAIR — Emissor virtual agêntico integrador da Receita

O EVAIR recebe a descrição de um serviço em português, monta um rascunho de
nota fiscal, pede sua revisão e aprovação no chat, e emite a **NFS-e** pela
**Sefin Nacional** (Sistema Nacional de Nota Fiscal de Serviço eletrônica),
em homologação ou produção.

## O objetivo de ponta a ponta

A ideia é que emitir uma nota seja uma conversa, não um formulário:

> Você digita: *"Emite uma nota de R$ 2.500 para a Clínica Alfa pelo suporte
> técnico de outubro."*

O agente entende o pedido, encontra o tomador cadastrado, pergunta o que
estiver ambíguo (ex.: data de competência), resolve o código do serviço e os
campos tributários a partir da configuração fiscal do emissor, e mostra o
rascunho. Ao aprovar, o backend autoriza o envio daquele rascunho e devolve a
chave de acesso e o XML da nota.

## A divisão de responsabilidades

O desenho separa o que é interpretação do que é validação/emissão:

- **O LLM interpreta e pergunta.** Extrai tomador, descrição, valor e
  competência; pede os dados que faltarem.
- **O código valida e executa.** Confere os dados fiscais contra o XSD
  oficial, controla a numeração (série/número da DPS) e emite a nota.
- **A chave privada nunca é persistida no backend.** O `.pfx` de assinatura é
  selecionado no navegador e enviado só na hora de emitir; é usado em memória
  e descartado em seguida. Fica fora do prompt e dos checkpoints do grafo.

## Login e certificado digital

Dois usos distintos do certificado ICP-Brasil e-CNPJ:

- **Login (identidade)** — o usuário entra pela **janela nativa de seleção de
  certificado do navegador** (mTLS): clica em "Entrar com certificado digital"
  e escolhe o certificado instalado no sistema operacional. O servidor
  `scripts/mtls_login.py` (porta 8443) faz o handshake TLS com certificado de
  cliente e registra a identidade (CN/CNPJ) no backend, só em memória. Nenhum
  arquivo é enviado — o navegador nunca exporta a chave privada.
- **Assinatura (emissão)** — para assinar a DPS o backend precisa da chave
  privada. Ela **não fica no backend**: o usuário seleciona o `.pfx` no
  navegador (no cartão de revisão do rascunho), e o front-end envia o arquivo
  (base64) + senha junto com a aprovação (`POST /chat/resume`). O backend usa
  a chave só em memória no instante da assinatura/transmissão e descarta.

## O que já funciona hoje (Etapa 1 — emissão sem IA)

O caminho completo de emissão está implementado e testado, sem a parte de
agente:

```
DPS (modelo Pydantic)
  -> XML (leiaute v1.01, sem prefixo de namespace)
  -> validação contra o XSD oficial (schemas/Schemas/1.01)
  -> assinatura XMLDSig SHA-256 enveloped (sobre <infDPS>)
  -> gzip + base64 -> POST /nfse via mTLS (certificado ICP-Brasil A1)
  -> resposta síncrona com a chave de acesso (50 dígitos) + XML da NFS-e
```

O script `scripts/emitir_nfse_teste.py` roda esse fluxo inteiro em modo
*dry-run* (monta, valida, assina e verifica a assinatura, sem rede) e, com as
credenciais configuradas, faz a emissão real com `--emitir`.

## Estrutura do repositório

```
src/evair/
  config.py            # carrega o .env (ambiente, CNPJ, cert, endpoints)
  nfse/
    models.py          # modelos Pydantic da DPS
    dps.py             # monta o XML da DPS
    sign.py            # assinatura XMLDSig + carga do .pfx
    validate.py        # validação contra o XSD oficial
    client.py          # cliente mTLS (POST /nfse, GET/HEAD /dps/{id})
scripts/
  emitir_nfse_teste.py # CLI de emissão (dry-run + real)
  gerar_cert_teste.sh  # gera um .pfx autossinado só para testes locais
schemas/Schemas/1.01/  # XSD oficial v1.01 (DPS, NFSe, eventos, tipos)
docs/                  # manuais oficiais e notas de pesquisa
```

## Como rodar

Pré-requisito: Python 3.11+ e [`uv`](https://docs.astral.sh/uv/).

```bash
uv venv && source .venv/bin/activate && uv pip install -e . && uv pip install -e ".[agent,server,dev]"

# Dry-run (monta + valida no XSD + assina com cert de teste, sem rede):
python scripts/emitir_nfse_teste.py

# Com um certificado de teste explícito:
bash scripts/gerar_cert_teste.sh
python scripts/emitir_nfse_teste.py \
  --cert-pfx certs/certificado.pfx --cert-senha teste123

# Emissão real (homologação) pelo script de linha de comando: copie
# .env.example -> .env, preencha NFS_E_CERT_PFX / NFS_E_CERT_SENHA
# (e-CNPJ A1 habilitado) e rode:
python scripts/emitir_nfse_teste.py --emitir
```

Para o app completo (backend + frontend + servidor mTLS de login), use o
`./dev.sh`.

## Configuração

Copie `.env.example` para `.env` e preencha. As variáveis principais:

| Variável | O que é |
|---|---|
| `NFS_E_AMBIENTE` | `1` produção, `2` homologação (produção restrita) |
| `NFS_E_CERT_PFX` | caminho do certificado e-CNPJ A1 (`.pfx`) — **só scripts CLI** |
| `NFS_E_CERT_SENHA` | senha do `.pfx` — **só scripts CLI** |
| `NFS_E_CNPJ` | CNPJ do prestador/emissor (14 dígitos) |
| `NFS_E_COD_MUNICIPIO` | IBGE do município emissor conveniado |

O `.env` e os certificados ficam fora do controle de versão (ver
`.gitignore`). Nunca versionar a chave privada. O servidor (API) **não** lê
`NFS_E_CERT_PFX`/`NFS_E_CERT_SENHA` — o `.pfx` de assinatura chega do
navegador a cada emissão.

## O que depende de credenciais reais

A emissão real só conclui quando existir um emissor habilitado:

- **CNPJ** habilitado como emissor na produção restrita (homologação).
- **Certificado ICP-Brasil e-CNPJ A1** (`.pfx`) do emissor ou de procurador
  autorizado.
- **Município conveniado** e ativo no Sistema Nacional (ex.: Uberlândia/MG =
  3170206).

Os dados do cenário de teste atual são **fictícios**.

## Roadmap

1. **Emitir nota sem IA** — concluído (módulo `nfse/`).
2. **Agente em LangGraph** — concluído (`agent/`): `StateGraph` + saída
   estruturada Pydantic (`DraftNota`), extração do tomador/serviço/valor/
   competência e perguntas sobre o que faltar.
3. **Revisão e aprovação no chat** — concluído: nó `revisar` usa
   `interrupt()` e o resume via `Command(resume=...)`, com o mesmo
   `thread_id` do frontend. Checkpointer em memória (nada em disco).
4. **Servidor HTTP local sem estado** — concluído (`api/`): FastAPI com
   `/health`, `/login/*`, `/chat` e `/chat/resume`. O `.pfx` de assinatura é
   recebido do front-end por requisição e usado só em memória; nada persistido.
5. **Frontend Svelte (chat)** — concluído: chat, barra lateral de conversas,
   login nativo com certificado (mTLS) e seleção do `.pfx` de assinatura.
6. **Fechamento e conciliação** — pendente: numeração (série/nDPS) e
   conciliação em timeout (`GET /dps/{id}`) — a numeração deve vir do
   navegador (IndexedDB), já que o backend é sem estado.

## Rodando o servidor (Etapa 2–3)

```bash
uv pip install -e ".[agent,server,dev]"
.venv/bin/uvicorn evair.api:app --host 127.0.0.1 --port 8321
```

```bash
# Testes (sem rede, sem LLM real):
.venv/bin/python -m pytest tests/ -q
```

Endpoints:

| Método | Rota | O que faz |
|---|---|---|
| `GET` | `/health` | status + ambiente/CNPJ |
| `POST` | `/login/cert` | registra a identidade validada pelo servidor mTLS |
| `GET` | `/login/status` | diz se há usuário autenticado |
| `POST` | `/logout` | descarta a identidade |
| `POST` | `/chat` | envia mensagem; devolve perguntas ou rascunho p/ aprovação |
| `POST` | `/chat/resume` | aprova/rejeita e emite (leva `pfx_base64` + `senha`) |

## Notas técnicas (confirmadas na documentação oficial)

- **Endpoints** — homologação: `https://sefin.producaorestrita.nfse.gov.br/SefinNacional`;
  produção: `https://sefin.nfse.gov.br/SefinNacional`. Emissão: `POST /nfse`.
- **Transporte** — mTLS com certificado ICP-Brasil A1, sem OAuth/token.
- **Payload** — `{"dpsXmlGZipB64": "<gzip+base64 do XML assinado>"}`.
- **Assinatura** — XMLDSig SHA-256 (não SHA-1), enveloped, sobre
  `<infDPS Id="DPS...">`, com a `<Signature>` irmã do `<infDPS>` e **sem
  prefixo de namespace** (prefixo é rejeitado, erro E1228).
- **Id da DPS** — `DPS` + cMun(7) + tpInsc(1) + inscrição(14) + série(5) +
  nDPS(15) = 45 posições, regex `DPS[0-9]{42}`.
- **Conciliação** — `GET /dps/{id}` e `HEAD /dps/{id}` (evita nota em dobro).

## Termos rápidos

- **DPS** (Declaração de Prestação de Serviços): o XML que o emissor monta e
  assina — a *entrada*.
- **NFS-e** (Nota Fiscal de Serviço eletrônica): o documento fiscal gerado
  pela Sefin Nacional a partir da DPS validada — a *saída*, com a chave de
  acesso.
