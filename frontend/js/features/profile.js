/**
 * @file 个人学情档案：知识点掌握、BKT 趋势、来源筛选与 LLM 分析
 * @module features/profile
 *
 * 所有个人练习数据仍只存在浏览器；只有用户主动点击分析时，
 * 才把汇总后的掌握度 / 趋势 / 错题计数发给服务端调用用户自己的模型。
 */
import { API } from '../core/env.js';
import { escapeHtml, jsStr, mdSafe } from '../core/render.js';
import {
  getConceptStats,
  getPersonalSummary,
  getRecentRecords,
  getDailyTrend,
} from '../core/localStore.js';
import { loadLatestAnalysis, saveLatestAnalysis, clearLatestAnalysis } from '../core/analysisStore.js';

const SCOPE_LABEL = { all: '全部', personal: '个人练习', assignment: '班级作业' };
const SOURCE_LABEL = { personal: '个人练习', assignment: '班级作业' };
const SOURCE_TONE = { personal: 'tag', assignment: 'tag tag-accent' };

const STATE = {
  scope: 'all',
  concepts: [],
  summary: null,
  selectedId: null,
  trend: [],
  plugin: null,
  analysis: null,
  analysisRequest: null,
  analysisToken: 0,
  lastFocus: null,
};
let _trendChart = null;
let _pluginCache = null;
let _pluginPromise = null;

const COLORS = (() => {
  const css = getComputedStyle(document.documentElement);
  const read = (name, fallback) => css.getPropertyValue(name).trim() || fallback;
  return {
    accent: read('--accent', '#A8442E'),
    success: read('--success', '#4F6B4A'),
    danger: read('--danger', '#A33A2E'),
    warning: read('--warning', '#9A6B2F'),
    ink: read('--ink', '#1F1D1A'),
    secondary: read('--ink-secondary', '#57524A'),
    tertiary: read('--ink-tertiary', '#857E72'),
    faint: read('--ink-faint', '#A39B8D'),
    line: read('--line', '#DDD5C6'),
    paper: read('--paper-raised', '#FBF8F1'),
  };
})();

function _pct(value) {
  return value === null || value === undefined ? '—' : `${Math.round(Number(value) * 100)}%`;
}

function _date(iso) {
  return (iso || '').slice(0, 16).replace('T', ' ') || '—';
}

function _tone(value) {
  if (value < 0.6) return 'is-low';
  if (value < 0.8) return 'is-mid';
  return 'is-high';
}

function _sparkline(series) {
  if (!series || series.length < 2) return '';
  const width = 86;
  const height = 20;
  const pad = 2;
  const points = series.map((p, i) => {
    const x = pad + (i / (series.length - 1)) * (width - pad * 2);
    const y = height - pad - Math.max(0, Math.min(1, p.mastery)) * (height - pad * 2);
    return [x, y];
  });
  const path = points.map(([x, y], i) => `${i ? 'L' : 'M'}${x.toFixed(1)} ${y.toFixed(1)}`).join(' ');
  const [lx, ly] = points[points.length - 1];
  return `<svg class="pci-spark" viewBox="0 0 ${width} ${height}" preserveAspectRatio="none" aria-hidden="true">
    <path d="${path}"></path><circle cx="${lx.toFixed(1)}" cy="${ly.toFixed(1)}" r="1.6"></circle>
  </svg>`;
}

function _pluginText(plugin) {
  const gen = plugin?.generator || {};
  const grader = plugin?.grader || {};
  if (!gen.name && !grader.name) return '当前插件信息暂不可用';
  return `当前插件：${gen.name || gen.id || '未知'} v${gen.version || '?'} · 判题：${grader.name || grader.id || '未知'} v${grader.version || '?'}`;
}

async function _loadPlugin() {
  if (_pluginCache) return _pluginCache;
  if (_pluginPromise) return _pluginPromise;
  _pluginPromise = fetch(API + '/plugins')
    .then(r => (r.ok ? r.json() : null))
    .then(data => { _pluginCache = data; return data; })
    .catch(() => null)
    .finally(() => { _pluginPromise = null; });
  return _pluginPromise;
}

