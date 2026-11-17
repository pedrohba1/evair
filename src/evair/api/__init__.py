"""Servidor HTTP local do EVAIR (Etapa 3).

Sem estado: nada é persistido em disco. O checkpointer do agente é o
MemorySaver (em memória) e o histórico de chat vive no navegador (IndexedDB).

Login: o usuário entra pela janela NATIVA de seleção de certificado do
navegador (mTLS). O servidor `scripts/mtls_login.py` faz o handshake TLS com
certificado de cliente e, em caso de sucesso, chama `POST /login/cert` com a
identidade (CN/CNPJ) do certificado. A identidade fica só em memória.

Assinatura: a chave privada para assinar a DPS vem do front-end, enviada como
base64 (`.pfx`) + senha na aprovação do rascunho (`POST /chat/resume`). O
backend carrega o `.pfx` em memória apenas no instante da assinatura e o
descarta em seguida — nada é lido do `.env` nem persistido em disco. O mTLS do
login apenas prova a posse do certificado; o navegador nunca exporta a chave.

Rotas:
  GET  /health        — status + ambiente/CNPJ configurados
  POST /login/cert    — registra a identidade validada pelo servidor mTLS
  GET  /login/status  — diz se há um usuário autenticado (identidade)
  POST /logout        — descarta a identidade da memória
  POST /chat          — envia uma mensagem; devolve perguntas OU um rascunho
                        aguardando aprovação (interrupt do grafo)
  POST /chat/resume   — aprova/rejeita o rascunho; emite (ou re-pergunta).
                        Leva `pfx_base64` + `senha` (o .pfx de assinatura).
"""
from __future__ import annotations

import base64
from contextvars import ContextVar
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from langgraph.types import Command
from pydantic import BaseModel

from ..agent.graph import build_graph
from ..config import EmissorConfig, load_config
from ..nfse.sign import CertBundle, load_pfx_bytes


class LoginCert(BaseModel):
    subject: str | None = None
    cn: str | None = None
    cnpj: str | None = None
    valido_ate: str | None = None


class Mensagem(BaseModel):
    thread_id: str
    message: str


class Resumo(BaseModel):
    thread_id: str
    aprovado: bool
    feedback: str | None = None
    pfx_base64: str | None = None  # .pfx de assinatura (base64), vindo do front-end
    senha: str | None = None       # senha do .pfx


# Certificado de assinatura fornecido pelo front-end na requisição atual.
# Fica num ContextVar (por requisição) e nunca entra no estado do grafo nem nos
# checkpoints — a chave privada só existe em memória no instante de assinar.
_cert_assinatura: ContextVar[tuple[bytes, str | None] | None] = ContextVar(
    "cert_assinatura", default=None
)


def _resposta(graph, result: dict[str, Any], tid: dict) -> dict[str, Any]:
    """Normaliza a saída do grafo: pausado (aprovação) vs concluído."""
    snapshot = graph.get_state(tid)
    if snapshot.next:
        # Pausado no nó de revisão (interrupt): devolve o rascunho.
        vals = snapshot.values or {}
        return {"status": "aguardando_aprovacao", "draft": vals.get("draft")}
    return {
        "status": "concluido",
        "perguntas": result.get("perguntas") or [],
        "resultado": result.get("resultado"),
        "erro": result.get("erro"),
    }


def create_app() -> FastAPI:
    cfg = load_config()

    # Identidade do usuário autenticado (via mTLS). Nada vai para o disco.
    identity: dict[str, Any] | None = None

    def bundle_provider() -> CertBundle:
        # Chave de ASSINATURA: vem do front-end (base64 + senha) enviado na
        # requisição de aprovação. O login mTLS só estabelece a identidade —
        # não fornece a chave privada.
        item = _cert_assinatura.get()
        if item is None:
            raise RuntimeError(
                "certificado de assinatura não enviado (envie o .pfx + senha)"
            )
        pfx_bytes, senha = item
        return load_pfx_bytes(pfx_bytes, senha)

    graph = build_graph(cfg, bundle_provider)

    app = FastAPI(title="EVAIR", version="0.4.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # app local, single-user
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.state.cfg = cfg
    app.state.graph = graph

    @app.get("/health")
    def health() -> dict[str, Any]:
        return {"ok": True, "ambiente": cfg.ambiente, "cnpj": cfg.cnpj}

    @app.post("/login/cert")
    def login_cert(m: LoginCert, request: Request) -> dict[str, Any]:
        nonlocal identity
        # Só aceita chamadas locais — quem valida o certificado é o servidor
        # mTLS (localhost), nunca um cliente remoto.
        if request.client is None or request.client.host not in ("127.0.0.1", "::1"):
            raise HTTPException(status_code=403, detail="login/cert é somente local")
        identity = {
            "subject": m.subject,
            "cn": m.cn,
            "cnpj": m.cnpj,
            "valido_ate": m.valido_ate,
        }
        return {"autenticado": True, **identity}

    @app.get("/login/status")
    def login_status() -> dict[str, Any]:
        if identity is None:
            return {"autenticado": False}
        return {"autenticado": True, **identity}

    @app.post("/logout")
    def logout() -> dict[str, Any]:
        nonlocal identity
        identity = None
        return {"autenticado": False}

    @app.post("/chat")
    def chat(m: Mensagem) -> dict[str, Any]:
        tid = {"configurable": {"thread_id": m.thread_id}}
        state = {"messages": [{"role": "user", "content": m.message}]}
        result = graph.invoke(state, config=tid)
        return _resposta(graph, result, tid)

    @app.post("/chat/resume")
    def resume(r: Resumo) -> dict[str, Any]:
        tid = {"configurable": {"thread_id": r.thread_id}}
        # O .pfx de assinatura entra em memória só nesta requisição (ContextVar);
        # nunca toca o estado do grafo nem os checkpoints.
        item = None
        if r.pfx_base64:
            item = (base64.b64decode(r.pfx_base64), r.senha)
        token = _cert_assinatura.set(item)
        try:
            cmd = Command(resume={"aprovado": r.aprovado, "feedback": r.feedback})
            result = graph.invoke(cmd, config=tid)
            return _resposta(graph, result, tid)
        finally:
            _cert_assinatura.reset(token)

    return app


app = create_app()
