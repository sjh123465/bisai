/**
 * @file 班级 / 统一作业界面
 * @module features/classroom
 *
 * 教师：多班级切换、创建班级、布置统一作业、查看提交统计；
 * 学生：查看待完成作业、作答、提交一次、查看结果并合并到本地学情。
 * 所有个人日常练习数据仍在 localStore，班级接口只处理作业。
 */
import { escapeHtml, jsStr, mdSafe } from '../core/render.js';
import { mergeAssignmentResults } from '../core/localStore.js';

let _teacherClasses = [];
let _teacherClassId = null;
let _currentAssignment = null;

function _role() {
  return localStorage.getItem('cm_role') || '';
}

function _loggedIn() {
  return !!localStorage.getItem('cm_token');
}

function _isTeacher() {
  return _role() === 'teacher';
}

function _msg(id, text, ok = false) {
  const el = document.getElementById(id);
  if (!el) return;
  el.textContent = text;
  el.className = ok ? 'msg-ok mt-2' : 'msg-err mt-2';
  el.classList.remove('hidden');
}

function _clearMsg(id) {
  const el = document.getElementById(id);
  if (el) el.classList.add('hidden');
}

/* ==================== 角色显隐 ==================== */

function updateRoleUI() {
  const teacher = _isTeacher();
  const student = _role() === 'student';
  document.querySelectorAll('.teacher-only').forEach(el => {
    el.classList.toggle('hidden', !teacher);
  });
  const studentBox = document.getElementById('student-assignments-box');
  if (studentBox) studentBox.classList.toggle('hidden', teacher);
  const profileBtn = document.getElementById('student-profile-btn');
  if (profileBtn) profileBtn.classList.toggle('hidden', teacher);
  // 教师不能打开学生作答入口
  if (teacher) closeTakeAssignment();
  const classSel = document.getElementById('teacher-class-select');
  if (classSel && !teacher) classSel.innerHTML = '<option>请使用教师账号</option>';
  if (student && !document.getElementById('panel-practice')?.classList.contains('hidden')) {
    loadStudentAssignments();
  }
}

/* ==================== 教师：班级 ==================== */

function _teacherClass() {
  return _teacherClasses.find(c => c.id === _teacherClassId) || null;
}

function _renderClassSelect() {
  const sel = document.getElementById('teacher-class-select');
  if (!sel) return;
  if (!_teacherClasses.length) {
    sel.innerHTML = '<option value="">暂无班级</option>';
  } else {
    sel.innerHTML = _teacherClasses.map(c =>
      `<option value="${escapeHtml(c.id)}">${escapeHtml(c.name)}（${Number(c.member_count) || 0} 人）</option>`
    ).join('');
    sel.value = _teacherClassId || _teacherClasses[0].id;
  }
  const cls = _teacherClass();
  const codeEl = document.getElementById('teacher-join-code');
  if (codeEl) codeEl.textContent = cls ? `邀请码 ${cls.join_code}` : '';
}

async function loadTeacherClasses() {
  if (!_isTeacher()) return;
  const sel = document.getElementById('teacher-class-select');
  try {
    const resp = await fetch('/api/classes');
    if (!resp.ok) throw new Error('HTTP ' + resp.status);
    const data = await resp.json();
    _teacherClasses = data.classes || [];
    if (!_teacherClasses.length) {
      _teacherClassId = null;
      _renderClassSelect();
      window.renderTeacherDashboard?.(null);
      return;
    }
    if (!_teacherClassId || !_teacherClasses.some(c => c.id === _teacherClassId)) {
      _teacherClassId = _teacherClasses[0].id;
    }
    _renderClassSelect();
    await refreshTeacherClassData();
  } catch (e) {
    if (sel) sel.innerHTML = '<option>班级加载失败</option>';
    console.error(e);
  }
}

function onTeacherClassChange() {
  const sel = document.getElementById('teacher-class-select');
  _teacherClassId = sel ? sel.value : null;
  _renderClassSelect();
  if (_teacherClassId) refreshTeacherClassData();
}

