#!/usr/bin/env bash
# Sobe o backend (uvicorn), o frontend (vite) e o login mTLS do EVAIR.
#
# Uso:
#   ./dev.sh            # sobe tudo; Ctrl+C para derrubar
#   EVAIR_BACKEND_PORT=9000 ./dev.sh   # troca a porta do backend
#
# O login mTLS (scripts/mtls_login.py) escuta em https://localhost:8443 e
# dispara a janela NATIVA de seleção de certificado do navegador.
#
# Pré-requisitos: uv (Python) e pnpm (Node).

set -u

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

BACKEND_PORT="${EVAIR_BACKEND_PORT:-8321}"
FRONTEND_PORT="${EVAIR_FRONTEND_PORT:-5173}"
MTLS_PORT="${EVAIR_MTLS_PORT:-8443}"

# --- 0. .venv do backend ---
if [ ! -d ".venv" ]; then
  echo "[dev] criando .venv e instalando deps do backend..."
  uv venv
  uv pip install --python .venv/bin/python -e ".[agent,server,dev]"
fi

# --- 0.1. bundle de CAs ICP-Brasil (para validar o certificado no login mTLS) ---
if [ ! -f "certs/ca_icp_bundle.pem" ]; then
  echo "[dev] gerando bundle de CAs do certificado (certs/ca_icp_bundle.pem)..."
  .venv/bin/python scripts/inspect_chain.py || true
fi

# --- 1. Backend (FastAPI + agente LangGraph) ---
echo "[dev] subindo backend  -> http://127.0.0.1:${BACKEND_PORT}"
.venv/bin/uvicorn evair.api:app --host 127.0.0.1 --port "$BACKEND_PORT" &
BACKEND_PID=$!

# --- 2. Frontend (Svelte + Vite) ---
if [ ! -d "$ROOT/frontend/node_modules" ]; then
  echo "[dev] instalando deps do frontend (pnpm)..."
  pnpm --dir "$ROOT/frontend" install
fi

echo "[dev] subindo frontend -> http://localhost:${FRONTEND_PORT}"
pnpm --dir "$ROOT/frontend" dev --port "$FRONTEND_PORT" &
FRONTEND_PID=$!

# --- 3. Login mTLS (janela nativa de seleção de certificado) ---
echo "[dev] subindo login mTLS -> https://localhost:${MTLS_PORT}"
.venv/bin/python scripts/mtls_login.py &
MTLS_PID=$!

# --- limpeza (Ctrl+C) ---
kill_tree() {
  local pid="$1"
  pkill -P "$pid" 2>/dev/null || true
  kill "$pid" 2>/dev/null || true
}

cleanup() {
  echo ""
  echo "[dev] encerrando..."
  kill_tree "$BACKEND_PID"
  kill_tree "$FRONTEND_PID"
  kill_tree "$MTLS_PID"
  wait "$BACKEND_PID" "$FRONTEND_PID" "$MTLS_PID" 2>/dev/null || true
}
trap cleanup INT TERM EXIT

echo "[dev] tudo no ar. Abra http://localhost:${FRONTEND_PORT} — Ctrl+C para parar."
wait "$BACKEND_PID" "$FRONTEND_PID" "$MTLS_PID"
