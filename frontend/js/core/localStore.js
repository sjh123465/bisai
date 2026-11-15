/**
 * @file 浏览器本地个人学情（BKT / 错题本 / 答题历史）
 * @module core/localStore
 *
 * 日常练习数据只存在学生浏览器，不上传服务端；教师任何接口都读不到。
 * 按登录用户名分区，未登录使用 guest。作业成绩由服务端返回后，可显式合并到本地。
 */

const VERSION = 1;
const MAX_HISTORY = 1200;
const MAX_WRONGBOOK = 300;
const BKT_INITIAL = 0.3;
const BKT_CORRECT = 0.15;
const BKT_WRONG = -0.10;
const BKT_MIN = 0.05;
const BKT_MAX = 0.98;

function currentUser() {
  return localStorage.getItem('cm_user') || 'guest';
}

function storageKey() {
  return `cm_profile_v1:${encodeURIComponent(currentUser())}`;
}

function _empty() {
  return {
    version: VERSION,
    mastery: {},        // concept_id -> 掌握度
    names: {},          // concept_id -> 中文名
    history: [],        // {concept_id, correct, time, source, assignment_id?}
    wrongbook: [],      // {concept_id, name, question, student_answer, time, source}
    merged_assignments: [],
  };
}

function _normalize(raw) {
  const base = _empty();
  if (!raw || typeof raw !== 'object') return base;
  return {
    version: VERSION,
    mastery: raw.mastery && typeof raw.mastery === 'object' ? raw.mastery : {},
    names: raw.names && typeof raw.names === 'object' ? raw.names : {},
    history: Array.isArray(raw.history) ? raw.history : [],
    wrongbook: Array.isArray(raw.wrongbook) ? raw.wrongbook : [],
    merged_assignments: Array.isArray(raw.merged_assignments) ? raw.merged_assignments : [],
  };
}

function loadProfile() {
  try {
    const raw = localStorage.getItem(storageKey());
    return _normalize(raw ? JSON.parse(raw) : null);
  } catch (e) {
    console.warn('[localStore] 学情数据读取失败，使用空档案', e);
    return _empty();
  }
}

function saveProfile(profile) {
  profile.version = VERSION;
  if (profile.history.length > MAX_HISTORY) profile.history = profile.history.slice(-MAX_HISTORY);
  if (profile.wrongbook.length > MAX_WRONGBOOK) profile.wrongbook = profile.wrongbook.slice(-MAX_WRONGBOOK);
  try {
    localStorage.setItem(storageKey(), JSON.stringify(profile));
  } catch (e) {
    console.error('[localStore] 本地存储写入失败（可能空间不足）', e);
    throw e;
  }
  window.dispatchEvent(new CustomEvent('cm-profile-updated', { detail: { user: currentUser() } }));
  return profile;
}

function clamp(v) {
  return Math.max(BKT_MIN, Math.min(BKT_MAX, v));
}

function _applyAnswer(profile, conceptId, conceptName, correct, time, source, assignmentId, question, answer, skipWrongbook = false) {
  const cid = conceptId || (question && question.concept_id) || 'unknown';
  const name = conceptName || (question && question.concept) || profile.names[cid] || cid;
  const prev = typeof profile.mastery[cid] === 'number' ? profile.mastery[cid] : BKT_INITIAL;
  const next = clamp(prev + (correct ? BKT_CORRECT : BKT_WRONG));
  profile.mastery[cid] = next;
  profile.names[cid] = name;
  profile.history.push({
    concept_id: cid,
    concept: name,
    correct: !!correct,
    time,
    source: source || 'personal',
    ...(assignmentId ? { assignment_id: assignmentId } : {}),
  });
  if (!correct && !skipWrongbook) {
    profile.wrongbook.push({
      concept_id: cid,
      name,
      question: question || null,
      student_answer: String(answer == null ? '' : answer).slice(0, 2000),
      time,
      source: source || 'personal',
      ...(assignmentId ? { assignment_id: assignmentId } : {}),
    });
  }
  return next;
}

/** 记录一次个人练习答题；返回该知识点最新掌握度。 */
function recordAnswer(conceptId, conceptName, question, answer, correct, source = 'personal', opts = {}) {
  const profile = loadProfile();
  const time = new Date().toISOString();
  const next = _applyAnswer(
    profile, conceptId, conceptName, !!correct, time, source, null, question, answer,
    !!opts.skipWrongbook,
  );
  saveProfile(profile);
  return { concept_id: conceptId, mastery: next };
}

/** 错题重做正确后移除对应错题记录（按知识点 + 首次答错时间）。 */
function resolveWrong(conceptId, wrongTime) {
  const profile = loadProfile();
  const before = profile.wrongbook.length;
  profile.wrongbook = profile.wrongbook.filter(it =>
    !(it.concept_id === conceptId && String(it.time) === String(wrongTime))
  );
  if (profile.wrongbook.length !== before) saveProfile(profile);
}