async function refreshTeacherClassData() {
  if (!_isTeacher() || !_teacherClassId) return;
  try {
    const resp = await fetch(`/api/teacher/classes/${encodeURIComponent(_teacherClassId)}/dashboard`);
    if (!resp.ok) throw new Error('HTTP ' + resp.status);
    const data = await resp.json();
    window.__teacherClassId = _teacherClassId;
    window.__teacherDashboard = data;
    window.renderTeacherDashboard?.(data);
    await loadTeacherAssignments();
  } catch (e) {
    console.error('班级看板加载失败', e);
  }
}

function openCreateClass() {
  const modal = document.getElementById('class-create-modal');
  if (!modal) return;
  const input = document.getElementById('class-name-input');
  if (input) {
    input.value = '';
    input.onkeydown = (e) => {
      if (e.key === 'Enter') {
        e.preventDefault();
        createClassUI();
      }
    };
  }
  _clearMsg('class-create-msg');
  modal.classList.remove('hidden');
  setTimeout(() => input && input.focus(), 100);
}

function closeCreateClass() {
  document.getElementById('class-create-modal')?.classList.add('hidden');
}

async function createClassUI() {
  if (!_loggedIn() || !_isTeacher()) {
    _msg('class-create-msg', '请先使用教师账号登录，再创建班级。');
    return;
  }
  const name = document.getElementById('class-name-input')?.value.trim() || '';
  if (!name) { _msg('class-create-msg', '请输入班级名称'); return; }
  const btn = document.getElementById('class-create-btn');
  const old = btn ? btn.textContent : '';
  if (btn) { btn.disabled = true; btn.textContent = '创建中...'; }
  try {
    const resp = await fetch('/api/classes', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name }),
    });
    const data = await resp.json().catch(() => ({}));
    if (resp.status === 401) {
      closeCreateClass();
      window.openLogin?.();
      return;
    }
    if (resp.status === 403) {
      throw new Error('当前账号不是教师，请使用教师账号登录');
    }
    if (!resp.ok) throw new Error(data.detail || ('HTTP ' + resp.status));
    _teacherClassId = data.id;
    closeCreateClass();
    await loadTeacherClasses();
  } catch (e) {
    _msg('class-create-msg', '创建失败：' + (e.message || e));
  } finally {
    if (btn) { btn.disabled = false; btn.textContent = old; }
  }
}

/* ==================== 教师：作业 ==================== */

function openCreateAssignment() {
  if (!_isTeacher()) return;
  if (!_teacherClasses.length) {
    alert('请先创建一个班级');
    openCreateClass();
    return;
  }
  if (window.requireLLMConfigured && !window.requireLLMConfigured()) return;
  const modal = document.getElementById('assignment-create-modal');
  if (!modal) return;
  _clearMsg('assignment-create-msg');
  const title = document.getElementById('assign-title');
  if (title) title.value = '';
  const due = document.getElementById('assign-due');
  if (due) due.value = '';
  const count = document.getElementById('assign-count');
  if (count) count.value = '5';
  const diff = document.getElementById('assign-difficulty');
  if (diff) diff.value = 'medium';
  const boxes = document.getElementById('assign-classes');
  if (boxes) {
    boxes.innerHTML = _teacherClasses.map(c => `
      <label class="row-item cursor-pointer" style="font-size:12px">
        <input type="checkbox" value="${escapeHtml(c.id)}" ${c.id === _teacherClassId ? 'checked' : ''}>
        <span class="text-slate-200">${escapeHtml(c.name)}</span>
        <span class="text-slate-500 ml-auto">${Number(c.member_count) || 0} 人</span>
      </label>
    `).join('');
  }
  modal.classList.remove('hidden');
}

function closeCreateAssignment() {
  document.getElementById('assignment-create-modal')?.classList.add('hidden');
}