function _modal() {
  return document.getElementById('profile-detail-modal');
}

function _refreshData() {
  STATE.concepts = getConceptStats(STATE.scope);
  STATE.summary = getPersonalSummary(STATE.scope);
  STATE.trend = getDailyTrend(30, STATE.scope);
  const exists = STATE.concepts.some(c => c.concept_id === STATE.selectedId);
  if (!exists) STATE.selectedId = STATE.concepts[0]?.concept_id || null;
}

function _renderScopeButtons() {
  document.querySelectorAll('#profile-detail-modal .profile-scope').forEach(btn => {
    const active = btn.dataset.scope === STATE.scope;
    btn.classList.toggle('active', active);
    btn.setAttribute('aria-selected', active ? 'true' : 'false');
  });
}

function _renderSummary() {
  const el = document.getElementById('profile-summary');
  const s = STATE.summary;
  if (!el || !s) return;
  const stats = [
    ['总答题', s.total_attempts ?? 0],
    ['正确率', _pct(s.accuracy)],
    ['平均掌握度', _pct(s.avg_mastery)],
    ['薄弱知识点', s.weak_count ?? 0],
    ['已练习知识点', s.active_concepts ?? 0],
    ['连续学习', `${s.streak_days ?? 0} 天`],
  ];
  el.innerHTML = stats.map(([label, value]) => `
    <div class="profile-stat">
      <div class="profile-stat-label">${label}</div>
      <div class="profile-stat-value">${escapeHtml(String(value))}</div>
    </div>
  `).join('');
  const analyzeAll = document.getElementById('profile-analyze-all');
  if (analyzeAll) {
    const hasData = (s.total_attempts || 0) > 0;
    analyzeAll.disabled = !hasData;
    analyzeAll.title = hasData ? '基于本浏览器汇总数据生成分析' : '先答几道题，再生成分析';
  }
}

function _scrollToAnalysis() {
  const box = document.getElementById('profile-analysis-box');
  if (!box) return;
  const pane = document.getElementById('profile-detail-pane');
  const modalBody = document.querySelector('#profile-detail-modal .profile-body');
  if (window.innerWidth <= 800 && modalBody) {
    const top = box.getBoundingClientRect().top - modalBody.getBoundingClientRect().top + modalBody.scrollTop - 8;
    modalBody.scrollTop = Math.max(0, top);
    return;
  }
  if (pane) {
    const top = box.getBoundingClientRect().top - pane.getBoundingClientRect().top + pane.scrollTop - 8;
    pane.scrollTop = Math.max(0, top);
  }
}

function _renderList() {
  const el = document.getElementById('profile-concept-list');
  const countEl = document.getElementById('profile-concept-count');
  if (!el) return;
  if (countEl) countEl.textContent = `${STATE.concepts.length} 个${STATE.scope === 'all' ? '' : ' · 掌握度为总体值'}`;
  if (!STATE.concepts.length) {
    el.innerHTML = '<p class="footnote p-3">还没有练习记录。去「练一练」答一道题后，这里会生成画像。</p>';
    return;
  }
  el.innerHTML = STATE.concepts.map(c => {
    const pct = Math.round(c.mastery * 100);
    const active = c.concept_id === STATE.selectedId;
    return `
      <button class="profile-concept-item ${active ? 'active' : ''}" onclick="selectProfileConcept(${jsStr(c.concept_id)})" title="最近练习：${escapeHtml(_date(c.last_time))}">
        <div class="pci-top">
          <span class="pci-name">${escapeHtml(c.name || c.concept_id)}</span>
          <span class="pci-pct">${pct}%</span>
        </div>
        <div class="pci-meta">${c.attempts} 次 · 正确率 ${_pct(c.accuracy)}${c.wrong_count ? ` · 错题 ${c.wrong_count}` : ''}</div>
        <div class="pci-bar"><span class="${_tone(c.mastery)}" style="width:${pct}%"></span></div>
        ${_sparkline(c.series)}
      </button>`;
  }).join('');
}