/**
 * 合并一次班级作业的批改结果（服务端返回）。按 assignmentId 幂等，防止刷新页面重复扣分。
 * results: [{concept_id, concept, correct, question, answer}]
 */
function mergeAssignmentResults(assignmentId, results) {
  if (!assignmentId || !Array.isArray(results) || !results.length) return { merged: false, count: 0 };
  const profile = loadProfile();
  if (profile.merged_assignments.includes(assignmentId)) return { merged: false, count: 0 };
  const time = new Date().toISOString();
  results.forEach(r => {
    _applyAnswer(
      profile,
      r.concept_id,
      r.concept,
      !!r.correct,
      r.time || time,
      'assignment',
      assignmentId,
      r.question,
      r.answer,
    );
  });
  profile.merged_assignments.push(assignmentId);
  saveProfile(profile);
  return { merged: true, count: results.length };
}

function getMastery() {
  return { ...loadProfile().mastery };
}

/** 带中文名的掌握度，供雷达图直接使用。 */
function getMasteryNamed() {
  const p = loadProfile();
  const out = {};
  Object.entries(p.mastery).forEach(([cid, score]) => {
    out[p.names[cid] || cid] = score;
  });
  return out;
}

function getWeakPoints(threshold = 0.6, limit = 10) {
  const p = loadProfile();
  return Object.entries(p.mastery)
    .filter(([, v]) => typeof v === 'number' && v < threshold)
    .sort((a, b) => a[1] - b[1])
    .slice(0, limit)
    .map(([cid, v]) => ({ concept_id: cid, name: p.names[cid] || cid, mastery: Math.round(v * 1000) / 1000 }));
}

function getWrongCounts() {
  const p = loadProfile();
  const counts = {};
  p.wrongbook.forEach(it => {
    const cid = it.concept_id || 'unknown';
    counts[cid] = (counts[cid] || 0) + 1;
  });
  return counts;
}

function getWrongCountsNamed() {
  const p = loadProfile();
  const counts = {};
  p.wrongbook.forEach(it => {
    const cid = it.concept_id || 'unknown';
    const name = p.names[cid] || it.name || cid;
    counts[name] = (counts[name] || 0) + 1;
  });
  return counts;
}

function _sortByTime(records) {
  return records.slice().sort((a, b) => String(a.time).localeCompare(String(b.time)));
}

function _replayMastery(records) {
  let mastery = BKT_INITIAL;
  return records.map((r, i) => {
    mastery = clamp(mastery + (r.correct ? BKT_CORRECT : BKT_WRONG));
    return {
      index: i + 1,
      time: r.time,
      mastery: Math.round(mastery * 1000) / 1000,
      correct: !!r.correct,
    };
  });
}

function _sourceMatches(source, filter) {
  return !filter || filter === 'all' || (source || 'personal') === filter;
}

/** 连续学习天数：从今天或昨天开始，向前数有答题记录的自然日。 */
function getStudyStreak(source = 'all') {
  const p = loadProfile();
  const days = new Set();
  p.history.forEach(r => {
    if (!_sourceMatches(r.source, source)) return;
    const t = new Date(r.time);
    if (!Number.isNaN(t.getTime())) days.add(_localDayKey(t));
  });
  if (!days.size) return 0;
  const cursor = new Date();
  cursor.setHours(0, 0, 0, 0);
  if (!days.has(_localDayKey(cursor))) {
    cursor.setDate(cursor.getDate() - 1);
    if (!days.has(_localDayKey(cursor))) return 0;
  }
  let streak = 0;
  while (days.has(_localDayKey(cursor))) {
    streak++;
    cursor.setDate(cursor.getDate() - 1);
  }
  return streak;
}

/**
 * 个人学情档案：按知识点聚合掌握度、练习量、正确率、错题与 BKT 轨迹。
 * @param {'all'|'personal'|'assignment'} source - 数据来源筛选
 */
