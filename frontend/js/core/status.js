/**
 * @file AI 思考阶段指示器（由 SSE status 事件驱动）
 * @module core/status
 */

  // ---------- 发送消息（SSE 流式） ----------
  // ---------- AI 思考阶段指示器 ----------
  const STATUS_META = {
    planning:   { icon: '🧠', text: '理解问题 · 规划解题思路' },
    replanning: { icon: '🔁', text: '结合工具结果继续规划' },
    tool:       { icon: '🔧', text: '调用工具' },
    tool_done:  { icon: '✅', text: '工具执行完成' },
    answering:  { icon: '✍️', text: '生成引导回答' },
  };

  function attachStatusBox(wrap) {
    const bubble = wrap.querySelector('.prose-cm');
    const box = document.createElement('div');
    box.className = 'cm-status-box';
    bubble.parentElement.insertBefore(box, bubble);
    return box;
  }

  function closeRunning(box) {
    box.querySelectorAll('.cm-status-item.running').forEach(el => {
      el.classList.remove('running');
      el.classList.add('done');
      const sp = el.querySelector('.cm-status-spinner');
      if (sp) sp.textContent = '✓';
      // 「正在 xxx」→「xxx」，已完成项的文案读起来更自然
      const txt = el.querySelector('.cm-status-text');
      if (txt) txt.textContent = txt.textContent.replace(/^正在/, '');
    });
  }

  /**
   * 消费一条 SSE `status` 事件，更新思考阶段列表。
   * @param {HTMLElement|null} box - attachStatusBox 创建的容器
   * @param {'planning'|'replanning'|'tool'|'tool_done'|'answering'} stage - 阶段标识
   * @param {string} [detail] - 阶段描述（如工具名）
   * @returns {void}
   */
  function updateStatus(box, stage, detail) {
    if (!box) return;
    // 工具完成事件：就地收尾上一条「调用工具」行，不新增行
    if (stage === 'tool_done') {
      const last = box.querySelector('.cm-status-item.running');
      if (!last) return;
      last.classList.remove('running');
      last.classList.add('done');
      const sp = last.querySelector('.cm-status-spinner');
      if (sp) sp.textContent = '✓';
      const txt = last.querySelector('.cm-status-text');
      if (txt && detail) txt.textContent = detail;
      return;
    }
    closeRunning(box);
    const meta = STATUS_META[stage] || { icon: '•', text: stage };
    const item = document.createElement('div');
    item.className = 'cm-status-item running';
    if (stage === 'tool') item.dataset.tool = '1';
    item.innerHTML = '<span class="cm-status-spinner"></span>'
      + `<span class="cm-status-icon">${meta.icon}</span>`
      + '<span class="cm-status-text"></span>';
    item.querySelector('.cm-status-text').textContent = detail || meta.text;
    box.appendChild(item);
  }

  // 回答结束后把步骤折叠成一行摘要（可点击展开）
  function collapseStatus(box) {
    if (!box || box.dataset.collapsed) return;
    if (!box.children.length) { box.remove(); return; }
    box.dataset.collapsed = '1';
    closeRunning(box);
    const steps = box.querySelectorAll('.cm-status-item').length;
    const tools = box.querySelectorAll('.cm-status-item[data-tool="1"]').length;
    const details = document.createElement('details');
    details.className = 'cm-status-summary';
    const summary = document.createElement('summary');
    summary.textContent = `🧠 已完成 ${steps} 步推理${tools ? ` · 工具调用 ${tools} 次` : ''}`;
    details.appendChild(summary);
    box.parentElement.insertBefore(details, box);
    details.appendChild(box);
  }

// 导出 + 供 HTML 内联 onclick 使用
export { attachStatusBox, updateStatus, collapseStatus };
Object.assign(window, { attachStatusBox, updateStatus, collapseStatus });
