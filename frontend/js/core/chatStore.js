/**
 * @file 对话本地持久化（按用户分区，单会话，只保存最终消息）
 * @module core/chatStore
 *
 * - 不保存流式 token、工具过程或思考状态，只保存最终 user / assistant 文本；
 * - 每个账号独立 key，登录/退出切换会话；
 * - 只保留最近 120 条 / 约 20 万字符，超出裁剪最旧消息；
 * - 服务端不参与，刷新与跨页面重载后可恢复。
 */

const VERSION = 1;
const MAX_MESSAGES = 120;
const MAX_CHARS = 200000;

function currentUser() {
  return localStorage.getItem('cm_user') || 'guest';
}

function storageKey() {
  return `cm_chat_v1:${encodeURIComponent(currentUser())}`;
}

function _empty() {
  return { version: VERSION, updated_at: '', messages: [] };
}

function _normalize(raw) {
  if (!raw || typeof raw !== 'object' || raw.version !== VERSION) return _empty();
  const messages = Array.isArray(raw.messages)
    ? raw.messages
        .filter(m => m && (m.role === 'user' || m.role === 'assistant') && typeof m.content === 'string')
        .map(m => ({ role: m.role, content: m.content, time: m.time || '' }))
    : [];
  return { version: VERSION, updated_at: raw.updated_at || '', messages };
}

function _trim(messages) {
  const out = messages.slice(-MAX_MESSAGES);
  let total = out.reduce((sum, m) => sum + m.content.length, 0);
  while (out.length > 2 && total > MAX_CHARS) {
    total -= out[0].content.length;
    out.shift();
  }
  return out;
}

/** 读取当前账号的本地对话消息。 */
function loadChatMessages() {
  try {
    const raw = localStorage.getItem(storageKey());
    return raw ? _normalize(JSON.parse(raw)).messages : [];
  } catch (e) {
    console.warn('[chatStore] 对话读取失败', e);
    return [];
  }
}

/** 覆盖保存当前账号的本地对话（自动裁剪）。 */
function saveChatMessages(messages) {
  const data = {
    version: VERSION,
    updated_at: new Date().toISOString(),
    messages: _trim(Array.isArray(messages) ? messages : []),
  };
  try {
    localStorage.setItem(storageKey(), JSON.stringify(data));
  } catch (e) {
    // 配额不足时丢弃一半旧消息再试一次，不阻塞聊天
    data.messages = _trim(data.messages.slice(Math.max(0, Math.floor(data.messages.length / 2))));
    try {
      localStorage.setItem(storageKey(), JSON.stringify(data));
    } catch (e2) {
      console.warn('[chatStore] 对话持久化失败（可能是存储空间不足）', e2);
    }
  }
  return data.messages;
}

function appendChatMessage(role, content, time) {
  if (role !== 'user' && role !== 'assistant') return loadChatMessages();
  const text = String(content || '');
  if (!text.trim()) return loadChatMessages();
  const messages = loadChatMessages();
  messages.push({ role, content: text, time: time || new Date().toISOString() });
  return saveChatMessages(messages);
}

/** 一次完整问答结束后保存 user + assistant 两条消息。 */
function appendChatTurn(userContent, assistantContent, userTime, assistantTime) {
  const messages = loadChatMessages();
  const now = new Date().toISOString();
  if (String(userContent || '').trim()) {
    messages.push({ role: 'user', content: String(userContent), time: userTime || now });
  }
  if (String(assistantContent || '').trim()) {
    messages.push({ role: 'assistant', content: String(assistantContent), time: assistantTime || now });
  }
  return saveChatMessages(messages);
}

function clearChatMessages() {
  try {
    localStorage.removeItem(storageKey());
  } catch (e) {
    console.warn('[chatStore] 清空对话失败', e);
  }
}

export {
  currentUser,
  loadChatMessages,
  saveChatMessages,
  appendChatMessage,
  appendChatTurn,
  clearChatMessages,
};
Object.assign(window, {
  cmChatStore: { currentUser, loadChatMessages, saveChatMessages, appendChatMessage, appendChatTurn, clearChatMessages },
});