function getConceptStats(source = 'all') {
  const p = loadProfile();
  const byConcept = {};
  const ensure = (cid) => {
    if (!byConcept[cid]) {
      byConcept[cid] = {
        concept_id: cid,
        name: p.names[cid] || cid,
        mastery: typeof p.mastery[cid] === 'number' ? p.mastery[cid] : BKT_INITIAL,
        attempts: 0,
        correct: 0,
        accuracy: null,
        wrong_count: 0,
        first_time: null,
        last_time: null,
        sources: {},
        records: [],
      };
    }
    return byConcept[cid];
  };

  Object.keys(p.mastery).forEach(ensure);
  p.wrongbook.forEach(it => { if (it.concept_id) ensure(it.concept_id); });

  _sortByTime(p.history.filter(r => r && r.concept_id)).forEach(r => {
    const cid = r.concept_id;
    const c = ensure(cid);
    c.name = r.concept || c.name;
    const src = r.source || 'personal';
    c.sources[src] = (c.sources[src] || 0) + 1;
    if (!_sourceMatches(src, source)) return;
    c.attempts++;
    if (r.correct) c.correct++;
    if (!c.first_time || String(r.time) < String(c.first_time)) c.first_time = r.time;
    if (!c.last_time || String(r.time) > String(c.last_time)) c.last_time = r.time;
    c.records.push(r);
  });

  p.wrongbook.forEach(it => {
    if (!it.concept_id || !_sourceMatches(it.source, source)) return;
    ensure(it.concept_id).wrong_count++;
  });

  return Object.values(byConcept).map(c => {
    const series = _replayMastery(_sortByTime(c.records)).slice(-40);
    return {
      concept_id: c.concept_id,
      name: c.name,
      mastery: Math.round(c.mastery * 1000) / 1000,
      attempts: c.attempts,
      correct: c.correct,
      accuracy: c.attempts ? Math.round((c.correct / c.attempts) * 1000) / 1000 : null,
      wrong_count: c.wrong_count,
      first_time: c.first_time,
      last_time: c.last_time,
      sources: c.sources,
      series,
    };
  }).sort((a, b) => a.mastery - b.mastery || a.name.localeCompare(b.name, 'zh'));
}

/** 个人档案顶部的总体统计。 */
function getPersonalSummary(source = 'all') {
  const p = loadProfile();
  const concepts = getConceptStats(source);
  const active = concepts.filter(c => c.attempts > 0);
  const total = active.reduce((sum, c) => sum + c.attempts, 0);
  const correct = active.reduce((sum, c) => sum + c.correct, 0);
  const sourceCounts = {};
  p.history.forEach(r => {
    const src = r.source || 'personal';
    sourceCounts[src] = (sourceCounts[src] || 0) + 1;
  });
  return {
    scope: source,
    concepts_count: concepts.length,
    active_concepts: active.length,
    total_attempts: total,
    correct_attempts: correct,
    accuracy: total ? Math.round((correct / total) * 1000) / 1000 : null,
    // 掌握度只在当前范围内「练过」的知识点上取平均，避免把未练习概念算成薄弱
    avg_mastery: active.length
      ? Math.round((active.reduce((s, c) => s + c.mastery, 0) / active.length) * 1000) / 1000
      : 0,
    weak_count: active.filter(c => c.mastery < 0.6).length,
    streak_days: getStudyStreak(source),
    source_counts: sourceCounts,
  };
}

function getRecentRecords(conceptId, source = 'all', limit = 12) {
  return _sortByTime(loadProfile().history.filter(r =>
    r && r.concept_id === conceptId && _sourceMatches(r.source, source)
  )).reverse().slice(0, limit);
}

function getWrongItemsForConcept(conceptId, source = 'all') {
  return loadProfile().wrongbook
    .filter(it => it.concept_id === conceptId && _sourceMatches(it.source, source))
    .sort((a, b) => String(b.time).localeCompare(String(a.time)));
}

function getWrongList() {
  return [...loadProfile().wrongbook].reverse();
}

/** 错题重做：按知识点去重，每个知识点取最新一道。 */
function getRetryQuestions(limit = 10) {
  const p = loadProfile();
  const latest = {};
  p.wrongbook.forEach(it => {
    const cid = it.concept_id;
    if (!cid) return;
    if (!latest[cid] || String(it.time) > String(latest[cid].time)) latest[cid] = it;
  });
  return Object.values(latest)
    .sort((a, b) => String(b.time).localeCompare(String(a.time)))
    .slice(0, limit)
    .map(it => ({
      concept_id: it.concept_id,
      name: it.name || '',
      question: it.question,
      wrong_time: it.time,
      source: it.source || 'personal',
      assignment_id: it.assignment_id || '',
    }));
}

function _localDayKey(d) {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  return `${y}-${m}-${day}`;
}

function getTodayStats() {
  const p = loadProfile();
  const today = _localDayKey(new Date());
  const todayRecords = p.history.filter(r => {
    const t = new Date(r.time);
    return !Number.isNaN(t.getTime()) && _localDayKey(t) === today;
  });
  const answered = todayRecords.length;
  const correct = todayRecords.filter(r => r.correct).length;
  let streak = 0;
  for (let i = todayRecords.length - 1; i >= 0; i--) {
    if (todayRecords[i].correct) streak++;
    else break;
  }
  return {
    answered,
    correct,
    accuracy: answered ? Math.round((correct / answered) * 1000) / 1000 : null,
    streak,
  };
}