async function createAssignmentUI() {
  const title = document.getElementById('assign-title')?.value.trim() || '';
  const classIds = Array.from(document.querySelectorAll('#assign-classes input[type=checkbox]:checked')).map(el => el.value);
  const count = Number(document.getElementById('assign-count')?.value || 5);
  const difficulty = document.getElementById('assign-difficulty')?.value || 'medium';
  const dueRaw = document.getElementById('assign-due')?.value || '';
  if (!title) { _msg('assignment-create-msg', '请输入作业标题'); return; }
  if (!classIds.length) { _msg('assignment-create-msg', '请至少选择一个班级'); return; }
  if (!window.requireLLMConfigured?.()) return;

  let dueAt = null;
  if (dueRaw) {
    const d = new Date(dueRaw);
    if (!Number.isNaN(d.getTime())) dueAt = d.toISOString();
  }

  const btn = document.getElementById('assign-create-btn');
  const old = btn ? btn.textContent : '';
  if (btn) { btn.disabled = true; btn.textContent = 'AI 出题中...'; }
  _clearMsg('assignment-create-msg');
  try {
    const resp = await fetch('/api/teacher/assignments', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        title,
        class_ids: classIds,
        count,
        difficulty,
        due_at: dueAt,
      }),
    });
    const data = await resp.json();
    if (!resp.ok) throw new Error(data.detail || ('HTTP ' + resp.status));
    closeCreateAssignment();
    await refreshTeacherClassData();
    alert(`作业「${data.assignment.title}」已发布，共 ${data.generated} 题。`);
  } catch (e) {
    _msg('assignment-create-msg', '发布失败：' + (e.message || e));
  } finally {
    if (btn) { btn.disabled = false; btn.textContent = old; }
  }
}

async function loadTeacherAssignments() {
  if (!_isTeacher() || !_teacherClassId) return;
  const box = document.getElementById('teacher-assignment-list');
  if (!box) return;
  box.innerHTML = '<p class="text-xs text-slate-500">加载中...</p>';
  try {
    const resp = await fetch(`/api/teacher/assignments?class_id=${encodeURIComponent(_teacherClassId)}`);
    if (!resp.ok) throw new Error('HTTP ' + resp.status);
    const data = await resp.json();
    const items = data.assignments || [];
    if (!items.length) {
      box.innerHTML = '<p class="text-xs text-slate-500">还没有布置作业 · 点右上角「布置统一作业」</p>';
      return;
    }
    box.innerHTML = items.map(a => `
      <div class="row-item">
        <span class="text-slate-200 font-medium flex-1 min-w-[140px]">${escapeHtml(a.title)}</span>
        <span class="text-slate-500">${a.question_count} 题</span>
        <span class="text-slate-400">提交 ${a.submitted_count}/${a.total_students ?? '—'}</span>
        <span class="text-slate-400">均分 ${a.avg_score == null ? '—' : a.avg_score}</span>
        <span class="${a.status === 'closed' ? 'text-rose-300' : 'text-emerald-300'}">${a.status === 'closed' ? '已关闭' : '进行中'}</span>
        <button onclick="viewTeacherAssignment(${jsStr(a.id)})" class="btn btn-ghost btn-xs">查看提交</button>
      </div>
    `).join('');
  } catch (e) {
    box.innerHTML = '<p class="text-xs text-rose-400">作业列表加载失败</p>';
  }
}