function _recentRows(concept) {
  const records = getRecentRecords(concept.concept_id, STATE.scope, 8);
  if (!records.length) return '<p class="footnote">该来源下暂无作答记录。</p>';
  return records.map(r => `
    <div class="profile-recent-row">
      <span class="profile-recent-dot" style="background:${r.correct ? COLORS.success : COLORS.danger}"></span>
      <span class="flex-1">${r.correct ? '答对' : '答错'} · ${SOURCE_LABEL[r.source] || '练习'}</span>
      <span class="footnote">${escapeHtml(_date(r.time))}</span>
    </div>
  `).join('');
}

function _renderDetail() {
  const el = document.getElementById('profile-concept-detail');
  if (!el) return;
  _disposeTrendChart();
  const c = STATE.concepts.find(x => x.concept_id === STATE.selectedId);
  if (!c) {
    el.innerHTML = `
      <div class="profile-empty">
        <p class="empty-title">还没有练习记录</p>
        <p class="empty-sub">去「练一练」答一道题后，这里会显示每个知识点的掌握度和变化趋势。</p>
        <button onclick="closeProfileDetail();switchTab('practice')" class="btn btn-primary btn-sm mt-4">去练一练</button>
      </div>`;
    return;
  }
  const sourceText = Object.entries(c.sources)
    .map(([k, v]) => `${SOURCE_LABEL[k] || k} ${v}`)
    .join(' · ') || '—';
  el.innerHTML = `
    <div class="profile-detail-head">
      <div>
        <div class="eyebrow">Knowledge point</div>
        <h3 class="profile-detail-title">${escapeHtml(c.name || c.concept_id)}</h3>
        <p class="footnote mt-1">${escapeHtml(c.concept_id)} · 最近练习 ${escapeHtml(_date(c.last_time))} · 来源 ${escapeHtml(sourceText)}</p>
      </div>
      <div class="profile-score">
        <div class="profile-score-num">${Math.round(c.mastery * 100)}<span class="text-sm text-slate-500">%</span></div>
        <div class="score-label">当前掌握度</div>
      </div>
    </div>

    <div class="profile-detail-stats">
      <div><span>练习次数</span><b>${c.attempts}</b></div>
      <div><span>答对</span><b>${c.correct}</b></div>
      <div><span>正确率</span><b>${_pct(c.accuracy)}</b></div>
      <div><span>错题</span><b>${c.wrong_count}</b></div>
    </div>

    <div class="profile-chart-head">
      <span class="eyebrow">Mastery trend</span>
      <span class="footnote">按答题记录重放 BKT</span>
    </div>
    <div id="profile-concept-chart" class="profile-chart"></div>

    <div class="profile-section-head">
      <span class="eyebrow">Recent attempts</span>
      <span class="footnote">${STATE.scope === 'all' ? '全部来源' : SCOPE_LABEL[STATE.scope]}</span>
    </div>
    <div class="profile-recent">${_recentRows(c)}</div>

    <div class="profile-actions">
      ${c.attempts ? `
        <button id="profile-analyze-concept" onclick="generateProfileAnalysis('concept')" class="btn btn-primary btn-sm">
          <svg class="cm-icon cm-icon-sm" aria-hidden="true"><use href="#i-spark"></use></svg>AI 分析这个知识点
        </button>` : `<span class="footnote">先练一道题，才能分析这个知识点的趋势。</span>`}
      ${c.wrong_count ? `<button onclick="goRetryFromProfile()" class="btn btn-ghost btn-sm">去错题重做</button>` : ''}
    </div>
  `;
  setTimeout(() => {
    if (STATE.selectedId === c.concept_id) _renderConceptChart(c);
  }, 30);
}

function _disposeTrendChart() {
  if (_trendChart) {
    try { _trendChart.dispose(); } catch (_) { /* ignore */ }
    _trendChart = null;
  }
}

