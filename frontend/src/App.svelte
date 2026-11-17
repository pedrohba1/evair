<script>
  import { onMount } from 'svelte';
  import { health, loginStatus, logout, sendMessage, resume } from './lib/api.js';
  import {
    listConversations,
    createConversation,
    getCurrentChatId,
    setCurrentChatId,
    getMessages,
    addMessage,
    deleteConversation,
  } from './lib/store.js';

  let conversations = $state([]);
  let currentChatId = $state(null);
  let messages = $state([]);
  let input = $state('');
  let draft = $state(null);        // rascunho aguardando aprovação
  let feedback = $state('');
  let busy = $state(false);
  let backend = $state(null);      // { ok, ambiente, cnpj } | null
  let sidebarOpen = $state(true);

  // Login com certificado digital (mTLS — janela nativa do navegador)
  let autenticado = $state(false);
  let certInfo = $state(null);     // { subject, cn, cnpj, valido_ate }

  // Certificado A1 de ASSINATURA (.pfx), fornecido pelo usuário no navegador.
  // O .pfx fica em memória (base64) e é enviado só na hora de emitir.
  let pfxBase64 = $state(null);
  let senha = $state('');
  let certNome = $state(null);

  onMount(async () => {
    try {
      backend = await health();
    } catch {
      backend = null;
    }
    try {
      const status = await loginStatus();
      if (status.autenticado) {
        autenticado = true;
        certInfo = status;
      }
    } catch {
      /* backend offline ou ainda sem login */
    }
    if (autenticado) {
      conversations = await listConversations();
      currentChatId = await getCurrentChatId();
      if (currentChatId) {
        messages = await getMessages(currentChatId);
      }
    }
  });

  function entrarComCertificado() {
    const mtls = import.meta.env.VITE_MTLS_URL
      || `https://${window.location.hostname}:8443/login`;
    window.location.href = mtls;
  }

  function onCertFile(e) {
    const file = e.target.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = () => {
      const url = String(reader.result);
      pfxBase64 = url.split(',')[1]; // remove o prefixo "data:...;base64,"
      certNome = file.name;
    };
    reader.readAsDataURL(file);
  }

  async function sair() {
    try {
      await logout();
    } catch {
      /* ignore */
    }
    autenticado = false;
    certInfo = null;
    pfxBase64 = null;
    senha = '';
    certNome = null;
    messages = [];
    conversations = [];
    currentChatId = null;
    draft = null;
    input = '';
    feedback = '';
  }

  function addMsg(role, content, extra = {}) {
    const msg = { role, content, ...extra };
    messages.push(msg);
    if (currentChatId) addMessage(currentChatId, msg).catch(() => {});
  }

  async function refreshList() {
    conversations = await listConversations();
  }

  function handle(res) {
    if (res.status === 'aguardando_aprovacao') {
      draft = res.draft;
      addMsg('assistant', 'Rascunho pronto para sua revisão:');
    } else if (res.status === 'concluido') {
      if (res.perguntas && res.perguntas.length) {
        addMsg('assistant', 'Faltam alguns dados:\n• ' + res.perguntas.join('\n• '));
      }
      if (res.resultado) {
        if (res.resultado.ok) {
          addMsg('assistant', `✅ NFS-e emitida!\nChave de acesso: ${res.resultado.chave_acesso}`);
        } else {
          addMsg('assistant', `❌ Rejeitada: ${JSON.stringify(res.resultado, null, 2)}`);
        }
      }
      if (res.erro) {
        addMsg('assistant', `⚠️ Erro: ${res.erro}`);
      }
    }
  }

  async function novaConversa() {
    if (busy) return;
    const conv = await createConversation();
    currentChatId = conv.id;
    messages = [];
    draft = null;
    feedback = '';
    await refreshList();
  }

  async function abrirConversa(id) {
    if (id === currentChatId || busy) return;
    currentChatId = id;
    await setCurrentChatId(id);
    messages = await getMessages(id);
    draft = null;
    feedback = '';
  }

  async function excluirConversa(id) {
    await deleteConversation(id);
    if (id === currentChatId) {
      currentChatId = null;
      messages = [];
      draft = null;
    }
    await refreshList();
  }

  async function ensureChat() {
    if (!currentChatId) {
      const conv = await createConversation();
      currentChatId = conv.id;
    }
  }

  async function send() {
    const text = input.trim();
    if (!text || busy || draft) return;
    await ensureChat();
    input = '';
    addMsg('user', text);
    busy = true;
    try {
      const res = await sendMessage(currentChatId, text);
      handle(res);
    } catch (e) {
      addMsg('assistant', `⚠️ Erro de conexão com o backend: ${e.message}`);
    } finally {
      busy = false;
      await refreshList();
    }
  }

  async function aprovar() {
    if (busy || !draft) return;
    if (!pfxBase64) {
      addMsg('assistant', '⚠️ Carregue o certificado A1 (.pfx) e a senha antes de emitir.');
      return;
    }
    busy = true;
    draft = null;
    try {
      const res = await resume(currentChatId, true, null, pfxBase64, senha);
      handle(res);
    } catch (e) {
      addMsg('assistant', `⚠️ Erro: ${e.message}`);
    } finally {
      busy = false;
      await refreshList();
    }
  }

  async function rejeitar() {
    if (busy || !draft) return;
    busy = true;
    const fb = feedback.trim() || 'Revise o rascunho.';
    feedback = '';
    draft = null;
    try {
      const res = await resume(currentChatId, false, fb);
      handle(res);
    } catch (e) {
      addMsg('assistant', `⚠️ Erro: ${e.message}`);
    } finally {
      busy = false;
      await refreshList();
    }
  }
