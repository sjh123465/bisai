/**
 * @file 练一练：AI 出题 / 试卷 / 双轨批改 / 错题重练
 * @module features/exam
 */
import { API } from '../core/env.js';
import { mdSafe, escapeHtml } from '../core/render.js';
import {
  getRetryQuestions,
  recordAnswer as recordLocalAnswer,
  getTodayStats,
  resolveWrong,
} from '../core/localStore.js';

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
    if (!window.requireLLMConfigured?.()) return;
    const q = document.getElementById('exam-question');
    const empty = document.getElementById('exam-empty');
    const result = document.getElementById('exam-result');
    // loading 放到独立容器，避免覆盖 #exam-question 内部结构（否则 renderQuestion 找不到子元素）
    empty.classList.add('hidden');
    q.classList.add('hidden');
    result.classList.remove('hidden');
    result.innerHTML = `<div class="text-center py-8 text-slate-400"><div class="graph-spinner mx-auto"></div><p class="mt-3 text-xs">AI 正在出题...</p></div>`;
    try {
      const resp = await fetch(API + '/exam/generate', {
        method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
          concept: concept,
          qtype: qtype,
          difficulty: difficulty,
          // 只带最近用过的角度标签，成本固定且远低于回传完整题干
          avoid_variants: _recentVariants.slice(-6),
        }),
      });
      const data = await resp.json();
      if (!resp.ok || data.error || !data.question) {
        result.innerHTML = `<div class="msg-err">生成失败：${escapeHtml(data.error || data.detail || 'AI 未返回有效题目，请重试')}</div>`;
        return;
      }
      result.classList.add('hidden');
      result.innerHTML = '';
      const usedAngles = Array.isArray(data.variation) ? data.variation.filter(Boolean) : [];
      if (usedAngles.length) {
        _recentVariants = _recentVariants.concat(usedAngles).slice(-6);
      }
      _retryItem = null;
      currentQuestion = data;
      renderQuestion(data);
    } catch (e) {
      result.innerHTML = `<div class="msg-err">生成失败：${escapeHtml(e.message || String(e))}</div>`;
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
      result.innerHTML = '<div class="msg-err">请先选择知识点</div>';
      return;
    }
    if (!btn) btn = document.getElementById('btn-gen-question');
    const oldText = btn.textContent;
    btn.disabled = true; btn.textContent = '生成中...';
    try { await generateQuestionDirect(); }
    finally { btn.disabled = false; btn.textContent = oldText; }
  }

  let _paperQuestions = null;
  let _paperIndex = 0;
  let _currentAnswered = false;
  // 当前题目如果来自错题重做，记录原错题信息；作业错题需走服务端完整快照判分
  let _retryItem = null;
  // 最近一次答题的完整上下文，供「问 AI 详解 / 改进」使用（含题干、选项、作答、标准答案）
  let _lastAskPrompt = '';
  // 最近用过的切入角度（轻量指纹，非完整题干），随下一次出题请求发给后端做轮换
  let _recentVariants = [];

  async function generatePaper(btn) {
    if (!window.requireLLMConfigured?.()) return;
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
    btn.disabled = true; btn.textContent = '生成中...';
    try {
      const resp = await fetch('/api/exam/paper', {
        method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(body)
      });
      const data = await resp.json();
      if (!resp.ok || data.error || !data.questions || !data.questions.length) {
        result.classList.remove('hidden');
        result.innerHTML = `<div class="msg-err">生成试卷失败：${escapeHtml(data.error || data.detail || '未返回题目')}</div>`;
        return;
      }
      _paperQuestions = data.questions;
      _paperIndex = 0;
      showPaperQuestion();
    } catch (e) {
      result.classList.remove('hidden');
      result.innerHTML = `<div class="msg-err">生成试卷失败：${escapeHtml(e.message || String(e))}</div>`;
    } finally { btn.disabled = false; btn.textContent = oldText; }
  }

  function showPaperQuestion() {
    if (!_paperQuestions || _paperIndex >= _paperQuestions.length) {
      document.getElementById('exam-result').classList.remove('hidden');
      document.getElementById('exam-result').innerHTML = '<div class="result-card text-center"><p class="result-verdict">试卷完成</p><p class="result-body mt-1">可以回看错题，或再来一组练习。</p></div>';
      document.getElementById('paper-progress').classList.add('hidden');
      return;
    }
    _retryItem = null;
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
    listEl.innerHTML = '<p class="text-sm text-slate-400">加载错题中...</p>';
    try {
      const questions = getRetryQuestions(10);
      if (questions.length === 0) {
        listEl.innerHTML = '<div class="empty-state"><p class="empty-title">暂无错题</p><p class="empty-sub">继续保持。</p></div>';
        return;
      }
      // 先挂上引用再修旧数据，避免用户抢在异步请求前点击导致无效
      window._retryQuestions = questions;
      await hydrateLegacyAssignmentRetry(questions);
      listEl.innerHTML = `
        <div class="text-xs text-slate-400 mb-2">共 ${questions.length} 道错题（按知识点去重），点击重做：</div>
        ${questions.map((item, i) => `
          <div class="row-item cursor-pointer" style="align-items:flex-start;flex-direction:column;gap:4px" onclick='pickRetry(${i})'>
            <div class="flex justify-between items-center w-full">
              <span class="text-sm font-medium text-slate-200">${escapeHtml(item.concept_id || '')}</span>
              <span class="text-[10px] text-slate-500">${escapeHtml((item.wrong_time||'').slice(0,16))}</span>
            </div>
            <div class="text-xs text-slate-400 line-clamp-2">${escapeHtml((item.question && item.question.question) || '（无题干）')}</div>
          </div>
        `).join('')}
      `;
    } catch (e) {
      listEl.innerHTML = '<p class="text-rose-400 text-sm">加载失败: ' + escapeHtml(String(e)) + '</p>';
    }
  }

  function pickRetry(idx) {
    const item = window._retryQuestions[idx];
    if (!item || !item.question) return;
    document.getElementById('retry-list').classList.add('hidden');
    currentQuestion = item.question;
    if (!currentQuestion.concept_id) currentQuestion.concept_id = item.concept_id;
    if (!currentQuestion.concept) currentQuestion.concept = item.concept_id;
    _retryItem = item;
    renderQuestion(currentQuestion);
  }

  function renderQuestion(q) {
    _currentAnswered = false;
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
        const raw = String(o);
        // LLM 偶尔不返回 A./B. 前缀；前端统一补上，避免“正确选项看不出来”
        const display = /^\s*[A-Ha-h]\s*[.、:：)]/.test(raw)
          ? raw
          : String.fromCharCode(65 + i) + '. ' + raw;
        const btn = document.createElement('button');
        btn.className = 'option-btn';
        btn.textContent = display;
        btn.onclick = () => checkChoice(btn, q, display);
        opts.appendChild(btn);
      });
    } else if (q.type === 'judge') {
      ['正确', '错误'].forEach((label, i) => {
        const btn = document.createElement('button');
        btn.className = 'option-btn';
        btn.textContent = label;
        btn.onclick = () => checkJudge(btn, q, i === 0);
        opts.appendChild(btn);
      });
    } else if (q.type === 'code') {
      codeArea.classList.remove('hidden');
      if (q.test_cases) {
        const tc = document.createElement('div');
        tc.className = 'footnote mt-2';
        tc.innerHTML = `测试用例（${q.test_cases.length} 组）<br>` +
          q.test_cases.slice(0, 3).map(c => `输入 \`${escapeHtml(String(c.input || '').replace(/\n/g,' '))}\` → 期望 \`${escapeHtml(String(c.expected || ''))}\``).join('<br>');
        opts.appendChild(tc);
      }
    }
  }

  function showHint() {
    if (currentQuestion && currentQuestion.hint) {
      const h = document.getElementById('exam-hint');
      h.innerHTML = mdSafe(currentQuestion.hint);
      h.classList.remove('hidden');
    }
  }

  // 答题后只写入浏览器本地学情；服务端不保存个人练习数据。
  function recordAnswer(conceptId, question, answer, correct, opts = {}) {
    try {
      recordLocalAnswer(
        conceptId, (question && question.concept) || '', question, answer, correct,
        opts.source || 'personal', { skipWrongbook: !!opts.skipWrongbook },
      );
    } catch (e) {
      console.error('记录本地学情失败', e);
    }
    window.refreshTodayStats?.();
    window.refreshProgressCurve?.();
    window.refreshPersonalRadar?.();
    // 右侧「薄弱知识点」与统计立即更新，不用等 30 秒定时器
    window.refreshLocalSideStats?.();
    window.loadSideWeak?.();
  }

  function _disableOptions() {
    const opts = document.getElementById('exam-options');
    if (opts) opts.querySelectorAll('button').forEach(b => { b.disabled = true; b.classList.add('opacity-60'); });
  }

  /** 作业错题重做必须走服务端完整快照判分；个人练习错题仍用本地快照。 */
  function _assignmentRetryFor(item) {
    return item && item.source === 'assignment' && item.assignment_id ? item : null;
  }

  /** 旧版本地数据可能只存了作业的公开快照：没有答案 / 判题方案，且缺少 assignment_id。 */
  function _looksLikePublicAssignmentSnapshot(q) {
    return !!q && !q.grading_plan && !Object.prototype.hasOwnProperty.call(q, 'answer');
  }

  function _needsAssignmentSnapshot(item) {
    return !!item && (item.source === 'assignment' || _looksLikePublicAssignmentSnapshot(item.question));
  }

  /**
   * 兼容旧版错题：按题目 ID 找回对应作业，后续走服务端完整快照判分。
   * 只对缺少 assignment_id 的旧条目发请求；新数据不产生额外开销。
   */
  async function hydrateLegacyAssignmentRetry(items) {
    const legacy = (items || []).filter(it =>
      it.question && it.question.id && !it.assignment_id && _needsAssignmentSnapshot(it)
    );
    if (!legacy.length) return;
    if (localStorage.getItem('cm_role') !== 'student' || !localStorage.getItem('cm_token')) return;
    try {
      const mineResp = await fetch('/api/assignments/mine');
      if (!mineResp.ok) return;
      const mine = await mineResp.json();
      const submitted = (mine.assignments || []).filter(a => a.my_submission);
      const questionToAssignment = {};
      for (const a of submitted) {
        const resp = await fetch('/api/assignments/' + encodeURIComponent(a.id));
        if (!resp.ok) continue;
        const detail = await resp.json();
        (detail.questions || []).forEach(q => {
          if (q.id) questionToAssignment[q.id] = a.id;
        });
      }
      legacy.forEach(it => {
        const aid = questionToAssignment[it.question.id];
        if (aid) {
          it.assignment_id = aid;
          it.source = 'assignment';
        }
      });
    } catch (_) { /* 旧数据修复失败时保持原状，提交时给出明确提示 */ }
  }

  /** 客观题也走服务端“判题方案”判分，保证与班级作业同一套判定逻辑。 */
  async function submitObjective(q, selected, btn) {
    if (_currentAnswered) return;
    const retryItem = _retryItem;
    if (retryItem && _needsAssignmentSnapshot(retryItem) && !retryItem.assignment_id) {
      const r = document.getElementById('exam-result');
      r.classList.remove('hidden');
      r.innerHTML = '<div class="hint-box">这条作业错题来自旧版本地数据，缺少对应作业。请先登录，在「我的作业」中查看一次该作业结果，再回来重做。</div>';
      return;
    }
    _currentAnswered = true;
    if (btn) btn.classList.add('selected');
    _disableOptions();
    const assignmentRetry = _assignmentRetryFor(retryItem);
    try {
      const url = assignmentRetry
        ? `/api/assignments/${encodeURIComponent(assignmentRetry.assignment_id)}/retry`
        : '/api/exam/grade';
      const body = assignmentRetry
        ? { question_id: q.id, answer: String(selected) }
        : { question: q, answer: String(selected) };
      const resp = await fetch(url, {
        method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(body),
      });
      const data = await resp.json();
      if (!resp.ok) throw new Error(data.detail || ('HTTP ' + resp.status));
      const passed = data.correct === true;
      if (passed && retryItem) {
        resolveWrong(retryItem.concept_id, retryItem.wrong_time);
        if (_retryItem === retryItem) _retryItem = null;
      }
      recordAnswer(q.concept_id, q, selected, passed, retryItem
        ? { source: retryItem.source, skipWrongbook: true } : undefined);
      showResult(q, passed ? '通过' : '不通过', q.explanation || data.feedback || '', selected);
      markPaperAnswered();
    } catch (e) {
      _currentAnswered = false;
      const opts = document.getElementById('exam-options');
      if (opts) opts.querySelectorAll('button').forEach(b => { b.disabled = false; b.classList.remove('opacity-60', 'selected'); });
      showResult(q, '不通过', '判题请求失败：' + (e.message || e), selected);
    }
  }

  function checkChoice(btn, q, selected) {
    submitObjective(q, selected, btn);
  }

  function checkJudge(btn, q, val) {
    submitObjective(q, val ? '正确' : '错误', btn);
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
    btn.disabled = true; btn.textContent = '批改中...';
    document.getElementById('exam-result').classList.add('hidden');
    const retryItem = _retryItem;
    if (retryItem && _needsAssignmentSnapshot(retryItem) && !retryItem.assignment_id) {
      const r = document.getElementById('exam-result');
      r.classList.remove('hidden');
      r.innerHTML = '<div class="hint-box">这条作业错题来自旧版本地数据，缺少对应作业。请先登录，在「我的作业」中查看一次该作业结果，再回来重做。</div>';
      btn.disabled = false; btn.textContent = oldText;
      return;
    }
    const assignmentRetry = _assignmentRetryFor(retryItem);
    try {
      const url = assignmentRetry
        ? `/api/assignments/${encodeURIComponent(assignmentRetry.assignment_id)}/retry`
        : '/api/exam/grade';
      const body = assignmentRetry
        ? { question_id: currentQuestion.id, code }
        : { question: currentQuestion, code };
      const resp = await fetch(url, {
        method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(body),
      });
      const data = await resp.json();
      if (!resp.ok || data.detail) {
        renderGradeResult({ review: { correctness: '批改失败', correctness_score: 0, bugs: [String(data.error || data.detail || '服务异常')] } }, code, currentQuestion);
        return;
      }
      renderGradeResult(data, code, currentQuestion);
      // 编程题由服务端按判题方案给出 correct/score，本地只负责更新个人学情
      const correct = data.correct === true;
      if (correct && retryItem) {
        resolveWrong(retryItem.concept_id, retryItem.wrong_time);
        if (_retryItem === retryItem) _retryItem = null;
      }
      recordAnswer(currentQuestion.concept_id, currentQuestion, code, correct, retryItem
        ? { source: retryItem.source, skipWrongbook: true } : undefined);
      markPaperAnswered();
    } catch (e) {
      renderGradeResult({ review: { correctness: '批改失败', correctness_score: 0, bugs: [e.message] } }, code, currentQuestion);
    }
    finally { btn.disabled = false; btn.textContent = oldText; }
  }

  /** 从选项文本提取 A/B/C/D 标号；无标号时按它在 options 中的位置兜底。 */
  function optionLabel(q, optionText) {
    const text = String(optionText ?? '').trim();
    const m = text.match(/^([A-Za-z])[.、．:：)]/);
    if (m) return m[1].toUpperCase();
    const idx = Array.isArray(q.options) ? q.options.findIndex(o => String(o).trim() === text) : -1;
    return idx >= 0 ? String.fromCharCode(65 + idx) : '';
  }

  /** 标准答案的可读形式：选择题显示「B. xxx」，判断题显示「正确 / 错误」。 */
  function formatCorrectAnswer(q) {
    const ans = q && q.answer;
    if (ans === undefined || ans === null || ans === '') return '';
    if (q.type === 'judge') {
      if (typeof ans === 'boolean') return ans ? '正确' : '错误';
      const t = String(ans).trim().toLowerCase();
      if (['true', '正确', '对', 't', '1'].includes(t)) return '正确';
      if (['false', '错误', '错', 'f', '0'].includes(t)) return '错误';
      return String(ans);
    }
    const text = String(ans).trim();
    if (!Array.isArray(q.options) || !q.options.length) return text;
    const direct = q.options.find(o => String(o).trim() === text);
    if (direct) return String(direct);
    const byLetter = text.length === 1
      ? q.options.find(o => optionLabel(q, o) === text.toUpperCase())
      : null;
    return byLetter ? String(byLetter) : text;
  }

  /** 组装客观题提问：题干 + 选项 + 我的作答 + 判定结果 + 标准答案。 */
  function buildObjectiveAskPrompt(q, userAnswer, correct) {
    const typeName = q.type === 'judge' ? '判断题' : '选择题';
    const lines = [`请详细讲解下面这道${typeName}。`, '', '【题目】', String(q.question || '（题干缺失）')];
    if (q.type === 'choice' && Array.isArray(q.options) && q.options.length) {
      lines.push('', '【选项】', ...q.options.map(o => String(o)));
    }
    const chosen = String(userAnswer ?? '').trim() || '（未作答）';
    const hasLabel = /^[A-Za-z][.、．:：)]/.test(chosen);
    const label = q.type === 'choice' && !hasLabel ? optionLabel(q, chosen) : '';
    lines.push('', '【我的作答】' + (label ? `${label}. ${chosen}` : chosen));
    lines.push('【判定结果】' + (correct ? '回答正确' : '回答错误'));
    const correctAnswer = formatCorrectAnswer(q);
    if (correctAnswer) lines.push('【标准答案】' + correctAnswer);

    const structure = ['1. 这道题考查的核心知识点；'];
    if (q.type === 'judge') {
      structure.push(correct
        ? '2. 这个说法为什么正确，判断的关键依据是什么；'
        : '2. 这个说法为什么错误，正确的理解应该是什么；');
      structure.push(correct
        ? '3. 我判断对了，但请指出相关的易错点和容易混淆的概念；'
        : '3. 重点分析我的判断错在哪里、可能混淆了哪个概念；');
    } else {
      structure.push('2. 逐个分析每个选项为什么正确或错误；');
      structure.push(correct
        ? '3. 我虽然选对了，但请指出这道题的易错点和容易混淆的概念；'
        : '3. 重点分析我选的答案错在哪里、可能混淆了哪个概念；');
    }
    structure.push('4. 用一句话给出记忆要点。');
    lines.push('', '请按以下结构回答：', ...structure);
    return lines.join('\n');
  }

  /** 组装编程题提问：题干 + 测试用例 + 完整代码 + 判题结果。 */
  function buildCodeAskPrompt(q, code, data) {
    const lines = ['请批改并详细讲解下面这道编程题。', '', '【题目】', String((q && q.question) || '（题干缺失）')];
    if (q && Array.isArray(q.test_cases) && q.test_cases.length) {
      lines.push('', '【测试用例】');
      q.test_cases.slice(0, 5).forEach((tc, i) => {
        lines.push(`${i + 1}. 输入：${String(tc.input ?? '')} → 期望输出：${String(tc.expected ?? '')}`);
      });
    }
    lines.push('', '【我的代码】', '```python', String(code || '（空）'), '```');
    const sb = (data && data.sandbox_track) || {};
    if (sb.total) lines.push('', `【沙箱结果】通过 ${Number(sb.passed) || 0} / ${Number(sb.total) || 0} 组测试用例`);
    const review = (data && data.review) || {};
    if (review.correctness) lines.push(`【系统判定】${review.correctness}（正确性 ${review.correctness_score ?? '-'} 分）`);
    if (Array.isArray(review.bugs) && review.bugs.length) {
      lines.push('【系统发现的问题】');
      review.bugs.forEach((b, i) => lines.push(`${i + 1}. ${String(b)}`));
    }
    lines.push('', '请先指出代码中的具体问题（位置 + 原因），再给出改进思路；不要直接重写整份代码，先引导我思考。');
    return lines.join('\n');
  }

  /** 把最近一次答题的完整上下文发到对话 Tab。 */
  function askAiDetailed() {
    if (!_lastAskPrompt) return;
    window.sendQuick(_lastAskPrompt);
  }

  function showResult(q, verdict, explanation, userAnswer = '') {
    const r = document.getElementById('exam-result');
    r.classList.remove('hidden');
    const isCorrect = verdict === '通过';
    // 保存完整上下文：题干、选项、我的作答、判定结果与标准答案
    _lastAskPrompt = buildObjectiveAskPrompt(q, userAnswer, isCorrect);
    r.innerHTML = `
      <div class="result-card ${isCorrect ? 'is-correct' : 'is-wrong'}">
        <div class="result-head">
          <span class="result-verdict ${isCorrect ? 'is-correct' : 'is-wrong'}">${isCorrect ? '回答正确' : '回答错误'}</span>
          <span class="tag ${isCorrect ? 'tag-success' : 'tag-danger'}">${isCorrect ? '通过' : '不通过'}</span>
        </div>
        <div class="result-body prose-cm-result"></div>
        <div class="result-actions">
          <button onclick="generateQuestion()" class="btn btn-primary btn-sm">再来一道</button>
          <button onclick="askAiDetailed()" class="btn btn-ghost btn-sm">问 AI 详解</button>
        </div>
      </div>`;
    // 解析由 LLM 生成的解析，必须经 DOMPurify 后再插入 DOM
    const resultBody = r.querySelector('.prose-cm-result');
    if (resultBody) resultBody.innerHTML = mdSafe(explanation || '');
  }

  function renderGradeResult(data, code, question = currentQuestion) {
    const r = document.getElementById('exam-result');
    r.classList.remove('hidden');
    // 编程题同样保留完整上下文，避免只把代码前 120 字符发给 AI
    _lastAskPrompt = buildCodeAskPrompt(question, code, data);
    const review = data.review || {};
    const sb = data.sandbox_track || {};
    const score = review.correctness_score || 0;
    const isPass = score >= 60;
    r.innerHTML = `
      <div class="result-card ${isPass ? 'is-correct' : 'is-wrong'} space-y-3">
        <div class="result-head flex-wrap">
          <span class="result-verdict ${isPass ? 'is-correct' : 'is-wrong'}">${escapeHtml(review.correctness || '判定中')}</span>
          <span class="tag tag-accent">正确性 ${score}/100</span>
          <span class="tag">规范 ${escapeHtml(String(review.style_score ?? '-'))}/100</span>
        </div>
        ${sb.total ? `<div class="result-body">沙箱 · 通过 <b class="text-emerald-300">${Number(sb.passed) || 0}</b> / ${Number(sb.total) || 0} <span class="text-slate-500">· 用时 ${escapeHtml(String(sb.runtime_ms ?? '-'))}ms</span></div>` : ''}
        ${data.ast_text ? `<div class="result-body border-l-2 border-slate-600 pl-2">${mdSafe(data.ast_text)}</div>` : ''}
        ${review.complexity_analysis ? `<div class="result-body"><span class="eyebrow">复杂度</span><div class="mt-1">${escapeHtml(review.complexity_analysis)}</div></div>` : ''}
        ${(review.bugs||[]).length ? `<div class="result-body"><span class="eyebrow">问题</span><ul class="list-disc ml-5 mt-1 space-y-1">${review.bugs.map(b=>`<li>${escapeHtml(String(b))}</li>`).join('')}</ul></div>` : ''}
        ${(review.suggestions||[]).length ? `<div class="result-body"><span class="eyebrow">建议</span><ul class="list-disc ml-5 mt-1 space-y-1">${review.suggestions.map(s=>`<li>${escapeHtml(String(s))}</li>`).join('')}</ul></div>` : ''}
        ${review.encouragement ? `<div class="result-body italic border-t border-slate-700/30 pt-2 text-amber-300">${escapeHtml(review.encouragement)}</div>` : ''}
        <div class="result-actions">
          <button onclick="generateQuestion()" class="btn btn-primary btn-sm">再来一道</button>
          <button onclick="askAiDetailed()" class="btn btn-ghost btn-sm">问 AI 改进</button>
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
      box.className = 'mt-2 text-xs hint-box';
      box.classList.remove('hidden');
      box.textContent = '先写点代码再检查。';
      return;
    }
    box.className = 'mt-2 text-xs hint-box';
    box.classList.remove('hidden');
    box.textContent = '正在检查代码风格...';
    try {
      const resp = await fetch(API + '/code/style', {
        method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ code })
      });
      const d = await resp.json();
      if (d.clean) {
        box.className = 'mt-2 text-xs msg-ok';
        box.textContent = d.summary || '通过 PEP8 检查';
        return;
      }
      const issues = (d.issues || []).slice(0, 6);
      box.className = 'mt-2 text-xs hint-box';
      box.innerHTML = `<div class="font-medium mb-1">${escapeHtml(d.summary || '发现风格问题')}</div>` +
        issues.map(i => `<div class="font-mono text-[11px]">第 ${Number(i.line) || 0} 行 · ${escapeHtml(String(i.message || ''))}</div>`).join('');
    } catch (e) {
      box.className = 'mt-2 text-xs msg-err';
      box.textContent = '检查失败：' + (e.message || String(e));
    }
  }

  /** 今日练习数据来自浏览器本地学情 */
  function refreshTodayStats() {
    try {
      const d = getTodayStats();
      const answeredEl = document.getElementById('today-answered');
      if (!answeredEl) return;
      answeredEl.textContent = d.answered ?? 0;
      document.getElementById('today-accuracy').textContent =
        d.accuracy === null || d.accuracy === undefined ? '—' : Math.round(d.accuracy * 100) + '%';
      document.getElementById('today-streak').textContent = d.streak ?? 0;
      const empty = document.getElementById('today-empty');
      if (empty) empty.classList.toggle('hidden', (d.answered || 0) > 0);
    } catch (e) {
      console.error('本地今日统计读取失败', e);
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
export { loadExamConcepts, generateQuestion, quickExam, generatePaper, gradeQuestion, checkChoice, checkJudge, pickRetry, showHint, nextPaperQuestion, startBeginner, checkPep8, refreshTodayStats, askAiDetailed };
Object.assign(window, { loadExamConcepts, generateQuestion, quickExam, generatePaper, gradeQuestion, checkChoice, checkJudge, pickRetry, showHint, nextPaperQuestion, loadRetryQuestions, startBeginner, checkPep8, refreshTodayStats, askAiDetailed });