async function viewTeacherAssignment(assignmentId) {
  const modal = document.getElementById('teacher-detail-modal');
  const content = document.getElementById('teacher-detail-content');
  if (!modal || !content) return;
  content.innerHTML = '<p class="text-sm text-slate-400">加载中...</p>';
  modal.classList.remove('hidden');
  try {
    const resp = await fetch('/api/teacher/assignments/' + encodeURIComponent(assignmentId));
    if (!resp.ok) throw new Error('HTTP ' + resp.status);
    const data = await resp.json();
    const a = data.assignment;
    const subs = Object.values(data.submissions || {});
    const statusLabel = { published: '进行中', closed: '已关闭', draft: '草稿' }[a.status] || a.status;
    content.innerHTML = `
      <div class="modal-head">
        <div>
          <h2 class="modal-title">${escapeHtml(a.title)}</h2>
          <p class="modal-sub">${a.questions.length} 题 · ${escapeHtml(statusLabel)} · ${a.due_at ? '截止 ' + escapeHtml(a.due_at.slice(0, 16).replace('T', ' ')) : '无截止时间'}</p>
        </div>
        <button onclick="closeTeacherAssignmentModal()" class="modal-close" aria-label="关闭">
          <svg class="cm-icon cm-icon-lg" aria-hidden="true"><use href="#i-x"></use></svg>
        </button>
      </div>
      ${subs.length ? `
        <div class="space-y-2">
          ${subs.map(s => `
            <div class="row-item">
              <span class="text-slate-200 font-medium flex-1">${escapeHtml(s.student_id)}</span>
              <span class="text-accent">得分 ${s.teacher_override ?? s.score}</span>
              <span class="text-slate-400">${s.correct_count}/${s.total} 正确</span>
              ${s.late ? '<span class="tag tag-warning">迟交</span>' : ''}
              <span class="text-[10px] text-slate-500">${escapeHtml((s.submitted_at || '').slice(0, 16).replace('T', ' '))}</span>
            </div>
          `).join('')}
        </div>` : '<div class="empty-state" style="padding:24px 0"><p class="empty-sub">还没有学生提交。</p></div>'}
    `;
  } catch (e) {
    content.innerHTML = '<p class="text-sm text-rose-400">加载失败：' + escapeHtml(e.message || String(e)) + '</p>';
  }
}

function closeTeacherAssignmentModal() {
  document.getElementById('teacher-detail-modal')?.classList.add('hidden');
}

/* ==================== 学生：加入班级 / 作业列表 ==================== */

async function joinClassUI() {
  if (!_loggedIn() || _role() !== 'student') {
    alert('请先使用学生账号登录');
    return;
  }
  const input = document.getElementById('class-join-code');
  const msg = document.getElementById('class-join-msg');
  const code = (input?.value || '').trim().toUpperCase();
  if (!code) {
    if (msg) { msg.textContent = '请输入邀请码'; msg.className = 'msg-err mt-2'; msg.classList.remove('hidden'); }
    return;
  }
  try {
    const resp = await fetch('/api/classes/join', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ join_code: code }),
    });
    const data = await resp.json();
    if (!resp.ok) throw new Error(data.detail || ('HTTP ' + resp.status));
    if (input) input.value = '';
    if (msg) {
      msg.textContent = `已加入「${data.name}」`;
      msg.className = 'msg-ok mt-2';
      msg.classList.remove('hidden');
    }
    await loadStudentAssignments();
  } catch (e) {
    if (msg) {
      msg.textContent = '加入失败：' + (e.message || e);
      msg.className = 'msg-err mt-2';
      msg.classList.remove('hidden');
    }
  }
}

