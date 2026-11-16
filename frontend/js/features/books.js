/**
 * @file 我的书架 — 上传电子书、查看处理进度、选择知识范围
 * @module features/books
 *
 * 书籍只对上传者可见；解析/向量化在服务端后台进行。
 * 本模块只操作 UI 与 localStorage，检索逻辑由后端 KnowledgeRouter 完成。
 */
import { escapeHtml } from '../core/render.js';
import {
  getKnowledgeScope,
  saveKnowledgeScope,
  pruneKnowledgeScope,
  removeBookFromScope,
} from '../core/knowledgeScope.js';

let _books = [];
let _pollTimer = null;
let _maxMb = 50;
let _formats = ['PDF', 'Word', 'TXT', 'Markdown', 'EPUB'];
let _modalOpen = false;

const ALLOWED_EXT = ['.pdf', '.docx', '.txt', '.md', '.markdown', '.epub'];
const STATUS_META = {
  pending: ['排队中', 'info'],
  parsing: ['解析中', 'info'],
  embedding: ['向量化', 'warning'],
  ready: ['可用', 'success'],
  failed: ['失败', 'danger'],
  needs_reindex: ['待重建', 'warning'],
};

function _loggedIn() {
  return !!(localStorage.getItem('cm_token') && localStorage.getItem('cm_user'));
}

function _msg(text, ok = false) {
  const el = document.getElementById('books-msg');
  if (!el) return;
  el.textContent = text;
  el.className = ok ? 'msg-ok mb-3' : 'msg-err mb-3';
  el.classList.remove('hidden');
}

function _clearMsg() {
  document.getElementById('books-msg')?.classList.add('hidden');
}

function _fmtSize(bytes) {
  const n = Number(bytes) || 0;
  if (n >= 1024 * 1024) return (n / 1024 / 1024).toFixed(1) + ' MB';
  if (n >= 1024) return (n / 1024).toFixed(0) + ' KB';
  return n + ' B';
}

function _statusLabel(status) {
  const [label, tone] = STATUS_META[status] || [status || '未知', 'info'];
  return `<span class="book-status status-${tone}">${escapeHtml(label)}</span>`;
}

function _selectedTitles() {
  const scope = getKnowledgeScope();
  return _books.filter(b => b.status === 'ready' && scope.books.includes(b.id));
}

function _scopeLabel() {
  const scope = getKnowledgeScope();
  const parts = [];
  if (scope.builtin) parts.push('内置课程');
  const titles = _selectedTitles().map(b => `《${b.title}》`);
  if (titles.length) parts.push(titles.join('、'));
  return parts.join(' + ') || '内置课程';
}

function _updateHeader() {
  const btn = document.getElementById('btn-books');
  const count = document.getElementById('books-count');
  if (btn) btn.title = '知识范围：' + _scopeLabel();
  if (!count) return;
  const n = _loggedIn() ? _selectedTitles().length : 0;
  if (n > 0) {
    count.textContent = String(n);
    count.classList.remove('hidden');
  } else {
    count.classList.add('hidden');
  }
}

function _renderScope() {
  const box = document.getElementById('books-scope');
  if (!box) return;
  const scope = getKnowledgeScope();
  box.innerHTML = `
    <div class="books-scope-row">
      <label class="books-check">
        <input type="checkbox" ${scope.builtin ? 'checked' : ''} onchange="toggleBuiltinScope(this.checked)">
        <span class="books-check-text">
          <strong>内置课程库</strong>
          <span class="footnote">86 节点 · 14 篇教材片段 · 图谱 + 向量</span>
        </span>
      </label>
      <span class="book-scope-note">当前：${escapeHtml(_scopeLabel())}</span>
    </div>`;
}