function _renderConceptChart(concept) {
  const modal = _modal();
  if (!modal || modal.classList.contains('hidden')) return;
  const el = document.getElementById('profile-concept-chart');
  if (!el) return;
  if (typeof echarts === 'undefined') {
    el.innerHTML = '<p class="footnote">图表库未加载，暂时无法绘制趋势。</p>';
    return;
  }
  if (!concept.series || concept.series.length < 2) {
    el.innerHTML = '<p class="footnote" style="padding-top:28px">答题次数太少，暂时画不出趋势。再练 2–3 道后会显示掌握度变化。</p>';
    return;
  }
  _disposeTrendChart();
  _trendChart = echarts.init(el, null, { renderer: 'canvas' });
  const data = concept.series.map(p => ({
    value: Math.round(p.mastery * 100),
    itemStyle: { color: p.correct ? COLORS.success : COLORS.danger },
  }));
  _trendChart.setOption({
    backgroundColor: 'transparent',
    grid: { left: 34, right: 12, top: 18, bottom: 26 },
    tooltip: {
      trigger: 'axis',
      backgroundColor: COLORS.paper,
      borderColor: COLORS.line,
      borderWidth: 1,
      textStyle: { color: COLORS.secondary, fontSize: 11 },
      extraCssText: 'box-shadow:0 8px 24px rgba(31,29,26,.08);border-radius:6px;',
      formatter: params => {
        const point = concept.series[params[0]?.dataIndex ?? 0];
        if (!point) return '';
        return `${escapeHtml(_date(point.time))}<br>${point.correct ? '答对' : '答错'} · 掌握度 ${Math.round(point.mastery * 100)}%`;
      },
    },
    xAxis: {
      type: 'category',
      data: concept.series.map(p => `#${p.index}`),
      axisLine: { lineStyle: { color: COLORS.line } },
      axisTick: { show: false },
      axisLabel: { color: COLORS.faint, fontSize: 10 },
    },
    yAxis: {
      type: 'value', min: 0, max: 100,
      splitLine: { lineStyle: { color: COLORS.line } },
      axisLabel: { color: COLORS.faint, fontSize: 10, formatter: '{value}%' },
    },
    series: [{
      type: 'line',
      data,
      smooth: true,
      symbolSize: 5,
      lineStyle: { width: 1.5, color: COLORS.accent },
      itemStyle: { color: COLORS.accent },
      areaStyle: { color: 'rgba(168,68,46,0.07)' },
      markLine: {
        silent: true,
        symbol: 'none',
        label: { formatter: '掌握线 60%', color: COLORS.faint, fontSize: 10 },
        lineStyle: { color: COLORS.line, type: 'dashed' },
        data: [{ yAxis: 60 }],
      },
    }],
  });
  _trendChart.resize();
}

function _updateClearAnalysisButton(show) {
  const btn = document.getElementById('profile-clear-analysis');
  if (btn) btn.classList.toggle('hidden', !show);
}

function _analysisContextLabel(entry) {
  const scope = SCOPE_LABEL[entry.scope] || entry.scope || '全部';
  return entry.concept
    ? `${entry.concept_name || entry.concept} · ${scope}`
    : `整体 · ${scope}`;
}

function _fingerprintFor(mode, concept) {
  const s = STATE.summary || {};
  const cid = mode === 'concept' && concept ? concept.concept_id : 'all';
  const last = mode === 'concept' && concept
    ? (concept.last_time || '')
    : (s.last_activity_time || '');
  return [
    STATE.scope, cid,
    s.total_attempts || 0,
    s.correct_attempts || 0,
    s.weak_count || 0,
    concept?.attempts || 0,
    last || '',
  ].join('|');
}

