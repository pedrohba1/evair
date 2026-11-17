// Persistência local (IndexedDB via idb): múltiplas conversas + histórico.
// Tudo fica no navegador — o backend é sem estado. Cada conversa tem o seu
// próprio `id` (que também é o `thread_id` usado no backend).
import { openDB } from 'idb';

const DB_NAME = 'evair';
const DB_VERSION = 2;
const CHATS = 'chats';
const MESSAGES = 'messages';
const KV = 'kv';

let _db;

async function db() {
  if (!_db) {
    _db = await openDB(DB_NAME, DB_VERSION, {
      upgrade(d) {
        if (!d.objectStoreNames.contains(KV)) d.createObjectStore(KV);
        if (!d.objectStoreNames.contains(CHATS)) {
          d.createObjectStore(CHATS, { keyPath: 'id' });
        }
        if (!d.objectStoreNames.contains(MESSAGES)) {
          const m = d.createObjectStore(MESSAGES, { keyPath: 'id', autoIncrement: true });
          m.createIndex('chat_id', 'chat_id');
        }
      },
    });
    await _migrarLegado(_db);
  }
  return _db;
}

function _titulo(texto) {
  const t = (texto || '').trim().replace(/\s+/g, ' ');
  return t.length > 42 ? t.slice(0, 42) + '…' : t || 'Nova conversa';
}

// Migra o formato antigo (uma única conversa: loja 'chat' plana + 'thread_id'
// no KV) para uma conversa da nova estrutura, para não perder o que já existia.
// Totalmente defensiva: qualquer falha é engolida para nunca derrubar o app.
async function _migrarLegado(d) {
  let jaMigrou = false;
  try {
    jaMigrou = !!(await d.get(KV, 'migrado_v2'));
  } catch {
    /* ignore */
  }
  if (jaMigrou) return;

  try {
    await d.put(KV, true, 'migrado_v2');

    let antigas = [];
    let tid = null;
    try {
      if (d.objectStoreNames.contains('chat')) antigas = await d.getAll('chat');
      tid = (await d.get(KV, 'thread_id')) || null;
    } catch {
      /* instalação nova: não há loja 'chat' */
    }

    if (!antigas.length && !tid) return;

    const id = tid || crypto.randomUUID();
    const agora = Date.now();
    antigas = antigas.slice().sort((a, b) => (a.ts || 0) - (b.ts || 0));
    const primeira = antigas.find((m) => m.role === 'user');

    await d.put(CHATS, {
      id,
      title: primeira ? _titulo(primeira.content) : 'Conversa anterior',
      created_at: (antigas[0] && antigas[0].ts) || agora,
      updated_at: agora,
    });
    for (const m of antigas) {
      await d.add(MESSAGES, {
        chat_id: id,
        role: m.role,
        content: m.content,
        ts: m.ts || agora,
      });
    }
    await d.put(KV, id, 'current_chat_id');
  } catch (e) {
    // Limpa a flag para tentar migrar de novo no próximo carregamento.
    try {
      await d.delete(KV, 'migrado_v2');
    } catch {
      /* ignore */
    }
    console.warn('[evair] migração legada falhou (ignorando):', e);
  }
}

export async function listConversations() {
  const d = await db();
  const all = await d.getAll(CHATS);
  return all.sort((a, b) => (b.updated_at || 0) - (a.updated_at || 0));
}

export async function createConversation() {
  const d = await db();
  const agora = Date.now();
  const conv = {
    id: crypto.randomUUID(),
    title: 'Nova conversa',
    created_at: agora,
    updated_at: agora,
  };
  await d.put(CHATS, conv);
  await d.put(KV, conv.id, 'current_chat_id');
  return conv;
}

export async function getCurrentChatId() {
  const d = await db();
  return (await d.get(KV, 'current_chat_id')) || null;
}

export async function setCurrentChatId(id) {
  const d = await db();
  await d.put(KV, id, 'current_chat_id');
}

export async function getMessages(chatId) {
  const d = await db();
  const all = await d.getAllFromIndex(MESSAGES, 'chat_id', chatId);
  return all.sort((a, b) => (a.ts || 0) - (b.ts || 0));
}

export async function addMessage(chatId, msg) {
  const d = await db();
  const ts = Date.now();
  await d.add(MESSAGES, { chat_id: chatId, role: msg.role, content: msg.content, ts });

  const conv = await d.get(CHATS, chatId);
  if (conv) {
    const update = { ...conv, updated_at: ts };
    if (msg.role === 'user' && (!conv.title || conv.title === 'Nova conversa')) {
      update.title = _titulo(msg.content);
    }
    await d.put(CHATS, update);
  }
}

export async function deleteConversation(id) {
  const d = await db();
  await d.delete(CHATS, id);
  const msgs = await d.getAllFromIndex(MESSAGES, 'chat_id', id);
  await Promise.all(msgs.map((m) => d.delete(MESSAGES, m.id)));
  if ((await d.get(KV, 'current_chat_id')) === id) {
    await d.delete(KV, 'current_chat_id');
  }
}