/**
 * 近 N 天趋势；先重放窗口前的历史得到基线，再逐日累加，避免把最终状态污染到早期日期。
 * 返回 [{date,label,answered,correct,accuracy,mastery(0-1)}]
 */
function getDailyTrend(days = 7, source = 'all') {
  const p = loadProfile();
  const records = p.history
    .filter(r => r && r.concept_id && r.time && _sourceMatches(r.source, source))
    .slice()
    .sort((a, b) => String(a.time).localeCompare(String(b.time)));

  const start = new Date();
  start.setHours(0, 0, 0, 0);
  start.setDate(start.getDate() - (days - 1));

  const state = {};
  const pending = [];
  for (const r of records) {
    const t = new Date(r.time);
    if (Number.isNaN(t.getTime())) continue;
    if (t < start) {
      const prev = typeof state[r.concept_id] === 'number' ? state[r.concept_id] : BKT_INITIAL;
      state[r.concept_id] = clamp(prev + (r.correct ? BKT_CORRECT : BKT_WRONG));
    } else {
      pending.push({ ...r, _t: t });
    }
  }

  const trend = [];
  let idx = 0;
  for (let i = 0; i < days; i++) {
    const dayStart = new Date(start);
    dayStart.setDate(start.getDate() + i);
    const dayEnd = new Date(dayStart);
    dayEnd.setDate(dayStart.getDate() + 1);

    let answered = 0;
    let correct = 0;
    while (idx < pending.length && pending[idx]._t < dayEnd) {
      const r = pending[idx];
      if (r._t >= dayStart) {
        const prev = typeof state[r.concept_id] === 'number' ? state[r.concept_id] : BKT_INITIAL;
        state[r.concept_id] = clamp(prev + (r.correct ? BKT_CORRECT : BKT_WRONG));
        answered++;
        if (r.correct) correct++;
      }
      idx++;
    }
    const values = Object.values(state);
    const mastery = values.length ? values.reduce((a, b) => a + b, 0) / values.length : 0;
    trend.push({
      date: _localDayKey(dayStart),
      label: `${dayStart.getMonth() + 1}/${dayStart.getDate()}`,
      answered,
      correct,
      accuracy: answered ? Math.round((correct / answered) * 1000) / 1000 : null,
      mastery: Math.round(mastery * 10000) / 10000,
    });
  }
  return trend;
}

/** 发给 Agent 的本地学情摘要；只在当前请求中使用，服务端不持久化。 */
function getProfileSummary() {
  const p = loadProfile();
  const weak = Object.entries(p.mastery)
    .filter(([, v]) => typeof v === 'number' && v < 0.6)
    .sort((a, b) => a[1] - b[1])
    .slice(0, 8)
    .map(([cid, v]) => ({ concept_id: cid, name: p.names[cid] || cid, mastery: v }));
  return {
    mastery: p.mastery,
    names: p.names,
    weak,
    wrong_counts: getWrongCounts(),
  };
}

function clearProfile() {
  localStorage.removeItem(storageKey());
  window.dispatchEvent(new CustomEvent('cm-profile-updated', { detail: { user: currentUser(), cleared: true } }));
}

function exportProfile() {
  return JSON.stringify(loadProfile(), null, 2);
}

function importProfile(text) {
  const data = JSON.parse(text);
  if (!data || typeof data !== 'object') throw new Error('不是合法的学情文件');
  const normalized = _normalize(data);
  saveProfile(normalized);
  return normalized;
}

export {
  currentUser,
  loadProfile,
  recordAnswer,
  resolveWrong,
  mergeAssignmentResults,
  getMastery,
  getMasteryNamed,
  getWeakPoints,
  getWrongCounts,
  getWrongCountsNamed,
  getWrongList,
  getRetryQuestions,
  getTodayStats,
  getDailyTrend,
  getProfileSummary,
  getConceptStats,
  getPersonalSummary,
  getRecentRecords,
  getWrongItemsForConcept,
  getStudyStreak,
  clearProfile,
  exportProfile,
  importProfile,
};
Object.assign(window, {
  cmLocal: {
    currentUser,
    loadProfile,
    recordAnswer,
    resolveWrong,
    mergeAssignmentResults,
    getMastery,
    getMasteryNamed,
    getWeakPoints,
    getWrongCounts,
    getWrongCountsNamed,
    getWrongList,
    getRetryQuestions,
    getTodayStats,
    getDailyTrend,
    getProfileSummary,
    getConceptStats,
    getPersonalSummary,
    getRecentRecords,
    getWrongItemsForConcept,
    getStudyStreak,
    clearProfile,
    exportProfile,
    importProfile,
  },
});