function _updateAnalysisHint() {
  const hintEl = document.getElementById('profile-analysis-hint');
  if (!hintEl) return;
  const a = STATE.analysis;
  if (!a) {
    hintEl.textContent = '点击上方按钮生成；仅发送汇总数据';
    return;
  }
  const sameScope = a.scope === STATE.scope;
  const sameConcept = !a.concept || a.concept === STATE.selectedId;
  if (!sameScope || !sameConcept) {
    hintEl.textContent = `当前显示的是上次分析（${_analysisContextLabel(a)}）；当前选择已变化，可重新生成`;
    return;
  }
  const concept = a.mode === 'concept'
    ? STATE.concepts.find(c => c.concept_id === a.concept)
    : null;
  const current = _fingerprintFor(a.mode, concept);
  if (a.fingerprint && current !== a.fingerprint) {
    hintEl.textContent = '数据已更新，建议重新生成分析';
  } else {
    hintEl.textContent = a.cached ? '已加载本地缓存 · 仅本次请求发送' : '仅本次请求发送，服务端不保存';
  }
}

function _clearAnalysis(hint) {
  STATE.analysis = null;
  const content = document.getElementById('profile-analysis-content');
  const hintEl = document.getElementById('profile-analysis-hint');
  if (content) content.innerHTML = '';
  if (hintEl) hintEl.textContent = hint || '点击上方按钮生成；仅发送汇总数据';
  _updateClearAnalysisButton(!!loadLatestAnalysis());
}

function _setAnalysisLoading(loading) {
  const ids = ['profile-analyze-all', 'profile-analyze-concept'];
  ids.forEach(id => {
    const btn = document.getElementById(id);
    if (btn) btn.disabled = loading;
  });
}

function _renderAnalysis(report, mode, concept, meta = {}) {
  const content = document.getElementById('profile-analysis-content');
  const hintEl = document.getElementById('profile-analysis-hint');
  if (!content) return;
  const scopeLabel = SCOPE_LABEL[meta.scope || STATE.scope] || meta.scope || '全部';
  const context = meta.context || (mode === 'concept' && concept
    ? `${concept.name || concept.concept_id} · ${scopeLabel}`
    : `整体 · ${scopeLabel}`);
  const when = meta.generated_at ? _date(meta.generated_at) : _date(new Date().toISOString());
  const cacheBadge = meta.cached ? ' · 本地缓存' : '';
  content.innerHTML = `
    <div class="profile-analysis-meta">${escapeHtml(context)} · ${escapeHtml(when)}${cacheBadge}</div>
    <div class="prose-cm">${mdSafe(report)}</div>`;
  if (hintEl) hintEl.textContent = meta.hint || '仅本次请求发送，服务端不保存';
  _updateClearAnalysisButton(true);
  _scrollToAnalysis();
}

function clearProfileAnalysisCache() {
  if (STATE.analysisRequest) {
    alert('请等待当前分析完成后再清除缓存。');
    return;
  }
  if (!loadLatestAnalysis()) {
    _updateClearAnalysisButton(false);
    return;
  }
  if (!confirm('确定清除本地保存的上一次 AI 学情分析吗？')) return;
  clearLatestAnalysis();
  STATE.analysis = null;
  const content = document.getElementById('profile-analysis-content');
  const hintEl = document.getElementById('profile-analysis-hint');
  if (content) content.innerHTML = '';
  if (hintEl) hintEl.textContent = '已清除分析缓存；点击按钮可重新生成';
  _updateClearAnalysisButton(false);
}

