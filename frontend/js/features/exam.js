/**
 * @file 练一练：AI 出题 / 试卷 / 双轨批改 / 错题重练
 * @module features/exam
 */
import { API, currentStudentId } from '../core/env.js';
import { jsStr, mdSafe } from '../core/render.js';

      // 用 /api/teacher/dashboard 获取薄弱点和学生数（需要登录，失败就跳过）
  // 每 30 秒自动刷新

  // ---------- 练一练快速启动（空状态引导按钮） ----------
  /** 新手入门路径：预设知识点 + 难度后直接出题 */
  async function startBeginner(conceptName, difficulty) {
    const diffSel = document.getElementById('exam-difficulty');
    if (diffSel && difficulty) diffSel.value = difficulty;
    await quickExam(conceptName, '任意题型');
  }

  async function quickExam(conceptName, typeName) {
    const sel = document.getElementById('exam-concept');
    const typeSel = document.getElementById('exam-type');
    // 尝试匹配下拉选项
    const match = Array.from(sel.options).find(o =>
      o.textContent.trim() === conceptName || o.value.includes(conceptName)
    );
    if (match) {
      sel.value = match.value;
    } else {
      // 没找到也硬塞一个
      const opt = document.createElement('option');
      opt.value = conceptName; opt.textContent = conceptName;
      sel.appendChild(opt); sel.value = conceptName;
    }
    // 匹配题型
    const typeMatch = Array.from(typeSel.options).find(o =>
      o.textContent.includes(typeName.slice(0, 3)) || o.value.includes(typeName.slice(0, 2))
    );
    if (typeMatch) typeSel.value = typeMatch.value;
    window.switchTab('practice');
    await generateQuestionDirect();
  }

  // 直接调生成接口（不依赖按钮 event 对象）
  async function generateQuestionDirect() {
    const concept = document.getElementById('exam-concept').value;
    const qtype = document.getElementById('exam-type').value;
    const diffEl = document.getElementById('exam-difficulty');
    const difficulty = diffEl ? diffEl.value : 'medium';
    if (!concept) return;
    const q = document.getElementById('exam-question');
    const empty = document.getElementById('exam-empty');
    const result = document.getElementById('exam-result');
    // loading 放到独立容器，避免覆盖 #exam-question 内部结构（否则 renderQuestion 找不到子元素）
    empty.classList.add('hidden');
    q.classList.add('hidden');
    result.classList.remove('hidden');
    result.innerHTML = `<div class="text-center py-6 text-slate-400"><div class="inline-block w-8 h-8 border-2 border-indigo-500/30 border-t-indigo-500 rounded-full animate-spin"></div><p class="mt-2 text-sm">🎲 AI 正在出题...</p></div>`;
    try {
      const resp = await fetch(API + '/exam/generate', {
        method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ concept: concept, qtype: qtype, difficulty: difficulty }),
      });
      const data = await resp.json();
      if (!resp.ok || data.error || !data.question) {
        result.innerHTML = `<div class="text-rose-400 text-sm">❌ 生成失败：${data.error || data.detail || 'AI 未返回有效题目，请重试'}</div>`;
        return;
      }
      result.classList.add('hidden');
      result.innerHTML = '';
      currentQuestion = data;
      renderQuestion(data);
    } catch (e) {
      result.innerHTML = `<div class="text-rose-400 text-sm">❌ 生成失败：${e.message}</div>`;
    }
  }

  // ==================== 练一练：出题 + 批改 ====================
  let currentQuestion = null;

  async function loadExamConcepts() {
    const sel = document.getElementById('exam-concept');
    if (sel.options.length > 1) return;
    try {
      const g = await fetch('/api/knowledge/graph').then(r => r.json());
      const catLabel = {algorithm:'算法', structure:'数据结构', operation:'操作', paradigm:'编程范式', concept:'核心概念'};
      const groups = {};
      (g.nodes || []).filter(n => n.category !== 'chapter').forEach(n => {
        const c = n.category || 'concept';
        if (!groups[c]) groups[c] = [];
        groups[c].push(n);
      });
      Object.keys(groups).sort().forEach(cat => {
        const og = document.createElement('optgroup');
        og.label = catLabel[cat] || cat;
        groups[cat].sort((a, b) => a.name.localeCompare(b.name, 'zh')).forEach(n => {
          const o = document.createElement('option');
          o.value = n.id;
          o.textContent = n.name;
          og.appendChild(o);
        });
        sel.appendChild(og);
      });
    } catch (e) { console.error(e); }
  }

  /**
   * 按当前知识点生成一道题目（选择题 / 判断题 / 编程题）。
   * @param {HTMLButtonElement} [btn] - 触发按钮，用于 loading 态
   * @returns {Promise<void>}
   */
  async function generateQuestion(btn) {
    const concept = document.getElementById('exam-concept').value;
    if (!concept) {
      const result = document.getElementById('exam-result');
      document.getElementById('exam-empty').classList.add('hidden');
      document.getElementById('exam-question').classList.add('hidden');
      result.classList.remove('hidden');
      result.innerHTML = '<div class="text-amber-300 text-sm">⚠️ 请先选择知识点</div>';
      return;
    }
    if (!btn) btn = document.getElementById('btn-gen-question');
    const oldText = btn.textContent;
    btn.disabled = true; btn.textContent = '🎲 生成中...';
    try { await generateQuestionDirect(); }
    finally { btn.disabled = false; btn.textContent = oldText; }
  }

  let _paperQuestions = null;
  let _paperIndex = 0;

  async function generatePaper(btn) {
    const empty = document.getElementById('exam-empty');
    const q = document.getElementById('exam-question');
    const result = document.getElementById('exam-result');
    const retry = document.getElementById('retry-list');
    empty.classList.add('hidden');
    q.classList.add('hidden');
    result.classList.add('hidden');
    retry.classList.add('hidden');

    // 选知识点和题数
    const concept = document.getElementById('exam-concept').value;
    const count = 5;
    const body = { count };
    if (concept) body.concepts = Array(count).fill(concept);

    if (!btn) btn = document.getElementById('btn-gen-paper');
    const oldText = btn.textContent;
    btn.disabled = true; btn.textContent = '📄 生成中...';
    try {
      const resp = await fetch('/api/exam/paper', {
        method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(body)
      });
      const data = await resp.json();
      if (!resp.ok || data.error || !data.questions || !data.questions.length) {
        result.classList.remove('hidden');
        result.innerHTML = `<div class="text-rose-400 text-sm">❌ 生成试卷失败：${data.error || data.detail || '未返回题目'}</div>`;
        return;
      }
      _paperQuestions = data.questions;
      _paperIndex = 0;
      showPaperQuestion();
    } catch (e) {
      result.classList.remove('hidden');
      result.innerHTML = `<div class="text-rose-400 text-sm">❌ 生成试卷失败：${e.message}</div>`;
    } finally { btn.disabled = false; btn.textContent = oldText; }
  }

  function showPaperQuestion() {
    if (!_paperQuestions || _paperIndex >= _paperQuestions.length) {
      document.getElementById('exam-result').classList.remove('hidden');
      document.getElementById('exam-result').innerHTML = '<div class="text-center py-8"><div class="text-4xl mb-2">🎉</div><p class="text-slate-300">试卷完成！</p></div>';
      document.getElementById('paper-progress').classList.add('hidden');
      return;
    }
    currentQuestion = _paperQuestions[_paperIndex];
    document.getElementById('paper-progress').classList.remove('hidden');
    document.getElementById('paper-progress-text').textContent = `第 ${_paperIndex + 1} / ${_paperQuestions.length} 题`;
    document.getElementById('paper-next-btn').classList.add('hidden');
    document.getElementById('exam-result').classList.add('hidden');
    renderQuestion(currentQuestion);
  }

  function nextPaperQuestion() {
    _paperIndex++;
    showPaperQuestion();
  }

  function markPaperAnswered() {
    // 试卷模式下，答完一题显示"下一题"按钮
    if (_paperQuestions && _paperIndex < _paperQuestions.length) {
      document.getElementById('paper-next-btn').classList.remove('hidden');
    }
  }

  async function loadRetryQuestions() {
    const listEl = document.getElementById('retry-list');
    const empty = document.getElementById('exam-empty');
    const q = document.getElementById('exam-question');
    const result = document.getElementById('exam-result');
    empty.classList.add('hidden');
    q.classList.add('hidden');
    result.classList.add('hidden');
    listEl.classList.remove('hidden');
    listEl.innerHTML = '<p class="text-sm text-slate-400">⏳ 加载错题中...</p>';
    try {
      const data = await fetch('/api/wrongbook/retry/' + encodeURIComponent(currentStudentId()) + '?limit=10').then(r => r.json());
      const questions = data.questions || [];
      if (questions.length === 0) {
        listEl.innerHTML = '<div class="text-center py-8 text-slate-500"><div class="text-4xl mb-2">🎉</div><p>暂无错题，继续保持！</p></div>';
        return;
      }
      listEl.innerHTML = `
        <div class="text-sm text-slate-400 mb-2">共 ${questions.length} 道错题（按知识点去重），点击重做：</div>
        ${questions.map((item, i) => `
          <div class="bg-slate-900/50 rounded-lg p-3 border border-slate-700/50 hover:border-rose-500/50 cursor-pointer transition" onclick='pickRetry(${i})'>
            <div class="flex justify-between items-center mb-1">
              <span class="text-sm font-medium text-slate-200">${item.concept_id}</span>
              <span class="text-xs text-slate-500">${(item.wrong_time||'').slice(0,16)}</span>
            </div>
            <div class="text-xs text-slate-400 line-clamp-2">${(item.question && item.question.question) || '（无题干）'}</div>
          </div>
        `).join('')}
      `;
      window._retryQuestions = questions;
    } catch (e) {
      listEl.innerHTML = '<p class="text-rose-400 text-sm">加载失败: ' + e + '</p>';
    }
  }

  function pickRetry(idx) {
    const item = window._retryQuestions[idx];
    if (!item || !item.question) return;
    document.getElementById('retry-list').classList.add('hidden');
    currentQuestion = item.question;
    if (!currentQuestion.concept_id) currentQuestion.concept_id = item.concept_id;
    if (!currentQuestion.concept) currentQuestion.concept = item.concept_id;
    renderQuestion(currentQuestion);
  }

  function renderQuestion(q) {
    document.getElementById('exam-question').classList.remove('hidden');
    document.getElementById('exam-empty').classList.add('hidden');
    const typeMap = {choice:'选择题', judge:'判断题', code:'编程题'};
    document.getElementById('exam-type-badge').textContent = typeMap[q.type] || q.type;
    document.getElementById('exam-concept-badge').textContent = q.concept;
    document.getElementById('exam-question-text').innerHTML = mdSafe(q.question || '（题目内容为空）');
    document.getElementById('exam-hint').classList.add('hidden');

    const opts = document.getElementById('exam-options');
    opts.innerHTML = '';
    const codeArea = document.getElementById('exam-code-area');
    codeArea.classList.add('hidden');
    document.getElementById('exam-student-code').value = '';

    if (q.type === 'choice' && q.options) {
      q.options.forEach((o, i) => {
        const btn = document.createElement('button');
        btn.className = 'w-full text-left px-3 py-2 rounded-lg bg-slate-800 hover:bg-slate-700 border border-slate-600 text-sm';
        btn.textContent = o;
        btn.onclick = () => checkChoice(btn, q, o);
        opts.appendChild(btn);
      });
    } else if (q.type === 'judge') {
      ['✅ 正确', '❌ 错误'].forEach((label, i) => {
        const btn = document.createElement('button');
        btn.className = 'px-4 py-2 rounded-lg bg-slate-800 hover:bg-slate-700 border border-slate-600 text-sm';
        btn.textContent = label;
        btn.onclick = () => checkJudge(btn, q, i === 0);
        opts.appendChild(btn);
      });
    } else if (q.type === 'code') {
      codeArea.classList.remove('hidden');
      if (q.test_cases) {
        const tc = document.createElement('div');
        tc.className = 'text-xs text-slate-400 mt-2';
        tc.innerHTML = `📦 测试用例（${q.test_cases.length} 组）：<br>` +
          q.test_cases.slice(0, 3).map(c => `输入: \`${c.input.replace(/\n/g,' ')}\` → 期望: \`${c.expected}\``).join('<br>');
        opts.appendChild(tc);
      }
    }
  }

  function showHint() {
    if (currentQuestion && currentQuestion.hint) {
      const h = document.getElementById('exam-hint');
      h.innerHTML = '💡 ' + currentQuestion.hint;
      h.classList.remove('hidden');
    }
  }

  // 答题后自动记录到错题本 + 联动 BKT
  async function recordAnswer(conceptId, question, answer, correct) {
    try {
      await fetch('/api/wrongbook/record', {
        method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
          student_id: currentStudentId(),
          concept_id: conceptId,
          question: question,
          student_answer: String(answer).slice(0, 200),
          correct: correct,
        })
      });
    } catch (e) { console.error('记录答题失败', e); }
  }

  function checkChoice(btn, q, selected) {
    const correct = selected.startsWith(q.answer);
    btn.className = correct ? 'w-full text-left px-3 py-2 rounded-lg bg-emerald-700/50 border border-emerald-500 text-sm'
                              : 'w-full text-left px-3 py-2 rounded-lg bg-rose-700/50 border border-rose-500 text-sm';
    recordAnswer(q.concept_id, q, selected, correct);
    showResult(q, correct ? '通过' : '不通过', q.explanation);
    markPaperAnswered();
  }

  function checkJudge(btn, q, val) {
    const correct = (val === q.answer);
    recordAnswer(q.concept_id, q, val ? '正确' : '错误', correct);
    showResult(q, correct ? '通过' : '不通过', q.explanation);
    markPaperAnswered();
  }

  /**
   * 双轨批改：沙箱跑测试用例（客观轨）+ LLM 代码评审（主观轨），并联动 BKT / 错题本。
   * @param {HTMLButtonElement} [btn] - 提交按钮
   * @returns {Promise<void>}
   */
  async function gradeQuestion(btn) {
    const code = document.getElementById('exam-student-code').value.trim();
    if (!code) { alert('请先写代码'); return; }
    if (!currentQuestion) return;
    if (!btn) btn = document.getElementById('btn-grade-question');
    const oldText = btn.textContent;
    btn.disabled = true; btn.textContent = '⏳ 批改中...';
    document.getElementById('exam-result').classList.add('hidden');
    try {
      const resp = await fetch('/api/exam/grade', {
        method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({code, test_cases: currentQuestion.test_cases || [], concept_id: currentQuestion.concept_id})
      });
      const data = await resp.json();
      if (!resp.ok || data.detail) {
        renderGradeResult({ review: { correctness: '批改失败', correctness_score: 0, bugs: [String(data.error || data.detail || '服务异常')] } }, code);
        return;
      }
      renderGradeResult(data, code);
      // 编程题根据沙箱通过率 + 评分判定对错，联动 BKT
      const sb = data.sandbox_track || {};
      const score = (data.review || {}).correctness_score || 0;
      const allPass = sb.total > 0 && sb.passed === sb.total;
      const correct = allPass || score >= 80;
      recordAnswer(currentQuestion.concept_id, currentQuestion, code, correct);
      markPaperAnswered();
      window.refreshTodayStats?.();
      window.refreshProgressCurve?.();
    } catch (e) {
      renderGradeResult({ review: { correctness: '批改失败', correctness_score: 0, bugs: [e.message] } }, code);
    }
    finally { btn.disabled = false; btn.textContent = oldText; }
  }

  function showResult(q, verdict, explanation) {
    const r = document.getElementById('exam-result');
    r.classList.remove('hidden');
    const isCorrect = verdict === '通过';
    const mainColor = isCorrect ? 'emerald' : 'rose';
    r.innerHTML = `
      <div class="relative rounded-xl p-4 border overflow-hidden"
           style="background:linear-gradient(135deg, rgba(${isCorrect?'16,185,129':'244,63,94'},0.15), rgba(${isCorrect?'16,185,129':'244,63,94'},0.05));
                  border-color:rgba(${isCorrect?'16,185,129':'244,63,94'},0.35);
                  box-shadow: 0 0 0 1px rgba(${isCorrect?'16,185,129':'244,63,94'},0.15), 0 8px 24px rgba(${isCorrect?'16,185,129':'244,63,94'},0.15)">
        <div class="flex items-center gap-2 mb-2">
          <span class="text-2xl">${isCorrect?'🎉':'😅'}</span>
          <div class="font-semibold text-lg ${isCorrect?'text-emerald-300':'text-rose-300'}">
            ${isCorrect?'回答正确！':'回答错误'}
          </div>
        </div>
        <div class="text-sm text-slate-200 leading-relaxed prose-cm-result">${explanation || ''}</div>
        <div class="mt-3 flex gap-2">
          <button onclick="generateQuestion()" class="px-3 py-1.5 rounded-lg bg-${mainColor}-600 hover:bg-${mainColor}-500 text-white text-xs font-medium shadow transition">🔁 再来一道</button>
          <button onclick="switchTab('chat'); sendQuick(${jsStr(q.question || '')})" class="px-3 py-1.5 rounded-lg bg-slate-700/60 hover:bg-slate-600 text-slate-300 text-xs transition">💬 问 AI 详解</button>
        </div>
      </div>`;
    // 解析加粗（**xxx** → <b>xxx</b>）
    r.querySelectorAll('.prose-cm-result').forEach(el => {
      el.innerHTML = mdSafe(el.textContent);
    });
  }

  function renderGradeResult(data, code) {
    const r = document.getElementById('exam-result');
    r.classList.remove('hidden');
    const review = data.review || {};
    const sb = data.sandbox_track || {};
    const ast = data.ast_track || {};
    const score = review.correctness_score || 0;
    const isPass = score >= 60;
    const rgb = isPass ? '16,185,129' : '244,63,94';
    const toneCls = isPass ? 'emerald' : 'rose';
    r.innerHTML = `
      <div class="rounded-xl p-4 border space-y-3"
           style="background:linear-gradient(135deg, rgba(${rgb},0.12), rgba(${rgb},0.04));
                  border-color:rgba(${rgb},0.3);">
        <div class="flex items-center gap-3 pb-2 border-b border-slate-700/50">
          <span class="text-2xl">${isPass?'🎉':'💪'}</span>
          <div class="text-lg font-bold text-${toneCls}-300">${review.correctness || '判定中'}</div>
          <span class="text-[10px] px-2 py-0.5 rounded-full bg-indigo-500/20 border border-indigo-500/40 text-indigo-300 font-medium">正确性 ${score}/100</span>
          <span class="text-[10px] px-2 py-0.5 rounded-full bg-amber-500/20 border border-amber-500/40 text-amber-300 font-medium">规范 ${review.style_score ?? '-'}/100</span>
        </div>
        ${sb.total ? `<div class="text-sm text-slate-300"><span class="text-xs text-slate-500">🧪 沙箱</span>　通过 <b class="text-emerald-400">${sb.passed}</b> / ${sb.total}　<span class="text-slate-500 text-xs">· 用时 ${sb.runtime_ms ?? '-'}ms</span></div>` : ''}
        ${data.ast_text ? `<div class="text-sm text-slate-400 border-l-2 border-slate-600 pl-2">${data.ast_text}</div>` : ''}
        ${review.complexity_analysis ? `<div class="text-sm"><span class="text-xs text-purple-400 font-semibold">📐 复杂度</span> ${review.complexity_analysis}</div>` : ''}
        ${(review.bugs||[]).length ? `<div class="text-sm"><span class="text-xs text-rose-400 font-semibold">🐛 问题</span><ul class="list-disc ml-5 mt-1 space-y-1.5">${review.bugs.map(b=>`<li class="text-slate-300">${b}</li>`).join('')}</ul></div>` : ''}
        ${(review.suggestions||[]).length ? `<div class="text-sm"><span class="text-xs text-emerald-400 font-semibold">💡 建议</span><ul class="list-disc ml-5 mt-1 space-y-1.5">${review.suggestions.map(s=>`<li class="text-slate-300">${s}</li>`).join('')}</ul></div>` : ''}
        ${review.encouragement ? `<div class="text-sm text-amber-200 italic pt-1 border-t border-slate-700/30">${review.encouragement}</div>` : ''}
        <div class="flex gap-2 pt-2 border-t border-slate-700/30">
          <button onclick="generateQuestion()" class="px-3 py-1.5 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-medium shadow transition">🔁 再来一道</button>
          <button onclick="switchTab('chat'); sendQuick(${jsStr('帮我批改代码: ' + code.slice(0,120))})" class="px-3 py-1.5 rounded-lg bg-slate-700/60 hover:bg-slate-600 text-slate-300 text-xs transition">💬 问 AI 改进</button>
        </div>
      </div>`;
  }

  /**
   * PEP8 风格检查（后端 pycodestyle），结果渲染在代码编辑器下方。
   * @returns {Promise<void>}
   */
  async function checkPep8() {
    const code = document.getElementById('exam-student-code').value;
    const box = document.getElementById('pep8-result');
    if (!code.trim()) {
      box.className = 'mt-2 text-xs rounded-lg p-2 border border-amber-500/30 bg-amber-500/10 text-amber-300';
      box.classList.remove('hidden');
      box.textContent = '先写点代码再检查～';
      return;
    }
    box.className = 'mt-2 text-xs rounded-lg p-2 border border-slate-600/50 bg-slate-900/60 text-slate-300';
    box.classList.remove('hidden');
    box.textContent = '⏳ 正在检查代码风格...';
    try {
      const resp = await fetch(API + '/code/style', {
        method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ code })
      });
      const d = await resp.json();
      if (d.clean) {
        box.className = 'mt-2 text-xs rounded-lg p-2 border border-emerald-500/30 bg-emerald-500/10 text-emerald-300';
        box.textContent = d.summary || '✅ 通过 PEP8 检查';
        return;
      }
      const issues = (d.issues || []).slice(0, 6);
      box.className = 'mt-2 text-xs rounded-lg p-2 border border-amber-500/30 bg-amber-500/10 text-amber-200';
      box.innerHTML = `<div class="font-medium mb-1">${d.summary || '发现风格问题'}</div>` +
        issues.map(i => `<div class="font-mono text-[11px] text-amber-200/80">第 ${i.line} 行 · ${i.message}</div>`).join('');
    } catch (e) {
      box.className = 'mt-2 text-xs rounded-lg p-2 border border-rose-500/30 bg-rose-500/10 text-rose-300';
      box.textContent = '检查失败：' + e.message;
    }
  }

  /** 拉取今日练习数据（答题数 / 正确率 / 连续答对），供右侧栏展示 */
  async function refreshTodayStats() {
    const sid = currentStudentId();
    try {
      const d = await fetch(API + '/bkt/today/' + encodeURIComponent(sid)).then(r => r.json());
      const answeredEl = document.getElementById('today-answered');
      if (!answeredEl) return;
      answeredEl.textContent = d.answered ?? 0;
      document.getElementById('today-accuracy').textContent =
        d.accuracy === null || d.accuracy === undefined ? '—' : Math.round(d.accuracy * 100) + '%';
      document.getElementById('today-streak').textContent = d.streak ?? 0;
      const empty = document.getElementById('today-empty');
      if (empty) empty.classList.toggle('hidden', (d.answered || 0) > 0);
    } catch (e) {
      // 后端未启动时保持默认占位
    }
  }

  /** 编辑器快捷键：Ctrl/Cmd+Enter 提交，Tab 插入两空格 */
  function bindEditorShortcuts() {
    const ta = document.getElementById('exam-student-code');
    if (!ta || ta.dataset.bound) return;
    ta.dataset.bound = '1';
    ta.addEventListener('keydown', e => {
      if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
        e.preventDefault();
        gradeQuestion();
      } else if (e.key === 'Tab') {
        e.preventDefault();
        const s = ta.selectionStart, t = ta.selectionEnd;
        ta.value = ta.value.slice(0, s) + '  ' + ta.value.slice(t);
        ta.selectionStart = ta.selectionEnd = s + 2;
      }
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', bindEditorShortcuts);
  } else {
    bindEditorShortcuts();
  }

// 导出 + 供 HTML 内联 onclick 使用
export { loadExamConcepts, generateQuestion, quickExam, generatePaper, gradeQuestion, checkChoice, checkJudge, pickRetry, showHint, nextPaperQuestion, startBeginner, checkPep8, refreshTodayStats };
Object.assign(window, { loadExamConcepts, generateQuestion, quickExam, generatePaper, gradeQuestion, checkChoice, checkJudge, pickRetry, showHint, nextPaperQuestion, loadRetryQuestions, startBeginner, checkPep8, refreshTodayStats });