function _renderBooks() {
  const box = document.getElementById('book-list');
  if (!box) return;
  const scope = getKnowledgeScope();
  const formats = _formats.join(' / ');

  if (!_loggedIn()) {
    box.innerHTML = `
      <div class="books-empty">
        <p>登录后可以上传自己的 PDF / Word / 电子书，和内置课程一起检索。</p>
        <button class="btn btn-primary btn-sm mt-2" onclick="openLogin()">登录</button>
      </div>`;
    _updateUploadHint(formats);
    return;
  }

  if (!_books.length) {
    box.innerHTML = `
      <div class="books-empty">
        <p>书架还是空的。上传一本教材或笔记，它会成为本次对话的检索范围。</p>
        <p class="footnote mt-1">支持 ${escapeHtml(formats)}，单文件 ≤ ${_maxMb}MB。</p>
      </div>`;
    _updateUploadHint(formats);
    return;
  }

  const rows = _books.map(book => {
    const selected = scope.books.includes(book.id);
    const ready = book.status === 'ready';
    const progress = Math.max(0, Math.min(100, Number(book.progress) || 0));
    const processing = ['pending', 'parsing', 'embedding'].includes(book.status);
    const canReindex = ['failed', 'needs_reindex'].includes(book.status);
    return `
      <label class="book-item ${selected ? 'selected' : ''} ${ready ? '' : 'disabled'}">
        <input type="checkbox" ${selected ? 'checked' : ''} ${ready ? '' : 'disabled'}
               onchange="toggleBookScope('${book.id}', this.checked)">
        <div class="book-main">
          <div class="book-title">
            ${escapeHtml(book.title || book.filename || '未命名')}
            <span class="book-format">${escapeHtml(book.format || '')}</span>
            ${_statusLabel(book.status)}
          </div>
          <div class="book-meta">
            ${escapeHtml(book.filename || '')} · ${_fmtSize(book.size)} · ${Number(book.chunk_count) || 0} 片
          </div>
          ${processing ? `<div class="book-bar"><span style="width:${progress}%"></span></div>
            <div class="book-meta">处理中 ${progress}%</div>` : ''}
          ${book.error ? `<div class="book-error">${escapeHtml(book.error)}</div>` : ''}
        </div>
        <div class="book-actions">
          ${canReindex ? `<button class="btn btn-ghost btn-xs" onclick="event.preventDefault();event.stopPropagation();reindexBook('${book.id}')">重建索引</button>` : ''}
          <button class="btn btn-quiet btn-xs" onclick="event.preventDefault();event.stopPropagation();deleteBook('${book.id}')">
            <svg class="cm-icon cm-icon-sm" aria-hidden="true"><use href="#i-trash"></use></svg>删除
          </button>
        </div>
      </label>`;
  }).join('');

  box.innerHTML = `
    <div class="book-list-head">
      <span class="eyebrow">我的书架</span>
      <span class="footnote">${_books.length} 本 · 仅自己可见</span>
    </div>
    <div class="book-items">${rows}</div>`;
  _updateUploadHint(formats);
}

function _updateUploadHint(formats) {
  const hint = document.getElementById('books-upload-hint');
  if (hint) hint.textContent = `支持 ${formats}，单文件 ≤ ${_maxMb}MB`;
  const btn = document.getElementById('book-upload-btn');
  if (btn) {
    btn.disabled = !_loggedIn();
    btn.title = _loggedIn() ? '上传电子书' : '请先登录';
  }
}

function _schedulePoll() {
  clearTimeout(_pollTimer);
  if (!_modalOpen) return;
  if (_books.some(b => ['pending', 'parsing', 'embedding'].includes(b.status))) {
    _pollTimer = setTimeout(() => refreshBooks({ silent: true }), 2000);
  }
}

export function openBooks() {
  _modalOpen = true;
  document.getElementById('books-modal')?.classList.remove('hidden');
  _clearMsg();
  _renderScope();
  _renderBooks();
  _updateHeader();
  refreshBooks({ silent: true });
}

export function closeBooks() {
  _modalOpen = false;
  clearTimeout(_pollTimer);
  document.getElementById('books-modal')?.classList.add('hidden');
}

