// Cliente HTTP para o backend local (FastAPI).
const BASE = import.meta.env.VITE_API_BASE || 'http://localhost:8321';

async function post(path, body) {
  const r = await fetch(`${BASE}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!r.ok) {
    const text = await r.text();
    throw new Error(`${r.status}: ${text.slice(0, 300)}`);
  }
  return r.json();
}

export async function health() {
  const r = await fetch(`${BASE}/health`);
  if (!r.ok) throw new Error(`health ${r.status}`);
  return r.json();
}

// O login acontece via mTLS (janela nativa do navegador): o front-end apenas
// navega para o endpoint HTTPS do servidor mTLS, que valida o certificado e
// registra a identidade no backend (POST /login/cert). Não há upload de .pfx.
export async function loginStatus() {
  const r = await fetch(`${BASE}/login/status`);
  if (!r.ok) throw new Error(`login/status ${r.status}`);
  return r.json();
}

export function logout() {
  return post('/logout', {});
}

export function sendMessage(threadId, message) {
  return post('/chat', { thread_id: threadId, message });
}

export function resume(threadId, aprovado, feedback = null, pfxBase64 = null, senha = null) {
  return post('/chat/resume', {
    thread_id: threadId,
    aprovado,
    feedback,
    pfx_base64: pfxBase64,
    senha,
  });
}
