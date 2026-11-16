/**
 * @file 知识范围选择（内置课程 / 我的书架）
 * @module core/knowledgeScope
 *
 * 选择结果保存在当前账号的 localStorage；请求时随对话发送：
 * - builtin：内置课程图谱 + 教材片段
 * - books  ：当前勾选的用户书籍（book_ids）
 */

const PREFIX = 'cm_knowledge_scope:';

function _user() {
  return localStorage.getItem('cm_user') || 'guest';
}

function _key() {
  return PREFIX + _user();
}

function _loggedIn() {
  return !!(localStorage.getItem('cm_token') && localStorage.getItem('cm_user'));
}

/** 读取当前账号的知识范围；默认只开内置课程。 */
export function getKnowledgeScope() {
  try {
    const raw = localStorage.getItem(_key());
    if (raw) {
      const s = JSON.parse(raw) || {};
      return {
        builtin: s.builtin !== false,
        books: Array.isArray(s.books) ? [...new Set(s.books.filter(Boolean))] : [],
      };
    }
  } catch (_) { /* ignore broken local data */ }
  return { builtin: true, books: [] };
}

/** 保存知识范围；不允许两个来源都为空。 */
export function saveKnowledgeScope(scope) {
  const books = [...new Set((scope.books || []).filter(Boolean))];
  const clean = { builtin: !!scope.builtin, books };
  if (!clean.builtin && books.length === 0) clean.builtin = true;
  localStorage.setItem(_key(), JSON.stringify(clean));
  return clean;
}

/** 构造 /api/chat 需要的知识范围字段。 */
export function knowledgeSourcePayload() {
  if (!_loggedIn()) return { knowledge_sources: ['builtin'], book_ids: [] };
  const s = getKnowledgeScope();
  const sources = [];
  if (s.builtin) sources.push('builtin');
  if (s.books.length) sources.push('books');
  if (!sources.length) sources.push('builtin');
  return { knowledge_sources: sources, book_ids: s.books };
}

/** 书籍被删除/尚不可用时，从选择中剔除。 */
export function pruneKnowledgeScope(readyBookIds) {
  const s = getKnowledgeScope();
  const ready = new Set(readyBookIds || []);
  return saveKnowledgeScope({ builtin: s.builtin, books: s.books.filter(id => ready.has(id)) });
}

export function removeBookFromScope(bookId) {
  const s = getKnowledgeScope();
  return saveKnowledgeScope({ builtin: s.builtin, books: s.books.filter(id => id !== bookId) });
}
