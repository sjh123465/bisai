/**
 * @file Markdown 渲染 / XSS 消毒 / 代码高亮 / 消息气泡
 * @module core/render
 */
import { API } from './env.js';

  // ---------- 消息渲染增强（工具徽章 + 图谱节点卡片） ----------
  // 代码语言名映射（短名 → 展示名）
  const LANG_MAP = {
    py:'Python', python:'Python', js:'JavaScript', javascript:'JavaScript',
    ts:'TypeScript', java:'Java', c:'C', cpp:'C++', csharp:'C#', go:'Go',
    rs:'Rust', rb:'Ruby', php:'PHP', sql:'SQL', bash:'Bash', sh:'Shell',
    html:'HTML', css:'CSS', json:'JSON', yaml:'YAML', md:'Markdown',
  };

  function escapeHtml(s) {
    return String(s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  }

  // 把任意文本安全地嵌进 onclick="fn('...')"：先做 JS 字面量转义，再做 HTML 属性转义
  function jsStr(s) {
    const lit = "'" + String(s)
      .replace(/\\/g, '\\\\')
      .replace(/'/g, "\\'")
      .replace(/[\r\n]+/g, ' ') + "'";
    return lit.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }

  // 轻量兜底消毒器 —— DOMPurify 未加载成功（CDN 不可达）时使用，保证功能不中断
  function fallbackSanitize(html, allowDataAttrs) {
    const tpl = document.createElement('template');
    tpl.innerHTML = html || '';
    // 1. 移除危险标签
    tpl.content.querySelectorAll('script,style,iframe,object,embed,link,meta,base,form').forEach(el => el.remove());
    // 2. 清理危险属性
    tpl.content.querySelectorAll('*').forEach(el => {
      Array.from(el.attributes).forEach(attr => {
        const name = attr.name.toLowerCase();
        const val = (attr.value || '').replace(/[\s\u0000]/g, '').toLowerCase();
        if (name.startsWith('on')) { el.removeAttribute(attr.name); return; }
        if (name === 'srcdoc') { el.removeAttribute(attr.name); return; }
        if ((name === 'href' || name === 'src' || name === 'xlink:href') && val.startsWith('javascript:')) {
          el.removeAttribute(attr.name);
        }
      });
    });
    return tpl.innerHTML;
  }

  // 统一消毒入口：优先 DOMPurify，不可用时退回本地兜底
  function sanitizeHtml(html, opts) {
    if (typeof DOMPurify !== 'undefined' && DOMPurify && typeof DOMPurify.sanitize === 'function') {
      return DOMPurify.sanitize(html, opts || {});
    }
    if (!window.__cmDpWarned) {
      window.__cmDpWarned = true;
      console.warn('[CodeMentor] DOMPurify 未加载，已启用本地兜底消毒。请检查 CDN 网络。');
    }
    return fallbackSanitize(html, opts && opts.ADD_ATTR);
  }

  /**
   * 把 LLM 返回的 Markdown 渲染成可安全插入 DOM 的 HTML。
   * @param {string} text - 原始 Markdown 文本
   * @returns {string} 经 DOMPurify 消毒的 HTML 字符串
   */
  function mdSafe(text) {
    return sanitizeHtml(marked.parse(text || ''));
  }

  /**
   * 对话气泡专用渲染流水线：去思考注释 → 工具徽章 → 图谱节点卡片 → 代码高亮 → 消毒。
   * @param {string} content - Agent 流式输出的原始文本
   * @returns {string} 可直接写入 innerHTML 的 HTML
   */
  function renderContent(content) {
    content = content || '';
    // 1. 移除 thinking 注释
    content = content.replace(/<!--thinking:[\s\S]*?-->/g, '');
    // 2. 提取工具调用行，转成占位符（消毒后再还原为徽章）
    const tools = [];
    content = content.replace(/>\s*\*📎\s*工具\s*`([^`]+)`[^*\n]*\*/g, (m, t) => { tools.push(t); return `__TOOL${tools.length-1}__`; });
    // 额外：隐藏 agent 内部暴露的 TOOL N 编号标记
    content = content.replace(/\bTOOL\d+\b/g, '');
    // 3. Markdown 渲染
    let html = marked.parse(content);
    // 4. [text](graph:id) → 先转成带 data 属性的 span（graph: 协议会被消毒器移除 href，故提前转换）
    html = html.replace(/<a href="graph:([^"]+)">([^<]+)<\/a>/g,
      (m, id, text) => `<span class="graph-chip" data-graph-id="${id}">${text}</span>`);
    // 5. XSS 消毒（marked v5+ 默认不消毒）
    html = sanitizeHtml(html, { ADD_ATTR: ['data-graph-id'] });
    // 6. 消毒后还原图谱节点卡片（onclick 由本地生成，必须对 id 做 JS/HTML 双重转义）
    html = html.replace(/<span class="graph-chip" data-graph-id="([^"]+)">/g,
      (m, id) => `<span class="graph-chip" onclick="askAboutGraph(${jsStr(id)})" title="点击就该知识点提问">`);
    // 7. 插入工具徽章（工具名来自 LLM，需转义）
    tools.forEach((t, i) => {
      html = html.replace(`__TOOL${i}__`,
        `<span class="tool-badge"><svg class="cm-icon cm-icon-sm" aria-hidden="true"><use href="#i-settings"></use></svg>工具 · ${escapeHtml(t)}</span><br>`);
    });
    // 8. 代码块增强：语法高亮 + 语言标签 + 复制按钮
    html = enhanceCodeBlocks(html);
    // 9. 最终兜底：移除裸的 TOOL 编号标记
    html = html.replace(/<strong>\s*TOOL\d+\s*<\/strong>/gi, '');
    html = html.replace(/\bTOOL\d+\b/gi, '');
    // 清理多余空行
    html = html.replace(/(<br>\s*){3,}/g, '<br><br>');
    return html;
  }

  // 给 HTML 中的 <pre><code class="language-xxx"> 注入语言标签和复制按钮
  function enhanceCodeBlocks(html) {
    const wrap = document.createElement('div');
    wrap.innerHTML = html;
    wrap.querySelectorAll('pre').forEach(pre => {
      const code = pre.querySelector('code');
      let lang = 'CODE';
      if (code) {
        const cls = code.className.match(/language-(\w+)/);
        if (cls) {
          lang = LANG_MAP[cls[1].toLowerCase()] || cls[1].toUpperCase();
          pre.classList.add('code-block');
          pre.setAttribute('data-lang', lang);
        }
        // 语法高亮（marked v5+ 已移除 highlight 选项，这里显式调用 hljs）
        const raw = code.textContent;
        if (raw.trim()) {
          try {
            code.innerHTML = (cls && hljs.getLanguage(cls[1]))
              ? hljs.highlight(raw, { language: cls[1] }).value
              : hljs.highlightAuto(raw).value;
            code.classList.add('hljs');
          } catch (_) { /* 高亮失败则保留原文 */ }
        }
      }
      // 复制按钮
      const btn = document.createElement('button');
      btn.className = 'code-copy';
      btn.textContent = '复制';
      btn.type = 'button';
      btn.onclick = (e) => {
        const text = code ? code.textContent : pre.textContent;
        navigator.clipboard.writeText(text).then(() => {
          btn.textContent = '已复制';
          btn.classList.add('copied');
          setTimeout(() => { btn.textContent = '复制'; btn.classList.remove('copied'); }, 1500);
        });
      };
      pre.appendChild(btn);
    });
    return wrap.innerHTML;
  }

  function askAboutGraph(nodeId) {
    // 跨模块调用走 window（app.js 在初始化时把 UI 编排函数挂到 window 上）
    window.switchTab('chat');
    document.getElementById('user-input').value = `请详细讲解一下「${nodeId}」这个知识点`;
    window.sendMessage();
  }

  // ---------- 消息渲染 ----------
  /**
   * 向消息列表追加一条气泡。
   * @param {'user'|'assistant'} role - 消息角色
   * @param {string} content - 纯文本内容（用户输入按 textContent 写入，避免 XSS）
   * @param {boolean} [isStreaming=false] - 是否为流式占位（显示打字光标）
   * @returns {HTMLElement} 气泡外层容器，供后续 updateMessage 使用
   */
  function addMessage(role, content, isStreaming = false, timeLabel = '') {
    const container = document.getElementById('chat-messages');
    const wrap = document.createElement('div');
    const time = timeLabel || new Date().toLocaleTimeString('zh-CN', {hour:'2-digit', minute:'2-digit'});
    wrap.className = 'chat-msg-wrap ' + role;
    wrap.innerHTML = `
      <div class="cm-avatar">${role === 'user' ? '你' : 'C'}</div>
      <div class="flex-1 min-w-0">
        <div class="prose-cm cm-bubble ${isStreaming ? 'typing-cursor' : ''}"></div>
      </div>
      <span class="msg-meta">${role === 'user' ? '你' : 'CodeMentor'} · ${time} · <button onclick="copyMsg(this)">复制</button></span>
    `;
    container.appendChild(wrap);
    // 内容用 textContent 写入，避免用户输入被当作 HTML 解析
    wrap.querySelector('.prose-cm').textContent = content || '';
    container.scrollTop = container.scrollHeight;
    return wrap;
  }

  // 复制消息内容
  function copyMsg(btn) {
    const bubble = btn.closest('.chat-msg-wrap').querySelector('.prose-cm');
    const text = bubble.innerText;
    navigator.clipboard.writeText(text).then(() => {
      btn.textContent = '已复制';
      setTimeout(() => btn.textContent = '复制', 1200);
    });
  }

  function updateMessage(wrap, content, isStreaming = false) {
    const bubble = wrap.querySelector('.prose-cm');
    if (isStreaming) {
      bubble.textContent = content;
    } else {
      bubble.classList.remove('typing-cursor');
      bubble.innerHTML = renderContent(content);
      // 仅 AI 消息在流式结束后追加渐进式操作按钮（深入了解/看代码/出题）；
      // 欢迎语、错误提示没有对应的用户提问，不显示
      const originalQuery = _extractUserQuery(wrap);
      const isError = /^(请求失败|回答中断|分析失败|调用失败|工具调度中断)/.test(String(content || '').trim());
      if (
        wrap.classList.contains('assistant')
        && originalQuery
        && !isError
        && !wrap.querySelector('.progressive-actions')
      ) {
        const topicId = _registerTopic(originalQuery);
        const tpl = document.createElement('template');
        tpl.innerHTML = renderProgressiveActions(topicId).trim();
        const actionsEl = tpl.content.firstElementChild;
        bubble.insertAdjacentElement('afterend', actionsEl);
        bindProgressiveActions(actionsEl);
      }
    }
  }

  /** 提取用户提问原文，用于渐进式追问：优先沿 DOM 回溯，其次用发送时记录的原文 */
  function _extractUserQuery(wrap) {
    // 首选：从当前 AI 消息向上回溯最近的用户消息（历史消息与实时消息都适用）
    let prev = wrap.previousElementSibling;
    while (prev) {
      if (prev.classList.contains('user')) {
        return prev.querySelector('.prose-cm')?.textContent?.trim() || '';
      }
      prev = prev.previousElementSibling;
    }
    // 回退：发送时记录的原文（app.js 在添加用户消息时写入 window.__cmLastQuery）
    // 不做「取最后一条用户消息」的全局回退：否则欢迎语等无前置提问的消息也会挂上
    // 历史对话里最后一个问题的按钮。
    const recorded = typeof window.__cmLastQuery === 'string' ? window.__cmLastQuery.trim() : '';
    return recorded;
  }

  // ---------- 渐进式操作按钮 ----------
  // 话题文本存放在模块级注册表，用 addEventListener 绑定而非内联 onclick：
  // 内联拼接会被提问里的换行/引号破坏（如练一练「问 AI 详解」发出的多行完整上下文），
  // 导致按钮点击抛 SyntaxError 而完全无响应；同时避免用户文本进入 HTML 属性。
  const _progressiveTopics = new Map();
  let _progressiveSeq = 0;

  function _registerTopic(topic) {
    const id = 'pt' + (++_progressiveSeq);
    _progressiveTopics.set(id, String(topic || ''));
    return id;
  }

  /** 从原始提问提取短话题：练一练详解上下文取【题目】行，普通提问取首行并截断 */
  function _shortTopic(raw) {
    let t = String(raw || '').trim();
    if (!t) return '这个知识点';
    const m = t.match(/【题目】\s*([^\n]+)/);
    t = m ? m[1] : t.split('\n')[0];
    t = t.replace(/^(问题[:：]|请|帮我)\s*/, '').replace(/\s+/g, ' ').trim();
    if (t.length > 24) t = t.slice(0, 24) + '…';
    return t || '这个知识点';
  }

  /** 渲染渐进式操作按钮：深入了解 / 看代码 / 出题考考我 */
  function renderProgressiveActions(topicId) {
    return `
      <div class="progressive-actions flex flex-wrap gap-2 mt-3" data-topic-id="${topicId}">
        <button data-qa="deep" class="btn btn-ghost btn-sm">
          <svg class="cm-icon cm-icon-sm" aria-hidden="true"><use href="#i-book"></use></svg>深入了解
        </button>
        <button data-qa="code" class="btn btn-ghost btn-sm">
          <svg class="cm-icon cm-icon-sm" aria-hidden="true"><use href="#i-code"></use></svg>看代码
        </button>
        <button data-qa="quiz" class="btn btn-ghost btn-sm">
          <svg class="cm-icon cm-icon-sm" aria-hidden="true"><use href="#i-practice"></use></svg>出题考考我
        </button>
      </div>
    `;
  }

  /** 给渐进式按钮绑定点击事件：按短话题生成追问语并发送到对话 */
  function bindProgressiveActions(el) {
    const raw = _progressiveTopics.get(el.dataset.topicId) || '';
    const short = _shortTopic(raw);
    const prompts = {
      deep: `请深入讲解「${short}」的核心原理和关键细节`,
      code: `给我一个「${short}」的 Python 代码示例，并逐行解释`,
      quiz: `出几道关于「${short}」的练习题考我`,
    };
    el.querySelectorAll('button[data-qa]').forEach(btn => {
      btn.addEventListener('click', () => {
        const p = prompts[btn.dataset.qa];
        if (p && window.sendQuick) window.sendQuick(p);
      });
    });
  }

// 导出 + 供 HTML 内联 onclick 使用
export { LANG_MAP, escapeHtml, jsStr, sanitizeHtml, mdSafe, renderContent, enhanceCodeBlocks, askAboutGraph, addMessage, updateMessage, copyMsg };
Object.assign(window, { LANG_MAP, escapeHtml, jsStr, sanitizeHtml, mdSafe, renderContent, enhanceCodeBlocks, askAboutGraph, addMessage, updateMessage, copyMsg });