async function loadStudentAssignments() {
  if (_isTeacher()) return;
  const box = document.getElementById('student-assignment-list');
  if (!box) return;
  if (!_loggedIn()) {
    box.innerHTML = '<p class="text-xs text-slate-500">登录后查看老师布置的统一作业。</p>';
    return;
  }
  box.innerHTML = '<p class="text-xs text-slate-500">加载中...</p>';
  try {
    const resp = await fetch('/api/assignments/mine');
    if (!resp.ok) throw new Error('HTTP ' + resp.status);
    const data = await resp.json();
    const items = (data.assignments || []).sort((a, b) => {
      const sa = a.my_submission ? 1 : 0;
      const sb = b.my_submission ? 1 : 0;
      return sa - sb;
    });
    if (!items.length) {
      box.innerHTML = '<p class="text-xs text-slate-500">暂无班级作业 · 加入班级后这里会出现老师布置的任务</p>';
      return;
    }
    box.innerHTML = items.map(a => {
      const sub = a.my_submission;
      return `
        <div class="row-item">
          <span class="text-slate-200 font-medium flex-1 min-w-[140px]">${escapeHtml(a.title)}</span>
          <span class="text-slate-500">${escapeHtml((a.class_names || []).join('、'))}</span>
          <span class="text-slate-500">${a.question_count} 题</span>
          ${a.due_at ? `<span class="text-slate-500">截止 ${escapeHtml(a.due_at.slice(0, 16).replace('T', ' '))}</span>` : ''}
          ${sub
            ? `<span class="tag tag-success">已提交 · ${sub.score} 分</span><button onclick="openAssignment(${jsStr(a.id)})" class="btn btn-ghost btn-xs">查看结果</button>`
            : `<span class="tag tag-warning">待完成</span><button onclick="openAssignment(${jsStr(a.id)})" class="btn btn-primary btn-xs">开始作答</button>`}
        </div>`;
    }).join('');
  } catch (e) {
    box.innerHTML = '<p class="text-xs text-rose-400">作业加载失败</p>';
  }
}

/* ==================== 学生：作答 ==================== */

function _questionCard(q, index) {
  const typeLabel = { choice: '选择题', judge: '判断题', code: '编程题', blank: '填空题', short: '简答题' }[q.type] || q.type;
  let inputHtml = '';
  if (q.type === 'choice') {
    inputHtml = `<div class="option-list mt-3">${(q.options || []).map((opt, i) => {
      const raw = String(opt);
      const display = /^\s*[A-Ha-h]\s*[.、:：)]/.test(raw)
        ? raw
        : String.fromCharCode(65 + i) + '. ' + raw;
      return `
      <label class="option-btn flex items-start gap-2 cursor-pointer">
        <input type="radio" name="ans_${escapeHtml(q.id)}" value="${escapeHtml(display)}" class="mt-0.5">
        <span>${escapeHtml(display)}</span>
      </label>`;
    }).join('')}</div>`;
  } else if (q.type === 'judge') {
    inputHtml = `<div class="flex gap-3 mt-3">
      <label class="option-btn flex items-center gap-2 cursor-pointer"><input type="radio" name="ans_${escapeHtml(q.id)}" value="正确">正确</label>
      <label class="option-btn flex items-center gap-2 cursor-pointer"><input type="radio" name="ans_${escapeHtml(q.id)}" value="错误">错误</label>
    </div>`;
  } else if (q.type === 'code') {
    const cases = (q.test_cases || []).slice(0, 5).map(c =>
      `<div class="font-mono text-[11px] text-slate-400">输入 ${escapeHtml(String(c.input || ''))} → 期望 ${escapeHtml(String(c.expected || ''))}</div>`
    ).join('');
    inputHtml = `
      ${cases ? `<div class="mt-3 p-2 rounded bg-slate-950/70 border border-slate-700/40">${cases}</div>` : ''}
      <textarea id="code_${escapeHtml(q.id)}" rows="6" placeholder="# 写你的 Python 代码"
        class="code-editor w-full mt-3 p-3"></textarea>`;
  } else {
    inputHtml = `<textarea id="ans_${escapeHtml(q.id)}" rows="4" class="w-full mt-3 p-3 text-sm" placeholder="写下你的答案..."></textarea>`;
  }
  return `
    <div class="question-card">
      <div class="question-meta">
        <span class="tag tag-accent">第 ${index + 1} 题 · ${typeLabel}</span>
        ${q.concept ? `<span class="tag">${escapeHtml(q.concept)}</span>` : ''}
      </div>
      <div class="question-text prose-cm">${mdSafe(q.question || '')}</div>
      ${inputHtml}
    </div>`;
}

