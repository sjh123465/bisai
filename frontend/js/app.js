/**
 * @file 应用主入口：认证 / Tab 切换 / SSE 对话 / 代码面板 / 多模态 / 初始化
 * @module app
 */
import { API } from './core/env.js';
import { addMessage, updateMessage, jsStr, escapeHtml } from './core/render.js';
import { attachStatusBox, updateStatus, collapseStatus } from './core/status.js';
import { llmHeaders, hasLLMSettings } from './core/llmSettings.js';
import { getProfileSummary, getWeakPoints } from './core/localStore.js';
import { loadChatMessages, appendChatMessage, appendChatTurn, clearChatMessages } from './core/chatStore.js';
// 设置窗口与班级/作业 UI 通过 window 暴露内联事件入口
import './features/settings.js';
import './features/classroom.js';
import './features/profile.js';
import { loadGraph } from './features/graph.js';
import { loadTeacher } from './features/analytics.js';
import { loadExamConcepts, quickExam } from './features/exam.js';
// 语音模块只注册 window.toggleVoiceInput（由 HTML 内联 onclick 调用），无需命名导入
import './features/voice.js';

  marked.setOptions({
    breaks: true,
    gfm: true,
  });
  let chatHistory = [];
  let isStreaming = false;

  function _formatChatTime(iso) {
    if (!iso) return '';
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return '';
    return d.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' });
  }

  function _removeRenderedChat() {
    document.querySelectorAll('#chat-messages .chat-msg-wrap, #chat-messages .cm-status-summary').forEach(el => el.remove());
  }

  function _renderStoredMessage(msg) {
    const wrap = addMessage(
      msg.role,
      msg.role === 'assistant' ? '' : msg.content,
      false,
      _formatChatTime(msg.time),
    );
    if (msg.role === 'assistant') updateMessage(wrap, msg.content, false);
  }

  /** 切换/恢复当前账号的本地对话；greeting 只在新账号没有任何历史时写入。 */
  function reloadChatForCurrentUser({ greeting = '' } = {}) {
    const box = document.getElementById('chat-messages');
    const welcome = document.getElementById('chat-welcome');
    if (!box) return;
    _removeRenderedChat();
    let messages = loadChatMessages();
    if (!messages.length && greeting) {
      appendChatMessage('assistant', greeting, new Date().toISOString());
      messages = loadChatMessages();
    }
    chatHistory = messages.map(m => ({ role: m.role, content: m.content }));
    if (!messages.length) {
      if (welcome) welcome.classList.remove('hidden');
      box.scrollTop = 0;
      return;
    }
    if (welcome) welcome.classList.add('hidden');
    messages.forEach(_renderStoredMessage);
    box.scrollTop = box.scrollHeight;
  }

  function clearChatUI() {
    if (isStreaming) {
      alert('请等待当前回答生成完成后再清空对话。');
      return;
    }
    if (!confirm('确定清空当前账号的本地对话记录吗？此操作只影响当前浏览器。')) return;
    clearChatMessages();
    chatHistory = [];
    _removeRenderedChat();
    const welcome = document.getElementById('chat-welcome');
    if (welcome) welcome.classList.remove('hidden');
    const box = document.getElementById('chat-messages');
    if (box) box.scrollTop = 0;
  }

  // ---------- 认证：全局 fetch 拦截 ----------
  const _origFetch = window.fetch.bind(window);
  window.fetch = async function(input, init = {}) {
    const url = typeof input === 'string' ? input : (input && input.url) || '';
    const isApi = url.startsWith('/api') || url.startsWith(API);
    if (isApi) {
      const authHeaders = {};
      if (!url.includes('/auth/login') && !url.includes('/auth/register')) {
        const token = localStorage.getItem('cm_token');
        if (token) authHeaders['Authorization'] = 'Bearer ' + token;
      }
      // 用户自己的远程模型 Key：只放在请求头里，后端不落盘。
      // 显式传入的 X-LLM-* 头（如设置窗口的连接测试）优先于已保存配置。
      const modelHeaders = llmHeaders();
      init.headers = Object.assign({}, modelHeaders, init.headers, authHeaders);
    }
    const resp = await _origFetch(input, init);
    // 后台定时刷新教师数据时的 401 不自动弹登录框，避免每 30 秒打扰用户；
    // 用户主动操作（聊天、答题等）遇到 401 时才提示登录。
    if (resp.status === 401 && isApi && !url.includes('/auth/') && !url.includes('/teacher/')) {
      showLoginHint('请先登录（演示账号 teacher/123456 或 student/123456）');
    }
    return resp;
  };

  function openLogin() {
    const msg = document.getElementById('login-msg');
    if (msg) { msg.textContent = ''; msg.className = 'hidden'; }
    document.getElementById('login-modal').classList.remove('hidden');
    setTimeout(() => document.getElementById('login-user').focus(), 100);
  }
  function closeLogin() { document.getElementById('login-modal').classList.add('hidden'); }

  function showLoginHint(msg) {
    openLogin();
    const el = document.getElementById('login-msg');
    el.textContent = msg;
    el.className = 'msg-err mb-3';
    el.classList.remove('hidden');
  }

  function fillDemo(role) {
    const u = document.getElementById('login-user');
    const p = document.getElementById('login-pass');
    const r = document.getElementById('login-role');
    u.value = role; p.value = '123456'; r.value = role;
    u.focus();
    document.getElementById('login-msg').classList.add('hidden');
  }

  // ---------- 全局快捷键 ----------
  document.addEventListener('keydown', (e) => {
    // Esc 关闭弹窗
    if (e.key === 'Escape') {
      closeLogin();
    }
    // Ctrl+Enter / Cmd+Enter 发送消息
    if ((e.ctrlKey || e.metaKey) && e.key === 'Enter' && !document.getElementById('login-modal').classList.contains('hidden')) {
      doLogin('login'); return;
    }
  });

  // 登录输入框 Enter 提交
  ['login-user', 'login-pass'].forEach(id => {
    const el = document.getElementById(id);
    if (el) el.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') doLogin('login');
    });
  });

  function refreshUserUI() {    const token = localStorage.getItem('cm_token');
    const user = localStorage.getItem('cm_user');
    const role = localStorage.getItem('cm_role');
    const chip = document.getElementById('user-chip');
    if (token && user) {
      chip.innerHTML = '<svg class="cm-icon cm-icon-sm" aria-hidden="true"><use href="#i-user"></use></svg>'
        + escapeHtml(user) + '<span class="footnote">· ' + (role === 'teacher' ? '教师' : '学生') + '</span>';
      chip.classList.remove('hidden'); chip.classList.add('flex');
      document.getElementById('btn-login').classList.add('hidden');
      document.getElementById('btn-logout').classList.remove('hidden');
    } else {
      chip.classList.add('hidden');
      document.getElementById('btn-login').classList.remove('hidden');
      document.getElementById('btn-logout').classList.add('hidden');
    }
    window.updateRoleUI?.();
  }

  function doLogout() {
    localStorage.removeItem('cm_token');
    localStorage.removeItem('cm_user');
    localStorage.removeItem('cm_role');
    refreshUserUI();
    reloadChatForCurrentUser();
    window.loadStudentAssignments?.();
  }

  async function doLogin(mode) {
    const username = document.getElementById('login-user').value.trim();
    const password = document.getElementById('login-pass').value;
    const role = document.getElementById('login-role').value;
    const msg = document.getElementById('login-msg');
    if (!username || !password) { msg.textContent = '请输入用户名和密码'; msg.className = 'msg-err mb-3'; return; }
    try {
      const resp = await _origFetch(API + '/auth/' + mode, {
        method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ username, password, role }),
      });
      const data = await resp.json();
      if (!resp.ok) { msg.textContent = data.detail || '登录失败'; msg.className = 'msg-err mb-3'; return; }
      localStorage.setItem('cm_token', data.token);
      localStorage.setItem('cm_user', data.username);
      localStorage.setItem('cm_role', data.role);
      refreshUserUI();
      closeLogin();
      window.updateRoleUI?.();
      // 登录成功后显示当前账号的本地对话；新账号没有历史时写入一条欢迎语
      const welcomeMsg = data.role === 'teacher'
        ? `欢迎回来，${data.username}。已为你切到「学情」。\n\n你可以：\n- 查看班级作业完成情况与薄弱知识点\n- 创建班级并批量布置统一作业\n- 生成班级学情分析报告`
        : `欢迎，${data.username}。可以从这里开始：\n\n- 直接问：「红黑树和 AVL 有什么区别？」\n- 切到「练一练」开始做题\n- 在「图谱」里浏览学科结构`;
      reloadChatForCurrentUser({ greeting: welcomeMsg });
      if (data.role === 'teacher') switchTab('teacher');
    } catch (e) {
      msg.textContent = '网络错误：' + e.message; msg.className = 'msg-err mb-3';
    }
  }

  refreshUserUI();
  window.updateLLMStatus?.();
  switchTab('chat'); // 初始化 Tab 面板显隐（刷新后主区空白的根因）
  reloadChatForCurrentUser(); // 刷新后恢复当前账号的本地对话

  // ---------- 启动检查 ----------
  async function checkAPI() {
    try {
      const resp = await fetch('/health');
      const data = await resp.json();
      if (data.status === 'ok') {
        const el = document.getElementById('api-status');
        el.dataset.status = 'online';
        el.innerHTML = '<span class="status-dot"></span><span>后端在线</span>';
      }
    } catch(e) {
      const el = document.getElementById('api-status');
      el.dataset.status = 'offline';
      el.innerHTML = '<span class="status-dot"></span><span>后端离线</span>';
      const tip = document.getElementById('api-tip');
      if (tip) tip.classList.remove('hidden');
    }
  }
  checkAPI();

  // ---------- Tab 切换 ----------
  /**
   * 切换主区 Tab（对话 / 练一练 / 图谱 / 学情），并同步右侧边栏与懒加载数据。
   * @param {'chat'|'practice'|'graph'|'teacher'} name - Tab 标识
   * @returns {void}
   */
  function switchTab(name) {
    ['chat','practice','graph','teacher'].forEach(t => {
      const p = document.getElementById('panel-' + t);
      const b = document.getElementById('tab-' + t);
      if (t === name) {
        p.classList.remove('hidden');
        b.classList.add('active');
      } else {
        p.classList.add('hidden');
        b.classList.remove('active');
      }
    });
    updateSidebar(name);
    if (name === 'graph') loadGraph();
    if (name === 'teacher') { loadTeacher(); window.refreshProgressCurve?.(); }
    if (name === 'practice') {
      loadExamConcepts();
      window.refreshTodayStats?.();
      window.loadStudentAssignments?.();
    }
  }

  // 根据当前 Tab 显示所有 data-tabs 元素（通用：右侧边栏 + 输入栏快捷操作等）
  function updateSidebar(tab) {
    document.querySelectorAll('[data-tabs]').forEach(el => {
      const tabs = (el.dataset.tabs || '').split(',');
      if (tabs.includes(tab)) el.classList.remove('hidden');
      else el.classList.add('hidden');
    });
    if (tab === 'practice') loadSidePractice();
    if (tab === 'teacher') loadSideWeak();
  }

  // 练一练：热门知识点一键出题
  async function loadSidePractice() {
    const list = document.getElementById('side-practice-list');
    if (list.dataset.loaded) return;
    try {
      const g = await fetch(API + '/knowledge/graph').then(r => r.json());
      // 选非章节节点，按连接度排序取前 12（图谱 API 不返回 _deg，前端用边计算）
      const degree = {};
      (g.edges || []).forEach(e => {
        degree[e.source] = (degree[e.source] || 0) + 1;
        degree[e.target] = (degree[e.target] || 0) + 1;
      });
      const concepts = (g.nodes || [])
        .filter(n => n.category !== 'chapter')
        .sort((a, b) => (degree[b.id] || 0) - (degree[a.id] || 0))
        .slice(0, 12);
      if (concepts.length === 0) { list.innerHTML = '<span class="text-xs text-slate-500">暂无知识点</span>'; return; }
      list.innerHTML = concepts.map(c =>
        `<button onclick="quickExam(${jsStr(c.id)},'编程题')" class="quick-chip">${escapeHtml(c.name || c.id)}</button>`
      ).join('');
      list.dataset.loaded = '1';
    } catch (e) {
      list.innerHTML = '<span class="text-xs text-rose-400">加载失败</span>';
    }
  }

  // 学情：薄弱知识点 Top 3
  async function loadSideWeak() {
    const list = document.getElementById('side-weak-list');
    const role = localStorage.getItem('cm_role');
    if (role !== 'teacher') {
      const weak = getWeakPoints(0.6, 3);
      if (!weak.length) {
        list.innerHTML = '<p class="text-xs text-slate-500">暂无本地薄弱知识点 · 去练一练生成画像</p>';
        return;
      }
      const rank = ['01', '02', '03'];
      list.innerHTML = weak.map((item, i) => `
        <div class="flex items-center gap-2 text-xs">
          <span class="w-5 font-serif text-[10px] text-slate-500">${rank[i]}</span>
          <span class="flex-1 text-slate-200 truncate">${escapeHtml(item.name || item.concept_id)}</span>
          <span class="text-amber-300">${Math.round((item.mastery || 0) * 100)}%</span>
        </div>
      `).join('');
      return;
    }
    // 教师：直接使用班级看板缓存的作业错题榜，不再读取个人错题本
    const top = (window.__teacherDashboard?.wrong_ranking || []).slice(0, 3);
    if (!top.length) {
      list.innerHTML = '<p class="text-xs text-slate-500">暂无作业错题数据</p>';
      return;
    }
    const rank = ['01','02','03'];
    list.innerHTML = top.map((item, i) => `
      <div class="flex items-center gap-2 text-xs">
        <span class="w-5 font-serif text-[10px] text-slate-500">${rank[i]}</span>
        <span class="flex-1 text-slate-200 truncate">${escapeHtml(item.concept_name || item.concept_id || '')}</span>
        <span class="text-rose-300">错 ${escapeHtml(String(item.wrong_count ?? 0))}</span>
      </div>
    `).join('');
  }

  /**
   * SSE 流事件（与后端 app/routers/chat.py 的 _sse 保持一致）。
   * @typedef {{type:'start'}
   *   | {type:'status', stage:string, detail:string}
   *   | {type:'chunk', content:string}
   *   | {type:'end', full_length:number}} ChatStreamEvent
   */

  /**
   * 发送一条消息：POST /api/chat/stream，按 SSE 事件增量渲染，结束后折叠思考步骤。
   * @returns {Promise<void>}
   */
  async function sendMessage() {
    if (isStreaming) return;
    const input = document.getElementById('user-input');
    const message = input.value.trim();
    if (!message) return;
    if (!hasLLMSettings()) {
      window.requireLLMConfigured?.();
      return;
    }

    const code = document.getElementById('code-input').value.trim();
    const userTime = new Date().toISOString();
    input.value = '';
    isStreaming = true;
    hideWelcome();
    document.getElementById('send-btn').disabled = true;

    // 用户消息
    addMessage('user', message, false, _formatChatTime(userTime));

    // AI 消息占位
    const aiWrap = addMessage('assistant', '', true);
    const statusBox = attachStatusBox(aiWrap);
    let buffer = '';

    try {
      const resp = await fetch(API + '/chat/stream', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
          message,
          code: code || null,
          history: chatHistory.slice(-12),
          // 本地学情摘要：只用于本次 Prompt，后端不持久化
          profile: getProfileSummary(),
        })
      });
      if (!resp.ok) throw new Error('HTTP ' + resp.status);

      const reader = resp.body.getReader();
      const decoder = new TextDecoder();
      let sseBuffer = '';

      while (true) {
        const {done, value} = await reader.read();
        if (done) break;
        sseBuffer += decoder.decode(value, {stream: true});

        // 处理 SSE 事件
        let idx;
        while ((idx = sseBuffer.indexOf('\n\n')) !== -1) {
          const raw = sseBuffer.substring(0, idx);
          sseBuffer = sseBuffer.substring(idx + 2);
          const lines = raw.split('\n');
          let data = null;
          for (const ln of lines) {
            if (ln.startsWith('data: ')) {
              try { data = JSON.parse(ln.substring(6)); } catch(_) {}
            }
          }
          if (!data) continue;

          if (data.type === 'status') {
            updateStatus(statusBox, data.stage, data.detail);
          } else if (data.type === 'chunk') {
            buffer += data.content;
            updateMessage(aiWrap, buffer, true);
          } else if (data.type === 'end') {
            updateMessage(aiWrap, buffer, false);
            collapseStatus(statusBox);
            trackTopics(buffer);
          }
        }
      }

      // 保存历史：内存供本轮请求使用，同时写入当前账号的本地持久化
      chatHistory.push({role: 'user', content: message});
      chatHistory.push({role: 'assistant', content: buffer});
      appendChatTurn(message, buffer, userTime, new Date().toISOString());
    } catch(e) {
      collapseStatus(statusBox);
      updateMessage(aiWrap, '请求失败：' + e.message + '\n\n请确认后端已启动，并在右上角「配置模型」中填写你自己的远程 API Key', false);
    } finally {
      isStreaming = false;
      document.getElementById('send-btn').disabled = false;
    }
  }

  function sendQuick(msg) {
    switchTab('chat');
    hideWelcome();
    document.getElementById('user-input').value = msg;
    sendMessage();
  }

  /** 点击欢迎页能力卡片：隐藏欢迎区并直接发起示例提问 */
  function startFromCard(prompt) {
    switchTab('chat');
    hideWelcome();
    sendQuick(prompt);
  }

  function hideWelcome() {
    const w = document.getElementById('chat-welcome');
    if (w) w.classList.add('hidden');
  }

  // ---------- 对话涉及知识点追踪 ----------
  const chatTopics = new Map(); // nodeId -> {name, hits}

  /** 从回答内容里提取图谱节点引用（graph: 链接、节点名、工具徽章） */
  function trackTopics(text) {
    if (!text) return;
    // [名称](graph:节点ID)
    let m;
    const re = /\[([^\]]+)\]\(graph:([^)]+)\)/g;
    while ((m = re.exec(text)) !== null) {
      addTopic(m[2], m[1]);
    }
    renderTopics();
  }

  function addTopic(id, name) {
    const cur = chatTopics.get(id) || { name: name || id, hits: 0 };
    cur.hits += 1;
    if (name) cur.name = name;
    chatTopics.set(id, cur);
  }

  function renderTopics() {
    const list = document.getElementById('side-topic-list');
    const count = document.getElementById('side-topic-count');
    if (!list) return;
    if (chatTopics.size === 0) {
      list.innerHTML = '<p class="text-[11px] text-slate-500">发消息后，AI 命中的图谱节点会自动出现在这里</p>';
      if (count) count.textContent = '0 个';
      return;
    }
    if (count) count.textContent = chatTopics.size + ' 个';
    list.innerHTML = Array.from(chatTopics.entries()).slice(0, 8).map(([id, t]) =>
      `<button onclick="focusGraphNode(${jsStr(id)})" title="点击定位到图谱" class="graph-chip">
        ${escapeHtml(t.name || id)}${t.hits > 1 ? ' ×' + t.hits : ''}
      </button>`
    ).join('');
  }

  function clearTopics() {
    chatTopics.clear();
    renderTopics();
  }







  function toggleCodePanel() {
    const p = document.getElementById('code-panel');
    p.classList.toggle('hidden');
  }
  function clearCode() {
    document.getElementById('code-input').value = '';
    document.getElementById('code-output').classList.add('hidden');
  }

  async function runCode() {
    const code = document.getElementById('code-input').value;
    if (!code.trim()) return alert('请先输入代码');
    const out = document.getElementById('code-output');
    out.classList.remove('hidden');
    out.textContent = '沙箱执行中...';
    try {
      const resp = await fetch(API + '/code/execute', {
        method: 'POST', headers: {'Content-Type':'application/json'},
        body: JSON.stringify({code})
      });
      const data = await resp.json();
      out.textContent = data.success
        ? `执行成功 (${data.execution_time}s)\n\n${data.output || '(无输出)'}`
        : `执行失败\n\n${data.output || ''}\n${data.error || ''}`;
    } catch(e) { out.textContent = '执行失败：' + e.message; }
  }

  async function analyzeCode() {
    const code = document.getElementById('code-input').value;
    if (!code.trim()) return alert('请先输入代码');
    const out = document.getElementById('code-output');
    out.classList.remove('hidden');
    out.textContent = 'AST 分析中...';
    try {
      const resp = await fetch(API + '/code/analyze', {
        method: 'POST', headers: {'Content-Type':'application/json'},
        body: JSON.stringify({code})
      });
      const data = await resp.json();
      out.textContent = data.text;
    } catch(e) { out.textContent = '分析失败：' + e.message; }
  }

  // ==================== 多模态截图提问 ====================
  async function uploadImage(event) {
    const file = event.target.files[0];
    if (!file) return;
    if (!hasLLMSettings()) {
      window.requireLLMConfigured?.();
      event.target.value = '';
      return;
    }
    const reader = new FileReader();
    reader.onload = async (e) => {
      const dataUrl = e.target.result;   // 完整 data URL，保留真实 MIME（png/jpeg 等）
      const q = document.getElementById('user-input').value.trim() || '这张图里有什么算法或数据结构？请详细讲解。';
      const userTime = new Date().toISOString();
      const userLabel = `[图片] ${file.name}\n${q}`;
      hideWelcome();
      const wrap = addMessage('user', userLabel, false, _formatChatTime(userTime));
      // 直接在用户消息后追加图片预览（文件名可能来自本地任意字符，必须转义）
      const bubble = wrap.querySelector('.prose-cm');
      bubble.innerHTML = `<div><div class="text-xs text-slate-400 mb-1">上传图片：${escapeHtml(file.name)}</div><img src="${e.target.result}" class="max-w-xs rounded-lg inline-block" /><div class="mt-1 text-xs text-slate-400">${escapeHtml(q)}</div></div>`;

      const aiWrap = addMessage('assistant', '正在识别图片...', true);
      try {
        const res = await fetch('/api/multimodal/analyze', {
          method: 'POST', headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({image: dataUrl, question: q})
        }).then(r => r.json());
        if (res.ok) {
          updateMessage(aiWrap, res.answer, false);
          chatHistory.push({ role: 'user', content: userLabel });
          chatHistory.push({ role: 'assistant', content: res.answer || '' });
          appendChatTurn(userLabel, res.answer || '', userTime, new Date().toISOString());
        } else {
          updateMessage(aiWrap, `${res.message || '多模态调用失败'}`, false);
        }
      } catch (err) {
        updateMessage(aiWrap, `调用失败：${err}`, false);
      }
    };
    reader.readAsDataURL(file);
    event.target.value = '';
  }

// HTML 内联 onclick / onchange 需要全局可见
Object.assign(window, { openLogin, closeLogin, showLoginHint, fillDemo, refreshUserUI, doLogout, doLogin, checkAPI, switchTab, updateSidebar, loadSidePractice, loadSideWeak, sendMessage, sendQuick, startFromCard, trackTopics, clearTopics, hideWelcome, toggleCodePanel, clearCode, runCode, analyzeCode, uploadImage, reloadChatForCurrentUser, clearChatUI });
