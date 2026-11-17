# Frontend Svelte (Etapa 5) — plano

Chat que conversa com o agente do EVAIR e emite NFS-e. Estado todo no
navegador; o backend (`api/`) permanece sem estado.

## Stack

- **SvelteKit** (SSR desligado / `adapter-static`, é uma SPA local).
- **Tailwind CSS** (opcional; sem lib de componentes pesada).
- **IndexedDB** (via `idb`) para o histórico de chat e a numeração.

## Login com certificado (o popup nativo do navegador)

O objetivo é reproduzir o que o gov.br faz: o navegador mostra o popup
"escolha o certificado" e o usuário seleciona o seu e-CNPJ/e-CPF A1.

Isso é **mTLS de cliente na camada TLS** e não tem nada a ver com código no
frontend. Para disparar o popup, um servidor HTTPS precisa pedir o client
cert no handshake. Desenho para app local:

```
navegador  --HTTPS-->  Caddy/nginx (requer client cert, confia na cadeia ICP-Brasil)
                            |
                            v
                      backend FastAPI (127.0.0.1, sem TLS — fica atrás do proxy)
```

- O Caddy/nginx valida o certificado do usuário (verificação `verify` +
  a cadeia da ICP-Brasil) e repassa `X-Client-Cert-CN`/`serial` para o
  backend, que só então libera as rotas.
- O certificado precisa estar instalado no repositório do SO (mesmo que o
  usuário já usa para o gov.br — é o mesmo cert).
- Para dev sem fricção, dá para pular o mTLS e rodar só o chat (a emissão
  continua autenticada no backend pelo `.pfx` do `.env`).

Nota: o certificado de login (popup) e o de emissão (mTLS da Sefin) são o
mesmo `.pfx`; o de login é apresentado pelo navegador, o de emissão é
carregado pelo backend — porque o navegador não consegue apresentar client
cert numa chamada `fetch()` à Sefin.

## Fluxo da UI

1. **Chat** — mensagens em streaming (SSE do `/chat`; hoje é request/response,
   streaming é incremento posterior).
2. **Perguntas** — quando o backend responde `perguntas`, renderizar como
   mensagens do assistente.
3. **Rascunho** — quando responde `status: aguardando_aprovacao`, mostrar o
   `draft` formatado com botões **Aprovar** / **Rejeitar (com comentário)**.
4. **Emissão** — aprovar chama `/chat/resume`; o resultado (chave de acesso)
   aparece no chat.

## Persistência (IndexedDB)

- **Histórico de conversas** — por `thread_id` (UUID gerado no navegador e
  persistido). O agente pode recuperar esse histórico e injetá-lo como
  contexto em futuras mensagens (a base de busca da IA).
- **Numeração (série/nDPS)** — o backend é sem estado, então o próximo
  número da DPS fica aqui e é enviado junto na emissão (hoje o `to_dps`
  usa `n_dps="1"` fixo; será parametrizado).

## Contrato HTTP (consumir do `api/`)

- `GET /health` → `{ok, ambiente, cnpj}`.
- `POST /chat` `{thread_id, message}` →
  `{status: "aguardando_aprovacao", draft}` OU
  `{status: "concluido", perguntas: [...], resultado, erro}`.
- `POST /chat/resume` `{thread_id, aprovado, feedback?}` → idem.

## Passos de implementação

1. Scaffold SvelteKit + Tailwind + `idb`; tela de chat básica.
2. Wiring `POST /chat` + render de perguntas/rascunho.
3. `POST /chat/resume` + tela de aprovação.
4. IndexedDB (histórico + thread_id + numeração).
5. (Opcional) Caddy/nginx com client cert para o login por popup.