async function openAssignment(assignmentId) {
  const modal = document.getElementById('take-assignment-modal');
  const content = document.getElementById('take-assignment-content');
  if (!modal || !content) return;
  content.innerHTML = '<p class="text-sm text-slate-400">加载中...</p>';
  modal.classList.remove('hidden');
  try {
    const resp = await fetch('/api/assignments/' + encodeURIComponent(assignmentId));
    if (!resp.ok) throw new Error('HTTP ' + resp.status);
    const data = await resp.json();
    _currentAssignment = data;
    if (data.my_submission) {
      renderAssignmentResult(data.assignment, data.my_submission);
      return;
    }
    const questions = data.questions || [];
    content.innerHTML = `
      <div class="modal-head">
        <div>
          <h2 class="modal-title">${escapeHtml(data.assignment.title)}</h2>
          <p class="modal-sub">${escapeHtml((data.assignment.class_names || []).join('、'))} · ${questions.length} 题${data.assignment.due_at ? ' · 截止 ' + escapeHtml(data.assignment.due_at.slice(0, 16).replace('T', ' ')) : ''}</p>
        </div>
        <button onclick="closeTakeAssignment()" class="modal-close" aria-label="关闭">
          <svg class="cm-icon cm-icon-lg" aria-hidden="true"><use href="#i-x"></use></svg>
        </button>
      </div>
      <div class="space-y-3">${questions.map(_questionCard).join('')}</div>
      <div id="assignment-take-msg" class="hidden"></div>
      <div class="modal-actions">
        <button onclick="closeTakeAssignment()" class="btn btn-ghost btn-sm">取消</button>
        <button onclick="submitAssignmentFromUI()" id="assignment-submit-btn" class="btn btn-primary btn-sm">提交作业</button>
      </div>`;
  } catch (e) {
    content.innerHTML = '<p class="text-sm text-rose-400">加载失败：' + escapeHtml(e.message || String(e)) + '</p>';
  }
}

function _mergeSubmissionToLocal(assignmentId, questions, submission) {
  if (!submission || !Array.isArray(submission.results)) return;
  const byId = Object.fromEntries((questions || []).map(q => [q.id, q]));
  const results = submission.results
    .filter(r => r && !r.teacher_note)
    .map(r => ({
      concept_id: (r.concept_ids && r.concept_ids[0]) || r.concept || 'unknown',
      concept: r.concept,
      correct: !!r.correct,
      question: byId[r.question_id] || null,
      answer: '',
    }));
  if (results.length) {
    try {
      mergeAssignmentResults(assignmentId, results);
      window.refreshTodayStats?.();
      window.refreshPersonalRadar?.();
      window.refreshProgressCurve?.();
    } catch (e) { console.warn('合并作业成绩到本地学情失败', e); }
  }
}

function renderAssignmentResult(assignment, submission) {
  const content = document.getElementById('take-assignment-content');
  if (!content) return;
  const questions = (_currentAssignment && _currentAssignment.questions) || [];
  const byId = Object.fromEntries(questions.map(q => [q.id, q]));
  _mergeSubmissionToLocal(assignment.id, questions, submission);
  const results = (submission.results || []).filter(r => !r.teacher_note);
  content.innerHTML = `
    <div class="modal-head">
      <div>
        <h2 class="modal-title">${escapeHtml(assignment.title)} · 已提交</h2>
        <p class="modal-sub">${escapeHtml((assignment.class_names || []).join('、'))}${submission.late ? ' · 迟交' : ''}</p>
      </div>
      <button onclick="closeTakeAssignment()" class="modal-close" aria-label="关闭">
        <svg class="cm-icon cm-icon-lg" aria-hidden="true"><use href="#i-x"></use></svg>
      </button>
    </div>
    <div class="score-strip mb-4">
      <div>
        <div class="score-number">${submission.score ?? 0}</div>
        <div class="score-label">分</div>
      </div>
      <div class="text-sm text-slate-300">答对 ${submission.correct_count ?? 0} / ${submission.total ?? results.length}</div>
      <div class="footnote ml-auto">服务端按冻结的判题方案判分</div>
    </div>
    <div class="space-y-2">
      ${results.map((r, i) => {
        const q = byId[r.question_id] || {};
        return `<div class="row-item" style="align-items:flex-start">
          <div class="flex flex-wrap items-center gap-2 text-sm w-full">
            <span class="${r.correct ? 'text-emerald-300' : 'text-rose-300'} font-medium">第 ${i + 1} 题 · ${r.correct ? '正确' : '错误'}</span>
            <span class="text-slate-400 flex-1 min-w-[120px]">${escapeHtml(q.concept || r.concept || '')}</span>
            <span class="text-accent">${r.score ?? 0} 分</span>
          </div>
          ${r.feedback ? `<div class="text-xs text-slate-400 mt-1 w-full">${escapeHtml(String(r.feedback))}</div>` : ''}
        </div>`;
      }).join('')}
    </div>
    <div class="modal-actions">
      <button onclick="closeTakeAssignment()" class="btn btn-primary btn-sm">关闭</button>
    </div>`;
}