export async function refreshBooks({ silent = false } = {}) {
  if (!_loggedIn()) {
    _books = [];
    _renderScope();
    _renderBooks();
    _updateHeader();
    return;
  }
  try {
    const resp = await fetch('/api/books');
    if (resp.status === 401) {
      _books = [];
      if (!silent) _msg('请先登录后再使用我的书架', false);
    } else {
      const data = await resp.json();
      if (!resp.ok) throw new Error(data.detail || `HTTP ${resp.status}`);
      _books = Array.isArray(data.books) ? data.books : [];
      _maxMb = Number(data.max_mb) || _maxMb;
      _formats = Array.isArray(data.supported_formats) && data.supported_formats.length
        ? data.supported_formats : _formats;
      pruneKnowledgeScope(_books.filter(b => b.status === 'ready').map(b => b.id));
    }
  } catch (e) {
    if (!silent) _msg('读取书架失败：' + (e.message || e), false);
  }
  _renderScope();
  _renderBooks();
  _updateHeader();
  _schedulePoll();
}

export async function handleBookFile(event) {
  const input = event.target;
  const file = input.files && input.files[0];
  if (!file) return;
  if (!_loggedIn()) {
    _msg('请先登录后再上传', false);
    input.value = '';
    return;
  }
  const ext = (file.name.match(/\.[^.]+$/) || [''])[0].toLowerCase();
  if (!ALLOWED_EXT.includes(ext)) {
    _msg(`不支持 ${ext || '该'} 格式，请上传 ${_formats.join(' / ')}`, false);
    input.value = '';
    return;
  }
  if (file.size > _maxMb * 1024 * 1024) {
    _msg(`文件超过 ${_maxMb}MB 上限`, false);
    input.value = '';
    return;
  }

  const form = new FormData();
  form.append('file', file, file.name);
  const btn = document.getElementById('book-upload-btn');
  if (btn) btn.disabled = true;
  _msg('正在上传…', true);
  try {
    const resp = await fetch('/api/books', { method: 'POST', body: form });
    const data = await resp.json().catch(() => ({}));
    if (!resp.ok) throw new Error(data.detail || `HTTP ${resp.status}`);
    _msg('已上传，正在后台解析与向量化；完成后可在列表中勾选。', true);
    await refreshBooks({ silent: true });
    _schedulePoll();
  } catch (e) {
    _msg('上传失败：' + (e.message || e), false);
  } finally {
    input.value = '';
    if (btn) btn.disabled = false;
  }
}

export function toggleBuiltinScope(checked) {
  const scope = getKnowledgeScope();
  const saved = saveKnowledgeScope({ builtin: !!checked, books: scope.books });
  if (!checked && saved.books.length === 0) {
    _msg('至少保留一个知识源：请先勾选一本可用书籍', false);
  }
  _renderScope();
  _updateHeader();
}

export function toggleBookScope(bookId, checked) {
  const scope = getKnowledgeScope();
  const books = checked
    ? [...new Set([...scope.books, bookId])]
    : scope.books.filter(id => id !== bookId);
  saveKnowledgeScope({ builtin: scope.builtin, books });
  _renderScope();
  _renderBooks();
  _updateHeader();
}

export async function deleteBook(bookId) {
  if (!confirm('删除后本书的切片与向量索引都会清除，确定吗？')) return;
  try {
    const resp = await fetch(`/api/books/${encodeURIComponent(bookId)}`, { method: 'DELETE' });
    const data = await resp.json().catch(() => ({}));
    if (!resp.ok) throw new Error(data.detail || `HTTP ${resp.status}`);
    removeBookFromScope(bookId);
    _msg('已删除', true);
    await refreshBooks({ silent: true });
  } catch (e) {
    _msg('删除失败：' + (e.message || e), false);
  }
}

export async function reindexBook(bookId) {
  try {
    const resp = await fetch(`/api/books/${encodeURIComponent(bookId)}/reindex`, { method: 'POST' });
    const data = await resp.json().catch(() => ({}));
    if (!resp.ok) throw new Error(data.detail || `HTTP ${resp.status}`);
    _msg('已开始重建索引…', true);
    await refreshBooks({ silent: true });
    _schedulePoll();
  } catch (e) {
    _msg('重建失败：' + (e.message || e), false);
  }
}

// 供 HTML 内联事件使用；同时在 app.js 登录/退出后刷新
Object.assign(window, {
  openBooks,
  closeBooks,
  refreshBooks,
  handleBookFile,
  toggleBuiltinScope,
  toggleBookScope,
  deleteBook,
  reindexBook,
});