</script>

{#if !autenticado}
  <div class="login">
    <div class="login-card">
      <h1>EVAIR</h1>
      <p class="sub">emissor de NFS-e · Sistema Nacional</p>
      <div class="login-status">
        {#if backend === null}
          <span class="dot off"></span> backend offline
        {:else}
          <span class="dot on"></span> homologação · CNPJ {backend.cnpj}
        {/if}
      </div>

      <button
        class="primary cert-btn"
        onclick={entrarComCertificado}
        disabled={backend === null}
      >
        🔐 Entrar com certificado digital
      </button>

      <p class="hint">
        O navegador abre a janela nativa de seleção do certificado instalado no
        seu computador (e-CNPJ / e-CPF). Nenhum arquivo é enviado: a identidade é
        validada pelo próprio navegador na conexão segura (mTLS), como no
        Emissor Nacional.
      </p>
    </div>
  </div>
{:else}
  <div class="app">
    <aside class="sidebar" class:closed={!sidebarOpen}>
      <div class="sidebar-top">
        <button class="newchat" onclick={novaConversa} disabled={busy}>+ Nova conversa</button>
      </div>
      <nav class="conversations">
        {#each conversations as c (c.id)}
          <div
            class="conv"
            class:active={c.id === currentChatId}
            role="button"
            tabindex="0"
            onclick={() => abrirConversa(c.id)}
            onkeydown={(e) => e.key === 'Enter' && abrirConversa(c.id)}
          >
            <span class="conv-title">{c.title}</span>
            <button
              class="conv-del"
              title="Excluir conversa"
              onclick={(e) => { e.stopPropagation(); excluirConversa(c.id); }}
            >×</button>
          </div>
        {/each}
        {#if !conversations.length}
          <div class="empty">Nenhuma conversa ainda.<br />Comece uma nova conversa.</div>
        {/if}
      </nav>
    </aside>

    <div class="main">
      <header>
        <button class="hamburger" onclick={() => (sidebarOpen = !sidebarOpen)} title="Mostrar/ocultar conversas">☰</button>
        <div class="brand">EVAIR <span>emissor de NFS-e</span></div>
        <div class="status">
          {#if backend === null}
            <span class="dot off"></span> backend offline
          {:else}
            <span class="dot on"></span> homologação · CNPJ {backend.cnpj}
          {/if}
          {#if certInfo?.cn}
            <span class="cert-cn" title={certInfo.subject}>{certInfo.cn}</span>
          {/if}
        </div>
        <button onclick={sair}>Sair</button>
      </header>

      <main class="chat">
        {#each messages as m}
          {#if m.role === 'user'}
            <div class="row user"><div class="bubble">{m.content}</div></div>
          {:else}
            <div class="row assistant"><div class="bubble">
              <pre>{m.content}</pre>
            </div></div>
          {/if}
        {/each}

        {#if draft}
          <div class="row assistant">
            <div class="card">
              <h3>Revisão do rascunho</h3>
              <dl>
                <dt>Tomador</dt><dd>{draft.tomador_razao_social || '—'} (CNPJ {draft.tomador_cnpj || '—'})</dd>
                <dt>Endereço</dt><dd>{[draft.tomador_logradouro, draft.tomador_numero, draft.tomador_bairro, draft.tomador_cep].filter(Boolean).join(', ') || '—'}</dd>
                <dt>Serviço</dt><dd>{draft.descricao_servico || '—'}</dd>
                <dt>Valor</dt><dd>R$ {draft.valor_servico || '—'}</dd>
                <dt>Competência</dt><dd>{draft.data_competencia || '—'}</dd>
              </dl>
              <div class="cert-sign">
                <div class="cert-sign-title">Certificado A1 de assinatura (.pfx)</div>
                <div class="cert-sign-row">
                  <input type="file" accept=".pfx,.p12" onchange={onCertFile} />
                  <input type="password" placeholder="senha do .pfx" bind:value={senha} />
                </div>
                {#if certNome}
                  <div class="cert-loaded">🔑 {certNome}</div>
                {/if}
              </div>
              <div class="actions">
                <button class="primary" onclick={aprovar} disabled={busy || !pfxBase64}>Aprovar e emitir</button>
                <button class="danger" onclick={rejeitar} disabled={busy}>Rejeitar</button>
              </div>
              <input
                placeholder="Comentário (opcional, se rejeitar)"
                bind:value={feedback}
              />
            </div>
          </div>
        {/if}

        {#if busy}
          <div class="row assistant"><div class="bubble muted">…</div></div>
        {/if}
      </main>

      <footer>
        <form
          class="composer"
          onsubmit={(e) => { e.preventDefault(); send(); }}
        >
          <input
            placeholder="Descreva a nota (ex.: nota de R$ 2.500 para a Clínica Alfa pelo suporte de outubro)"
            bind:value={input}
            disabled={busy || draft}
          />
          <button class="primary" type="submit" disabled={busy || draft || !input.trim()}>Enviar</button>
        </form>
      </footer>
    </div>
  </div>
{/if}

<style>
  .app { display: flex; height: 100vh; }

  .login {
    height: 100vh; display: flex; align-items: center; justify-content: center;
    padding: 20px;
  }
  .login-card {
    width: 100%; max-width: 420px;
    background: var(--panel); border: 1px solid var(--border);
    border-radius: 14px; padding: 28px;
    display: flex; flex-direction: column; gap: 14px;
  }
  .login-card h1 { margin: 0; font-size: 26px; }
  .login-card .sub { margin: 0; color: var(--muted); }
  .login-status { color: var(--muted); font-size: 13px; display: flex; align-items: center; gap: 6px; }
  .cert-btn { width: 100%; }
  .hint { margin: 0; color: var(--muted); font-size: 12px; line-height: 1.5; }

  .sidebar {
    width: 260px; flex-shrink: 0;
    background: var(--panel);
    border-right: 1px solid var(--border);
    display: flex; flex-direction: column;
    transition: margin-left 0.2s ease;
    overflow: hidden;
  }
  .sidebar.closed { margin-left: -260px; }

  .sidebar-top { padding: 12px; border-bottom: 1px solid var(--border); }
  .newchat { width: 100%; }

  .conversations {
    flex: 1; overflow-y: auto; padding: 8px;
    display: flex; flex-direction: column; gap: 4px;
  }
  .conv {
    display: flex; align-items: center; gap: 6px;
    padding: 9px 10px; border-radius: 8px; cursor: pointer;
    color: var(--text); font-size: 14px; user-select: none;
  }
  .conv:hover { background: #1e232e; }
  .conv.active { background: #262c39; }
  .conv-title { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .conv-del {
    opacity: 0; border: none; background: none; padding: 2px 7px;
    color: var(--muted); font-size: 17px; line-height: 1; border-radius: 6px;
  }
  .conv:hover .conv-del, .conv-del:focus { opacity: 1; }
  .conv-del:hover { color: var(--danger); background: #1e232e; }

  .empty { color: var(--muted); font-size: 13px; padding: 8px 10px; line-height: 1.5; }

  .main { flex: 1; display: flex; flex-direction: column; min-width: 0; }

  header {
    display: flex; align-items: center; gap: 14px;
    padding: 12px 18px; border-bottom: 1px solid var(--border);
    background: var(--panel);
  }
  .hamburger { padding: 6px 10px; line-height: 1; }
  .brand { font-weight: 700; }
  .brand span { color: var(--muted); font-weight: 400; margin-left: 6px; }
  .status { flex: 1; color: var(--muted); font-size: 13px; display: flex; align-items: center; gap: 6px; min-width: 0; }
  .cert-cn {
    overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 320px;
    color: var(--text);
  }
  .dot { width: 8px; height: 8px; border-radius: 50%; display: inline-block; flex-shrink: 0; }
  .dot.on { background: var(--ok); }
  .dot.off { background: var(--danger); }

  .chat { flex: 1; overflow-y: auto; padding: 18px; display: flex; flex-direction: column; gap: 12px; }
  .row { display: flex; }
  .row.user { justify-content: flex-end; }
  .row.assistant { justify-content: flex-start; }

  .bubble {
    max-width: 72%; padding: 10px 14px; border-radius: 12px;
    background: var(--panel); border: 1px solid var(--border);
  }
  .row.user .bubble { background: var(--accent); border-color: var(--accent); color: #fff; }
  .bubble pre { margin: 0; white-space: pre-wrap; font: inherit; }
  .bubble.muted { color: var(--muted); }

  .card {
    max-width: 560px; background: var(--panel); border: 1px solid var(--border);
    border-radius: 12px; padding: 16px; display: flex; flex-direction: column; gap: 12px;
  }
  .card h3 { margin: 0; }
  .card dl { margin: 0; display: grid; grid-template-columns: 110px 1fr; row-gap: 6px; }
  .card dt { color: var(--muted); }
  .card dd { margin: 0; }
  .actions { display: flex; gap: 8px; }

  .cert-sign {
    border: 1px solid var(--border); border-radius: 8px; padding: 10px;
    display: flex; flex-direction: column; gap: 6px; background: #151a23;
  }
  .cert-sign-title { font-size: 12px; color: var(--muted); }
  .cert-sign-row { display: flex; gap: 8px; align-items: center; }
  .cert-sign-row input[type='file'] { flex: 1; font-size: 12px; }
  .cert-sign-row input[type='password'] { width: 160px; }
  .cert-loaded { font-size: 12px; color: var(--ok); }

  footer { padding: 12px 18px; border-top: 1px solid var(--border); background: var(--panel); }
  .composer { display: flex; gap: 10px; }
  .composer input { flex: 1; }
</style>