async function submitAssignmentFromUI() {
  const data = _currentAssignment;
  if (!data) return;
  const btn = document.getElementById('assignment-submit-btn');
  const answers = {};
  (data.questions || []).forEach(q => {
    if (q.type === 'code') {
      answers[q.id] = document.getElementById('code_' + q.id)?.value || '';
    } else if (q.type === 'choice' || q.type === 'judge') {
      const checked = document.querySelector(`input[name="ans_${q.id}"]:checked`);
      answers[q.id] = checked ? checked.value : '';
    } else {
      answers[q.id] = document.getElementById('ans_' + q.id)?.value || '';
    }
  });
  const unanswered = Object.values(answers).filter(v => !String(v).trim()).length;
  if (unanswered && !confirm(`还有 ${unanswered} 题未作答，仍要提交吗？提交后不能重做。`)) return;

  const old = btn ? btn.textContent : '';
  if (btn) { btn.disabled = true; btn.textContent = '提交判分中...'; }
  _clearMsg('assignment-take-msg');
  try {
    const resp = await fetch(`/api/assignments/${encodeURIComponent(data.assignment.id)}/submit`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ answers }),
    });
    const result = await resp.json();
    if (!resp.ok) throw new Error(result.detail || ('HTTP ' + resp.status));
    // 用提交返回结果覆盖当前作业的 submission，然后渲染结果页
    _currentAssignment.my_submission = {
      submitted: true,
      score: result.score,
      correct_count: result.correct_count,
      total: result.total,
      late: result.late,
      submitted_at: result.submitted_at,
      results: result.results,
    };
    renderAssignmentResult(data.assignment, _currentAssignment.my_submission);
    loadStudentAssignments();
  } catch (e) {
    _msg('assignment-take-msg', '提交失败：' + (e.message || e));
    if (btn) { btn.disabled = false; btn.textContent = old; }
  }
}

function closeTakeAssignment() {
  document.getElementById('take-assignment-modal')?.classList.add('hidden');
  _currentAssignment = null;
}

export {
  updateRoleUI,
  loadTeacherClasses,
  onTeacherClassChange,
  refreshTeacherClassData,
  openCreateClass,
  closeCreateClass,
  createClassUI,
  openCreateAssignment,
  closeCreateAssignment,
  createAssignmentUI,
  loadTeacherAssignments,
  viewTeacherAssignment,
  closeTeacherAssignmentModal,
  joinClassUI,
  loadStudentAssignments,
  openAssignment,
  submitAssignmentFromUI,
  closeTakeAssignment,
};
Object.assign(window, {
  updateRoleUI,
  loadTeacherClasses,
  onTeacherClassChange,
  refreshTeacherClassData,
  openCreateClass,
  closeCreateClass,
  createClassUI,
  openCreateAssignment,
  closeCreateAssignment,
  createAssignmentUI,
  loadTeacherAssignments,
  viewTeacherAssignment,
  closeTeacherAssignmentModal,
  joinClassUI,
  loadStudentAssignments,
  openAssignment,
  submitAssignmentFromUI,
  closeTakeAssignment,
});
