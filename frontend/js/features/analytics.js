/**
 * @file 学情仪表盘（教师班级视图 / 学生个人视图 / 雷达图 / 热力图 / AI 报告）
 * @module features/analytics
 */
import { mdSafe, escapeHtml } from '../core/render.js';
import {
  getMasteryNamed,
  getWeakPoints,
  getWrongCountsNamed,
  getDailyTrend,
  getTodayStats,
  loadProfile,
} from '../core/localStore.js';

    // 如果图谱已加载过，直接高亮；否则等加载完
      // 先尝试点击/定位已渲染节点
        // 滚动视图定位（用 viewBox）
        // 没找到就刷新图谱再试

  // ---------- 学情仪表盘 ----------
  let radarChart, heatmapChart;

  // 图表统一色板：墨阶 + 单一朱砂强调
  const CHART = {
    ink: '#1F1D1A',
    secondary: '#57524A',
    tertiary: '#857E72',
    faint: '#A39B8D',
    line: '#DDD5C6',
    paper: '#FBF8F1',
    accent: '#A8442E',
    success: '#4F6B4A',
    warning: '#9A6B2F',
    danger: '#A33A2E',
    info: '#3E5C76',
  };
  const CHART_TOOLTIP = {
    backgroundColor: CHART.paper,
    borderColor: CHART.line,
    borderWidth: 1,
    textStyle: { color: CHART.secondary, fontSize: 11 },
    extraCssText: 'box-shadow:0 8px 24px rgba(31,29,26,.08);border-radius:6px;',
  };

  /** 学生个人视图：全部来自浏览器本地学情，不请求服务端。 */
  function renderStudentPersonalView() {
    const named = getMasteryNamed();
    const profile = loadProfile();
    const answered = Array.isArray(profile.history) ? profile.history.length : 0;
    const radarTitle = document.getElementById('radar-title');
    if (radarTitle) {
      radarTitle.textContent = answered
        ? `我的知识点掌握度 · 累计 ${answered} 次答题`
        : '我的知识点掌握度';
    }
    renderRadar(named);

    const heat = {};
    Object.entries(named).forEach(([name, score]) => {
      heat[name] = { avg: score, count: 1, low_rate: score < 0.6 ? 1 : 0 };
    });
    renderHeatmap(heat);

    const wrongNamed = getWrongCountsNamed();
    const ranking = Object.entries(wrongNamed)
      .sort((a, b) => b[1] - a[1])
      .slice(0, 10)
      .map(([name, count]) => ({
        concept_name: name,
        concept_id: name,
        wrong_count: count,
        student_count: 1,
      }));
    renderWrongRanking(ranking, true);

    const wrongHeading = document.getElementById('wrong-ranking-title');
    if (wrongHeading) wrongHeading.textContent = '我的高频错题 · 仅本地可见';
    const heatTitle = document.getElementById('heatmap-title');
    if (heatTitle) heatTitle.textContent = '我的知识点掌握分布';
    const studentTitle = document.getElementById('student-list-title');
    if (studentTitle) studentTitle.textContent = '我的本地学习提示';

    renderStudentList([], true);
  }

  /** 答题后刷新学生个人雷达/热力图/错题（仅在学情 Tab 可见时执行，避免隐藏容器反复计算）。 */
  function refreshPersonalRadar() {
    if (localStorage.getItem('cm_role') === 'teacher') return;
    const panel = document.getElementById('panel-teacher');
    if (!panel || panel.classList.contains('hidden')) return;
    renderStudentPersonalView();
  }

  /**
   * 加载学情 Tab：按登录角色渲染班级视图（教师）或个人视图（学生）。
   * @returns {Promise<void>}
   */
  async function loadTeacher() {
    const isTeacher = localStorage.getItem('cm_role') === 'teacher';

    // 学生视角：全部数据来自浏览器本地，不发任何个人学情请求到服务端
    if (!isTeacher) {
      renderStudentPersonalView();
      return;
    }

    // 教师视角：班级/作业数据由 classroom 模块加载，之后回调本模块渲染图表
    window.loadTeacherClasses?.();
  }

  /** 教师班级看板：渲染作业维度的雷达 / 热力图 / 错题榜 / 学生完成情况。 */
  function renderTeacherDashboard(data) {
    const radarTitle = document.getElementById('radar-title');
    const heatTitle = document.getElementById('heatmap-title');
    const wrongTitle = document.getElementById('wrong-ranking-title');
    const studentTitle = document.getElementById('student-list-title');
    if (radarTitle) radarTitle.textContent = '班级作业掌握度雷达';
    if (heatTitle) heatTitle.textContent = '班级作业知识点薄弱分布';
    if (wrongTitle) wrongTitle.textContent = '作业高频错题榜 · 按班级作业数据';
    if (studentTitle) studentTitle.textContent = '学生作业完成情况 · 按均分升序';

    if (!data) {
      renderRadar({});
      renderHeatmap({});
      renderWrongRanking([]);
      renderStudentList([]);
      window.__teacherDashboard = null;
      return;
    }
    const heatmap = data.heatmap || {};
    const classAvg = {};
    Object.entries(heatmap).forEach(([name, info]) => {
      classAvg[name] = Number(info.avg) || 0;
    });
    renderRadar(classAvg);
    renderHeatmap(heatmap);
    renderWrongRanking(data.wrong_ranking || []);
    renderStudentList(data.students || []);
    window.__teacherDashboard = data;
    window.__teacherClassId = data.class?.id || window.__teacherClassId;
    window.refreshDashboard?.();
    window.loadSideWeak?.();
  }

  function renderStudentList(students, personal = false) {
    const el = document.getElementById('student-list');
    if (!el) return;
    if (personal) {
      // 学生视角：有数据时展示真实统计；空档案才引导去答题。
      const named = getMasteryNamed();
      const concepts = Object.keys(named).length;
      if (!concepts) {
        el.innerHTML = `
        <div class="empty-state" style="padding:28px 16px">
          <p class="empty-title" style="font-size:18px">这是你的个人学情画像</p>
          <p class="empty-sub">提交（不是只生成）任意一道练习题后，这里会自动生成画像；日常练习数据只保存在你的浏览器中。</p>
          <div class="flex flex-wrap items-center justify-center gap-2 mt-4">
            <button onclick="switchTab('practice')" class="btn btn-primary btn-sm">去做第一道题</button>
            <button onclick="openProfileDetail()" class="btn btn-ghost btn-sm">打开完整学情档案</button>
          </div>
        </div>`;
        return;
      }
      const profile = loadProfile();
      const weak = getWeakPoints(0.6, 999);
      const today = getTodayStats();
      const accuracy = today.accuracy === null ? '—' : Math.round(today.accuracy * 100) + '%';
      el.innerHTML = `
        <div class="row-item" style="flex-direction:column;align-items:flex-start;gap:6px">
          <p class="text-sm text-slate-200">这是你的个人学情画像</p>
          <p class="text-[11px] text-slate-400">已记录 ${profile.history.length} 次答题，覆盖 ${concepts} 个知识点，其中薄弱 ${weak.length} 个；数据只保存在你的浏览器中。</p>
          <p class="text-[11px] text-slate-400">今日已答 ${today.answered} 题，正确率 <span class="text-emerald-300">${accuracy}</span>。</p>
          <div class="flex flex-wrap gap-2 mt-1">
            <button onclick="openProfileDetail()" class="btn btn-primary btn-sm">打开完整学情档案</button>
            <button onclick="switchTab('practice')" class="btn btn-ghost btn-sm">继续练习</button>
          </div>
        </div>`;
      return;
    }
    if (!students || students.length === 0) {
      el.innerHTML = `
        <div class="text-center py-4 px-3 rounded-xl bg-slate-900/60 border border-slate-700/50">
          <p class="text-xs text-slate-400 mb-1">本班还没有作业提交记录</p>
          <p class="text-[11px] text-slate-500">布置统一作业后，学生完成情况会出现在这里（不读取日常练习数据）</p>
        </div>`;
      return;
    }
    el.innerHTML = students.map((s, idx) => {
      const score = Math.max(0, Math.min(100, Number(s.avg_score) || 0));
      const submitted = Number(s.submitted) || 0;
      const total = Number(s.total_assignments) || 0;
      const weak = Array.isArray(s.weak_concepts) ? s.weak_concepts : [];
      const color = score < 40 ? 'text-rose-400' : score < 70 ? 'text-amber-400' : 'text-emerald-400';
      const tone = score < 40 ? 'is-low' : score < 70 ? 'is-mid' : 'is-high';
      return `
        <div class="student-row">
          <div class="flex flex-wrap items-center gap-3">
            <span class="text-[10px] w-5 font-serif text-slate-500 flex-shrink-0">${String(idx + 1).padStart(2, '0')}</span>
            <span class="text-sm text-slate-200 min-w-[80px] truncate flex-1">${escapeHtml(s.student_id)}</span>
            <div class="score-track">
              <span class="${tone}" style="width:${score}%"></span>
            </div>
            <span class="text-xs ${color} w-12 text-right font-medium">${score} 分</span>
            <span class="text-[10px] text-slate-500 w-16 text-right">提交 ${submitted}/${total}</span>
            <span class="text-[10px] text-slate-500 w-24 text-right">薄弱 ${Number(s.weak_count) || 0} · 错题 ${Number(s.total_wrong) || 0}</span>
          </div>
          ${weak.length ? `<div class="flex flex-wrap gap-1.5 mt-2 pl-7">${weak.map(w =>
            `<span class="tag tag-warning">${escapeHtml(w)}</span>`
          ).join('')}</div>` : ''}
        </div>`;
    }).join('');
  }

  function renderWrongRanking(ranking, personal = false) {
    const el = document.getElementById('wrong-ranking');
    if (!ranking || ranking.length === 0) {
      el.innerHTML = personal
        ? '<p class="text-xs text-slate-500">本地暂无错题 · 个人练习答错后会记录在这里</p>'
        : '<p class="text-xs text-slate-500">暂无作业错题数据 · 学生提交统一作业后自动统计</p>';
      return;
    }
    const maxCount = ranking[0].wrong_count;
    el.innerHTML = ranking.map((item, i) => {
      return `
      <div class="flex items-center gap-3 text-sm py-2 border-b border-slate-700/50 last:border-b-0">
        <span class="w-6 font-serif text-[10px] text-slate-500">${String(i + 1).padStart(2, '0')}</span>
        <div class="flex-1 min-w-0">
          <div class="flex justify-between items-center mb-1.5">
            <span class="text-slate-200 truncate">${escapeHtml(item.concept_name || item.concept_id || '')}</span>
            <div class="flex items-center gap-2 flex-shrink-0">
              <span class="tag tag-danger">错 ${Number(item.wrong_count) || 0}${personal ? ' 次' : ''}</span>
              ${personal ? '' : `<span class="text-[10px] text-slate-500">${Number(item.student_count) || 0} 人</span>`}
            </div>
          </div>
          <div class="wrong-bar">
            <span style="width:${Math.max(6, item.wrong_count/maxCount*100)}%"></span>
          </div>
        </div>
      </div>`;
    }).join('');
  }

  function renderRadar(mastery) {
    const el = document.getElementById('radar-chart');
    if (radarChart) radarChart.dispose();
    // Tab 刚显示时容器宽高可能为 0，延迟到下一帧布局完成后再初始化
    requestAnimationFrame(() => {
      if (el.clientWidth === 0) return setTimeout(() => renderRadar(mastery), 100);
      radarChart = echarts.init(el, null, {renderer: 'canvas'});
      const keys = Object.keys(mastery || {}).slice(0, 7);
      if (!keys.length) {
        radarChart.setOption({
          backgroundColor: 'transparent',
          title: {
            text: '暂无练习数据',
            subtext: '提交题目后自动生成本地学情画像',
            left: 'center', top: 'middle',
            textStyle: { color: CHART.tertiary, fontSize: 13, fontFamily: '"Noto Serif SC", "Songti SC", SimSun, serif' },
            subtextStyle: { color: CHART.faint, fontSize: 11 },
          },
        });
        return;
      }
      const values = keys.map(k => Math.round((mastery[k] || 0.3) * 100));
      radarChart.setOption({
        backgroundColor: 'transparent',
        tooltip: { trigger: 'item', ...CHART_TOOLTIP },
        radar: {
          indicator: keys.map(k => ({name: k, max: 100})),
          axisName: {color: CHART.secondary, fontSize: 11},
          splitLine: {lineStyle: {color: CHART.line}},
          splitArea: {areaStyle: {color: [CHART.paper, '#F6F2E9']}},
          axisLine: {lineStyle: {color: CHART.line}},
        },
        series: [{
          type: 'radar',
          data: [{value: values, name: '掌握度', areaStyle: {color: 'rgba(168,68,46,0.10)'}, lineStyle: {color: CHART.accent, width: 1.5}, itemStyle: {color: CHART.accent}}],
        }],
      });
    });
  }

  function renderHeatmap(heatmap) {
    const el = document.getElementById('heatmap-chart');
    if (heatmapChart) heatmapChart.dispose();
    requestAnimationFrame(() => {
      if (el.clientWidth === 0) return setTimeout(() => renderHeatmap(heatmap), 100);
      heatmapChart = echarts.init(el, null, {renderer: 'canvas'});
      const items = Object.entries(heatmap).sort((a,b) => a[1].avg - b[1].avg).slice(0, 15);
      if (items.length === 0) {
        heatmapChart.setOption({
          backgroundColor: 'transparent',
          title: {text: '暂无答题数据 · 学生答题后自动更新', left: 'center', top: 'middle', textStyle: {color: CHART.tertiary, fontSize: 13, fontFamily: '"Noto Serif SC", "Songti SC", SimSun, serif'}},
        });
        return;
      }
      heatmapChart.setOption({
        backgroundColor: 'transparent',
        tooltip: {trigger: 'axis', axisPointer: {type: 'shadow'}, ...CHART_TOOLTIP},
        grid: {left: 140, right: 20, top: 10, bottom: 30},
        xAxis: {type: 'value', max: 100, axisLabel: {color: CHART.tertiary, formatter: '{value}%'}, splitLine: {lineStyle: {color: CHART.line}}},
        yAxis: {type: 'category', data: items.map(i => i[0]), axisLabel: {color: CHART.secondary, fontSize: 11}, axisLine: {lineStyle: {color: CHART.line}}, axisTick: {show: false}},
        series: [{
          type: 'bar',
          data: items.map(i => ({value: Math.round(i[1].avg*100), itemStyle: {color: i[1].avg < 0.6 ? CHART.danger : i[1].avg < 0.8 ? CHART.warning : CHART.success}})),
          barWidth: 10,
          itemStyle: {borderRadius: [0, 2, 2, 0]},
        }],
      });
    });
  }

  async function generateReport() {
    const classId = window.__teacherClassId || document.getElementById('teacher-class-select')?.value;
    if (!classId) {
      alert('请先创建或选择一个班级');
      return;
    }
    if (window.requireLLMConfigured && !window.requireLLMConfigured()) return;

    const box = document.getElementById('report-box');
    const content = document.getElementById('report-content');
    box.classList.remove('hidden');
    content.textContent = 'AI 正在基于作业数据生成班级报告...';
    const btn = document.getElementById('report-expand-btn');
    btn.textContent = '展开';
    content.classList.remove('max-h-none');
    content.classList.add('max-h-96');
    try {
      const resp = await fetch(`/api/teacher/classes/${encodeURIComponent(classId)}/report`);
      const data = await resp.json();
      if (!resp.ok) throw new Error(data.detail || ('HTTP ' + resp.status));
      content.innerHTML = mdSafe(data.report || '报告生成失败，AI 未返回有效内容，请稍后重试。');
      if (data.dashboard) renderTeacherDashboard(data.dashboard);
    } catch (e) {
      content.textContent = '报告生成失败：' + (e.message || e);
    }
  }

  // 报告展开/收起切换
  function toggleReportExpand() {
    const content = document.getElementById('report-content');
    const btn = document.getElementById('report-expand-btn');
    if (content.classList.contains('max-h-none')) {
      content.classList.remove('max-h-none');
      content.classList.add('max-h-96');
      btn.textContent = '展开';
    } else {
      content.classList.remove('max-h-96');
      content.classList.add('max-h-none');
      btn.textContent = '收起';
    }
  }

  // ---------- 窗口 resize ----------
  window.addEventListener('resize', () => {
    if (radarChart) radarChart.resize();
    if (heatmapChart) heatmapChart.resize();
    if (progressChart) progressChart.resize();
  });

  // 初始化：HTML 里已有欢迎卡片，这里只初始化右侧边栏/仪表盘
  setTimeout(() => {
    window.updateSidebar('chat');
    refreshDashboard();
  }, 300);

  // ---------- 右侧动态仪表盘 ----------
  /** 答题后立即刷新右侧实时数据：只读浏览器本地，不发请求。 */
  function refreshLocalSideStats() {
    if (localStorage.getItem('cm_role') === 'teacher') return;
    const weakEl = document.getElementById('stat-weak');
    const stuEl = document.getElementById('stat-students');
    const weak = getWeakPoints(0.6, 999).length;
    if (weakEl) { weakEl.textContent = weak || '暂无'; weakEl.classList.toggle('text-sm', !weak); }
    if (stuEl) { stuEl.textContent = '本地'; stuEl.classList.add('text-sm'); }
  }

  async function refreshDashboard() {
    try {
      const g = await fetch('/api/knowledge/graph').then(r => r.json()).catch(() => null);
      if (g) {
        document.getElementById('stat-nodes').textContent = g.nodes?.length ?? '—';
        document.getElementById('stat-edges').textContent = g.edges?.length ?? '—';
      }
      const role = localStorage.getItem('cm_role');
      if (role === 'teacher') {
        // 班级数据由 classroom 模块加载后缓存在 window.__teacherDashboard
        const d = window.__teacherDashboard;
        const stuEl = document.getElementById('stat-students');
        const weakEl = document.getElementById('stat-weak');
        if (d) {
          const total = d.class_summary?.total_students;
          if (stuEl) { stuEl.textContent = total ?? '暂无'; stuEl.classList.toggle('text-sm', !total); }
          const heatmap = d.heatmap || {};
          const weak = Object.values(heatmap).filter(h => h.avg < 0.6).length;
          if (weakEl) { weakEl.textContent = Object.keys(heatmap).length ? weak : '暂无'; weakEl.classList.toggle('text-sm', !Object.keys(heatmap).length); }
        } else {
          if (stuEl) { stuEl.textContent = '暂无'; stuEl.classList.add('text-sm'); }
          if (weakEl) { weakEl.textContent = '暂无'; weakEl.classList.add('text-sm'); }
        }
      } else {
        // 学生：显示本地薄弱点数量，不请求任何教师接口
        refreshLocalSideStats();
      }
    } catch (e) { console.warn('仪表盘数据加载失败:', e); }
  }
  setInterval(refreshDashboard, 30000);

  // ---------- 学情右侧栏：近 7 天进步曲线 ----------
  let progressChart = null;

  /** 近 7 天趋势完全由浏览器本地学情计算，无数据时显示空状态引导。 */
  function refreshProgressCurve() {
    const box = document.getElementById('progress-chart');
    const empty = document.getElementById('progress-empty');
    const sub = document.getElementById('progress-sub');
    if (!box || typeof echarts === 'undefined') return;
    const panel = document.getElementById('panel-teacher');
    if (panel && panel.classList.contains('hidden')) return;
    let trend = [];
    try { trend = getDailyTrend(7); } catch (e) { trend = []; }

    const hasData = trend.some(t => t.answered > 0);
    box.style.display = hasData ? '' : 'none';
    if (empty) empty.classList.toggle('hidden', hasData);
    if (!hasData) {
      if (sub) sub.textContent = '暂无数据';
      return;
    }
    if (!progressChart) progressChart = echarts.init(box);
    const labels = trend.map(t => t.label);
    const mastery = trend.map(t => Math.round((t.mastery || 0) * 100));
    const answered = trend.map(t => t.answered || 0);
    progressChart.setOption({
      backgroundColor: 'transparent',
      grid: { left: 34, right: 10, top: 18, bottom: 22 },
      tooltip: { trigger: 'axis', ...CHART_TOOLTIP },
      xAxis: { type: 'category', data: labels, axisLine: { lineStyle: { color: CHART.line } }, axisTick: { show: false }, axisLabel: { color: CHART.faint, fontSize: 10 } },
      yAxis: { type: 'value', max: 100, min: 0, splitLine: { lineStyle: { color: CHART.line } }, axisLabel: { color: CHART.faint, fontSize: 10, formatter: '{value}%' } },
      series: [
        { name: '平均掌握度', type: 'line', smooth: true, data: mastery, symbolSize: 4,
          lineStyle: { width: 1.5, color: CHART.accent }, itemStyle: { color: CHART.accent },
          areaStyle: { color: 'rgba(168,68,46,0.08)' } },
        { name: '答题数', type: 'bar', data: answered, barWidth: 6, itemStyle: { color: 'rgba(62,92,118,0.30)', borderRadius: [2, 2, 0, 0] } },
      ],
    });
    progressChart.resize();
    const total = trend.reduce((s, t) => s + (t.answered || 0), 0);
    if (sub) sub.textContent = `近 7 天 ${total} 题`;
  }

// 导出 + 供 HTML 内联 onclick 使用
export { loadTeacher, refreshDashboard, refreshLocalSideStats, generateReport, toggleReportExpand, refreshProgressCurve, refreshPersonalRadar, renderStudentPersonalView, renderTeacherDashboard };
Object.assign(window, { loadTeacher, refreshDashboard, refreshLocalSideStats, generateReport, toggleReportExpand, refreshProgressCurve, refreshPersonalRadar, renderStudentPersonalView, renderTeacherDashboard });