async function generateProfileAnalysis(mode = 'all') {
  if (window.requireLLMConfigured && !window.requireLLMConfigured()) return;
  const concept = mode === 'concept'
    ? STATE.concepts.find(c => c.concept_id === STATE.selectedId)
    : null;
  if (mode === 'concept' && !concept) return;
  if (!STATE.summary) return;

  await _loadPlugin();
  const plugin = _pluginCache || {};
  const requestScope = STATE.scope;
  const fingerprint = _fingerprintFor(mode, concept);
  const analysisConcepts = STATE.concepts.filter(c => c.attempts > 0);
  if (concept && !analysisConcepts.some(c => c.concept_id === concept.concept_id)) {
    analysisConcepts.push(concept);
  }
  const payload = {
    scope: requestScope,
    plugin,
    summary: STATE.summary,
    concepts: analysisConcepts.slice(0, 80).map(c => ({ ...c, series: c.series.slice(-12) })),
    trend: STATE.trend,
    selected_concept: mode === 'concept' ? concept.concept_id : null,
  };

  const content = document.getElementById('profile-analysis-content');
  const hintEl = document.getElementById('profile-analysis-hint');
  const token = ++STATE.analysisToken;
  STATE.analysisRequest = {
    mode,
    scope: requestScope,
    concept: mode === 'concept' ? concept.concept_id : null,
  };
  _setAnalysisLoading(true);
  if (content) {
    content.innerHTML = '<div class="profile-analysis-loading"><span class="graph-spinner"></span><span>AI 正在阅读你的学情...</span></div>';
  }
  if (hintEl) hintEl.textContent = '仅发送汇总数据，服务端不保存';
  _scrollToAnalysis();

  try {
    const resp = await fetch(API + '/analysis/personal', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    const data = await resp.json().catch(() => ({}));
    if (!resp.ok) throw new Error(data.detail || `HTTP ${resp.status}`);
    if (token !== STATE.analysisToken) return;
    const entry = saveLatestAnalysis({
      report: data.report || 'AI 未返回内容。',
      scope: requestScope,
      concept_id: mode === 'concept' ? concept.concept_id : null,
      concept_name: mode === 'concept' ? (concept.name || concept.concept_id) : '',
      fingerprint,
      model: data.model || '',
      generated_at: data.generated_at || new Date().toISOString(),
    });
    STATE.analysis = {
      mode,
      scope: requestScope,
      concept: mode === 'concept' ? concept.concept_id : null,
      concept_name: mode === 'concept' ? (concept.name || concept.concept_id) : '',
      report: entry.report,
      fingerprint: entry.fingerprint,
      generated_at: entry.generated_at,
      model: entry.model,
      cached: false,
    };
    const context = mode === 'concept'
      ? `${concept.name || concept.concept_id} · ${SCOPE_LABEL[requestScope]}`
      : `整体 · ${SCOPE_LABEL[requestScope]}`;
    _renderAnalysis(entry.report, mode, concept, {
      scope: requestScope,
      context,
      generated_at: entry.generated_at,
      hint: '已生成并写入本地缓存 · 仅本次请求发送',
    });
  } catch (e) {
    if (token !== STATE.analysisToken) return;
    if (content) content.innerHTML = `<div class="msg-err">分析失败：${escapeHtml(e.message || String(e))}</div>`;
    if (hintEl) hintEl.textContent = '请检查模型配置或稍后重试';
  } finally {
    if (token === STATE.analysisToken) {
      STATE.analysisRequest = null;
      _setAnalysisLoading(false);
    }
  }
}

function _maybeClearAnalysisOnChange() {
  // 缓存报告不因为切换筛选而消失；只更新“上下文已变化 / 数据已更新”的提示。
  _updateAnalysisHint();
}

function setProfileScope(scope) {
  if (!SCOPE_LABEL[scope] || scope === STATE.scope) return;
  if (STATE.analysisRequest) {
    STATE.analysisToken++;
    STATE.analysisRequest = null;
    _setAnalysisLoading(false);
  }
  STATE.scope = scope;
  _refreshData();
  _renderScopeButtons();
  _renderSummary();
  _renderList();
  _renderDetail();
  _maybeClearAnalysisOnChange();
}

function selectProfileConcept(conceptId) {
  if (!conceptId || conceptId === STATE.selectedId) return;
  if (STATE.analysisRequest?.concept && STATE.analysisRequest.concept !== conceptId) {
    STATE.analysisToken++;
    STATE.analysisRequest = null;
    _setAnalysisLoading(false);
  }
  STATE.selectedId = conceptId;
  _renderList();
  _renderDetail();
  _maybeClearAnalysisOnChange();
  if (window.innerWidth <= 800) {
    const body = document.querySelector('#profile-detail-modal .profile-body');
    const detail = document.getElementById('profile-concept-detail');
    if (body && detail) {
      const top = detail.getBoundingClientRect().top - body.getBoundingClientRect().top + body.scrollTop - 8;
      body.scrollTop = Math.max(0, top);
    }
  }
}

function openProfileDetail(conceptId = null) {
  const modal = _modal();
  if (!modal) return;
  const cached = loadLatestAnalysis();
  STATE.lastFocus = document.activeElement;
  // 恢复上次分析时的数据范围，让缓存报告与列表上下文一致
  STATE.scope = cached && SCOPE_LABEL[cached.scope] ? cached.scope : 'all';
  STATE.analysis = null;
  STATE.analysisRequest = null;
  STATE.analysisToken++;
  STATE.selectedId = conceptId || null;
  _setAnalysisLoading(false);
  _disposeTrendChart();
  _refreshData();
  if (conceptId && STATE.concepts.some(c => c.concept_id === conceptId)) {
    STATE.selectedId = conceptId;
  } else if (cached?.concept_id && STATE.concepts.some(c => c.concept_id === cached.concept_id)) {
    STATE.selectedId = cached.concept_id;
  }
  _renderScopeButtons();
  _renderSummary();
  _renderList();
  _renderDetail();

  if (cached) {
    STATE.analysis = {
      mode: cached.concept_id ? 'concept' : 'all',
      scope: cached.scope,
      concept: cached.concept_id || null,
      concept_name: cached.concept_name || '',
      report: cached.report,
      fingerprint: cached.fingerprint || '',
      generated_at: cached.generated_at || '',
      model: cached.model || '',
      cached: true,
    };
    const conceptForRender = cached.concept_id
      ? { concept_id: cached.concept_id, name: cached.concept_name || cached.concept_id }
      : null;
    const context = _analysisContextLabel({
      scope: cached.scope,
      concept: cached.concept_id,
      concept_name: cached.concept_name,
    });
    _renderAnalysis(cached.report, cached.concept_id ? 'concept' : 'all', conceptForRender, {
      scope: cached.scope,
      context,
      generated_at: cached.generated_at,
      cached: true,
    });
    _updateAnalysisHint();
    setTimeout(_scrollToAnalysis, 60);
  } else {
    _clearAnalysis('点击「AI 分析整体」或知识点详情里的「AI 分析这个知识点」');
  }

  modal.classList.remove('hidden');
  document.documentElement.classList.add('profile-modal-open');
  setTimeout(() => {
    const close = modal.querySelector('.modal-close');
    if (close) close.focus();
  }, 30);

  const pluginLine = document.getElementById('profile-plugin-line');
  if (pluginLine) {
    pluginLine.textContent = '正在读取当前插件...';
    _loadPlugin().then(plugin => {
      STATE.plugin = plugin;
      pluginLine.textContent = `${_pluginText(plugin)} · 数据只保存在本浏览器`;
    });
  }
}

function closeProfileDetail() {
  const modal = _modal();
  if (!modal) return;
  modal.classList.add('hidden');
  document.documentElement.classList.remove('profile-modal-open');
  STATE.analysisToken++;
  STATE.analysisRequest = null;
  _setAnalysisLoading(false);
  _disposeTrendChart();
  if (STATE.lastFocus && typeof STATE.lastFocus.focus === 'function') {
    STATE.lastFocus.focus();
  }
}

function goRetryFromProfile() {
  closeProfileDetail();
  window.switchTab?.('practice');
  setTimeout(() => window.loadRetryQuestions?.(), 160);
}

// Esc 关闭；只在档案打开时生效
document.addEventListener('keydown', e => {
  const modal = _modal();
  if (e.key === 'Escape' && modal && !modal.classList.contains('hidden')) closeProfileDetail();
});

window.addEventListener('resize', () => {
  if (_trendChart) _trendChart.resize();
});

export {
  openProfileDetail,
  closeProfileDetail,
  setProfileScope,
  selectProfileConcept,
  generateProfileAnalysis,
  clearProfileAnalysisCache,
  goRetryFromProfile,
};
Object.assign(window, {
  openProfileDetail,
  closeProfileDetail,
  setProfileScope,
  selectProfileConcept,
  generateProfileAnalysis,
  clearProfileAnalysisCache,
  goRetryFromProfile,
});
