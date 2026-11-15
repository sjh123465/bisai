/**
 * @file 学情仪表盘（教师班级视图 / 学生个人视图 / 雷达图 / 热力图 / AI 报告）
 * @module features/analytics
 */
import { API, currentStudentId } from '../core/env.js';
import { mdSafe } from '../core/render.js';

    // 如果图谱已加载过，直接高亮；否则等加载完
      // 先尝试点击/定位已渲染节点
        // 滚动视图定位（用 viewBox）
        // 没找到就刷新图谱再试

  // ---------- 学情仪表盘 ----------
  let radarChart, heatmapChart;
  /**
   * 加载学情 Tab：按登录角色渲染班级视图（教师）或个人视图（学生）。
   * @returns {Promise<void>}
   */
  async function loadTeacher() {
    const isTeacher = localStorage.getItem('cm_role') === 'teacher';
    let classHeatmap = {};

    // 热力图 + 高频错题榜（教师专属）
    try {
      const resp = await fetch(API + '/teacher/dashboard');
      if (resp.status === 403) {
        renderHeatmap({});
        renderWrongRanking([]);
        let hint = document.getElementById('heatmap-hint');
        if (!hint) {
          const el = document.getElementById('heatmap-chart');
          hint = document.createElement('p');
          hint.id = 'heatmap-hint';
          hint.className = 'text-xs text-amber-400/80 p-2';
          hint.textContent = '🔒 班级热力图为教师专属，使用 teacher 账号登录后可见';
          el.parentElement.insertBefore(hint, el);
        }
      } else {
        const dash = await resp.json();
        classHeatmap = dash.heatmap || {};
        renderHeatmap(classHeatmap);
        renderWrongRanking(dash.wrong_ranking || []);
      }
    } catch(e) {
      renderHeatmap({});
      renderWrongRanking([]);
    }

    // 雷达图：教师看班级平均掌握度，学生看个人掌握度
    const radarTitle = document.getElementById('radar-title');
    if (isTeacher && Object.keys(classHeatmap).length > 0) {
      radarTitle.textContent = '👥 班级平均掌握度雷达';
      const classAvg = {};
      Object.entries(classHeatmap).forEach(([name, info]) => {
        classAvg[name] = info.avg || 0.3;
      });
      renderRadar(classAvg);
    } else {
      radarTitle.textContent = '👤 个人掌握度雷达';
      try {
        const resp = await fetch(API + '/bkt/mastery/' + encodeURIComponent(currentStudentId()));
        const mastery = await resp.json();
        renderRadar(mastery);
      } catch(e) {
        const sample = {'红黑树': 0.85, '快速排序': 0.72, '图论': 0.40, '动态规划': 0.55, '链表': 0.92, '二叉树': 0.68, '最短路径': 0.38};
        renderRadar(sample);
      }
    }

    // 学生列表（教师专属）
    try {
      const sr = await fetch(API + '/teacher/students');
      if (sr.status === 403) {
        renderStudentList([], true);
      } else {
        const sd = await sr.json();
        renderStudentList(sd.students || []);
      }
    } catch(e) {
      renderStudentList([]);
    }
  }

  function renderStudentList(students, forbidden = false) {
    const el = document.getElementById('student-list');
    if (forbidden) {
      el.innerHTML = '<p class="text-xs text-amber-400/80">🔒 学生学情列表为教师专属功能，请用 teacher 账号登录</p>';
      return;
    }
    if (students.length === 0) {
      el.innerHTML = '<p class="text-xs text-slate-500">暂无学生数据 — 学生答题后自动出现</p>';
      return;
    }
    el.innerHTML = students.map((s, idx) => {
      const pct = Math.round(s.avg_mastery * 100);
      const color = pct < 40 ? 'text-rose-400' : pct < 70 ? 'text-amber-400' : 'text-emerald-400';
      const barFrom = pct < 40 ? 'from-rose-500' : pct < 70 ? 'from-amber-500' : 'from-emerald-500';
      const barTo = pct < 40 ? 'to-red-500' : pct < 70 ? 'to-orange-500' : 'to-teal-500';
      return `
        <div class="student-row group p-2.5 rounded-lg bg-slate-800/40 hover:bg-slate-700/50 cursor-pointer transition border border-slate-700/30 hover:border-indigo-500/30"
             onclick="toggleStudentRow(this, '${s.student_id}')">
          <div class="flex items-center gap-3">
            <span class="text-[10px] w-5 h-5 rounded-full bg-slate-700/50 text-slate-400 flex items-center justify-center flex-shrink-0 group-hover:bg-indigo-500/20 group-hover:text-indigo-300 transition">${idx+1}</span>
            <span class="text-sm text-slate-200 w-24 truncate flex-1">${s.student_id}</span>
            <div class="w-28 h-1.5 bg-slate-700/50 rounded-full overflow-hidden">
              <div class="h-full bg-gradient-to-r ${barFrom} ${barTo} rounded-full transition-all duration-500" style="width:${pct}%"></div>
            </div>
            <span class="text-xs ${color} w-10 text-right font-medium">${pct}%</span>
            <span class="text-[10px] text-slate-500 w-20 text-right">薄弱${s.weak_count} · 错题${s.total_wrong}</span>
            <span class="text-slate-500 text-xs group-hover:text-indigo-400 transition flex-shrink-0 arrow">▶</span>
          </div>
          <div class="student-detail hidden mt-3 pt-3 border-t border-slate-700/40">
            <div class="grid grid-cols-1 md:grid-cols-2 gap-3">
              <div class="h-40">
                <div class="text-[10px] text-slate-500 mb-1">📊 掌握度雷达</div>
                <div class="inline-radar" data-student="${s.student_id}" style="width:100%; height:140px;"></div>
              </div>
              <div class="text-xs">
                <div class="text-[10px] text-slate-500 mb-1">⚠️ 薄弱知识点</div>
                <div class="inline-weak text-slate-300" data-student="${s.student_id}">加载中...</div>
              </div>
            </div>
          </div>
        </div>
      `;
    }).join('');
  }

  // 学生列表行展开/收起
  function toggleStudentRow(row, studentId) {
    const detail = row.querySelector('.student-detail');
    const arrow = row.querySelector('.arrow');
    const isHidden = detail.classList.contains('hidden');
    if (isHidden) {
      detail.classList.remove('hidden');
      arrow.textContent = '▼';
      // 内联渲染雷达图 + 薄弱知识点
      loadInlineStudentDetail(row, studentId);
    } else {
      detail.classList.add('hidden');
      arrow.textContent = '▶';
    }
  }

  // 学生行内联展开：小雷达图 + 薄弱知识点列表
  async function loadInlineStudentDetail(row, studentId) {
    const radarBox = row.querySelector('.inline-radar');
    const weakBox = row.querySelector('.inline-weak');
    if (!radarBox || radarBox.dataset.loaded) return;
    radarBox.dataset.loaded = '1';
    try {
      const r = await fetch(API + '/teacher/student/' + studentId);
      const data = await r.json();
      const bkt = data.bkt || {};
      const items = Object.entries(bkt);
      // 雷达图（最多 6 个概念）
      const radarItems = items.slice(0, 6);
      const chart = echarts.init(radarBox);
      chart.setOption({
        tooltip: { trigger: 'item' },
        radar: {
          indicator: radarItems.map(([k]) => ({ name: k.slice(0, 6), max: 1 })),
          center: ['50%', '55%'], radius: '60%',
          splitLine: { lineStyle: { color: 'rgba(100,116,139,0.3)' } },
          axisLine: { lineStyle: { color: 'rgba(100,116,139,0.3)' } },
          axisName: { color: '#94a3b8', fontSize: 10 },
          splitArea: { show: false },
        },
        series: [{
          type: 'radar',
          data: [{ value: radarItems.map(([, v]) => v), areaStyle: { color: 'rgba(99,102,241,0.35)' }, lineStyle: { color: '#818cf8' }, itemStyle: { color: '#818cf8' } }],
        }],
        animationDuration: 400,
      });
      // 薄弱知识点（掌握度 < 0.6）
      const weak = items.filter(([, v]) => v < 0.6).sort((a, b) => a[1] - b[1]);
      if (weak.length === 0) {
        weakBox.innerHTML = '<span class="text-emerald-400 text-xs">🎉 暂无明显薄弱点</span>';
      } else {
        weakBox.innerHTML = weak.slice(0, 5).map(([k, v]) => {
          const pct = Math.round(v * 100);
          const rgb = pct < 40 ? '244,63,94' : '251,191,36';
          return `<div class="flex items-center gap-2 mb-1.5">
            <span class="text-slate-300 truncate flex-1">${k}</span>
            <div class="w-14 h-1 rounded-full bg-slate-700 overflow-hidden"><div class="h-full" style="width:${pct}%; background:rgb(${rgb});"></div></div>
            <span class="text-[10px] text-slate-400 w-8 text-right">${pct}%</span>
          </div>`;
        }).join('');
      }
    } catch (e) {
      radarBox.innerHTML = '<div class="text-xs text-rose-400">加载失败</div>';
    }
  }

  async function loadStudentDetail(studentId) {
    try {
      const r = await fetch(API + '/teacher/student/' + studentId);
      const d = await r.json();
      document.getElementById('student-detail').classList.remove('hidden');

      // 雷达图
      const mastery = d.mastery || {};
      const names = Object.keys(mastery);
      const values = names.map(n => Math.round(mastery[n] * 100));
      const dom = document.getElementById('student-radar');
      if (names.length >= 3 && window.echarts) {
        const chart = echarts.init(dom, 'dark');
        chart.setOption({
          radar: { indicator: names.map(n => ({name: n, max: 100})), radius: '65%' },
          series: [{ type: 'radar', data: [{ value: values, name: studentId, areaStyle: {opacity: 0.3} }] }]
        });
      } else {
        dom.innerHTML = '<p class="text-xs text-slate-500">知识点少于3个，无法绘制雷达图</p>';
      }

      // 薄弱点
      const weak = d.weak_points || [];
      document.getElementById('student-weak').innerHTML = weak.length
        ? '⚠️ 薄弱知识点: ' + weak.map(w => `${w.concept_id}(${Math.round(w.mastery*100)}%)`).join('、')
        : '✅ 暂无明显薄弱知识点';
    } catch(e) { console.error(e); }
  }

  function renderWrongRanking(ranking) {
    const el = document.getElementById('wrong-ranking');
    if (!ranking || ranking.length === 0) {
      el.innerHTML = '<p class="text-xs text-slate-500">📕 暂无错题数据 — 学生在「练一练」答错题目后自动统计</p>';
      return;
    }
    const medals = ['🥇','🥈','🥉','4','5','6','7','8','9','10'];
    const medalColors = ['text-amber-400','text-slate-300','text-orange-400','text-slate-500','text-slate-500','text-slate-500','text-slate-500','text-slate-500','text-slate-500','text-slate-500'];
    const maxCount = ranking[0].wrong_count;
    const barColors = [
      'from-rose-500 to-red-500',
      'from-orange-500 to-rose-500',
      'from-amber-500 to-orange-500',
      'from-amber-400 to-yellow-500',
    ];
    el.innerHTML = ranking.map((item, i) => {
      const barCls = i < 3 ? barColors[i] : barColors[3];
      return `
      <div class="wrong-item group flex items-center gap-3 text-sm p-2 -mx-2 rounded-lg hover:bg-slate-800/40 transition">
        <span class="w-6 text-center font-bold ${medalColors[i] || 'text-slate-500'}">${medals[i] || (i+1)}</span>
        <div class="flex-1 min-w-0">
          <div class="flex justify-between items-center mb-1">
            <span class="text-slate-200 truncate">${item.concept_name || item.concept_id}</span>
            <div class="flex items-center gap-2 flex-shrink-0">
              <span class="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-medium bg-rose-500/20 text-rose-300 border border-rose-500/30">
                ❌ ${item.wrong_count}
              </span>
              <span class="text-[10px] text-slate-500">${item.student_count} 人</span>
            </div>
          </div>
          <div class="w-full h-2 bg-slate-700/50 rounded-full overflow-hidden">
            <div class="h-full bg-gradient-to-r ${barCls} rounded-full transition-all duration-500" style="width:${Math.max(8, item.wrong_count/maxCount*100)}%"></div>
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
      const keys = Object.keys(mastery).slice(0, 7);
      const values = keys.map(k => Math.round((mastery[k] || 0.3) * 100));
      radarChart.setOption({
        backgroundColor: 'transparent',
        tooltip: {trigger: 'item'},
        radar: {
          indicator: keys.map(k => ({name: k, max: 100})),
          axisName: {color: '#cbd5e1', fontSize: 11},
          splitLine: {lineStyle: {color: '#334155'}},
          splitArea: {areaStyle: {color: ['#1e293b', '#1e293b']}},
          axisLine: {lineStyle: {color: '#475569'}},
        },
        series: [{
          type: 'radar',
          data: [{value: values, name: '掌握度', areaStyle: {color: 'rgba(99,102,241,0.3)'}, lineStyle: {color: '#6366f1'}, itemStyle: {color: '#a5b4fc'}}],
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
          title: {text: '暂无答题数据 — 学生答题后自动更新', left: 'center', top: 'middle', textStyle: {color: '#64748b', fontSize: 13}},
        });
        return;
      }
      heatmapChart.setOption({
        backgroundColor: 'transparent',
        tooltip: {trigger: 'axis', axisPointer: {type: 'shadow'}},
        grid: {left: 140, right: 20, top: 10, bottom: 30},
        xAxis: {type: 'value', max: 100, axisLabel: {color: '#94a3b8', formatter: '{value}%'}, splitLine: {lineStyle: {color: '#334155'}}},
        yAxis: {type: 'category', data: items.map(i => i[0]), axisLabel: {color: '#e2e8f0', fontSize: 11}, axisLine: {lineStyle: {color: '#475569'}}},
        series: [{
          type: 'bar',
          data: items.map(i => ({value: Math.round(i[1].avg*100), itemStyle: {color: i[1].avg < 0.6 ? '#ef4444' : i[1].avg < 0.8 ? '#f59e0b' : '#10b981'}})),
          barWidth: 14,
        }],
      });
    });
  }

  async function generateReport() {
    const box = document.getElementById('report-box');
    const content = document.getElementById('report-content');
    box.classList.remove('hidden');
    content.textContent = '⏳ AI 正在生成学情报告...';
    // 重置展开按钮状态
    const btn = document.getElementById('report-expand-btn');
    btn.textContent = '展开 ▼';
    content.classList.remove('max-h-none');
    content.classList.add('max-h-96');
    try {
      const resp = await fetch(API + '/teacher/report');
      const data = await resp.json();
      const report = data.report || '⚠️ 报告生成失败，AI 未返回有效内容，请稍后重试。';
      content.innerHTML = mdSafe(report);
    } catch(e) { content.textContent = '❌ ' + e.message; }
  }

  // 报告展开/收起切换
  function toggleReportExpand() {
    const content = document.getElementById('report-content');
    const btn = document.getElementById('report-expand-btn');
    if (content.classList.contains('max-h-none')) {
      content.classList.remove('max-h-none');
      content.classList.add('max-h-96');
      btn.textContent = '展开 ▼';
    } else {
      content.classList.remove('max-h-96');
      content.classList.add('max-h-none');
      btn.textContent = '收起 ▲';
    }
  }

  // ---------- 窗口 resize ----------
  window.addEventListener('resize', () => {
    if (radarChart) radarChart.resize();
    if (heatmapChart) heatmapChart.resize();
  });

  // 初始化
  setTimeout(() => {
    // 精致欢迎语卡片（独立 HTML，不用 Markdown 流程）
    const chat = document.getElementById('chat-messages');
    const wc = document.createElement('div');
    wc.className = 'welcome-card';
    wc.innerHTML = `
      <div class="welcome-title">
        <div class="w-7 h-7 rounded-lg bg-gradient-to-br from-indigo-500 to-purple-600 flex items-center justify-center font-bold text-white text-xs">C</div>
        <span>你好！我是 CodeMentor 🤖</span>
        <span class="welcome-arrow" id="welcome-arrow">▼</span>
      </div>
      <div class="welcome-body collapsed" id="welcome-body">
        我可以帮你做这几件事：
        <ul>
          <li>📖 <b>理论问答</b> — 红黑树、动态规划、图论… 问就完事</li>
          <li>🐛 <b>代码调试</b> — 贴一段 Python，沙箱运行 + AST 分析死循环/嵌套/复杂度</li>
          <li>📝 <b>AI 出题 + 双轨批改</b> — 切「练一练」Tab，按知识点生成，沙箱跑 + LLM 解释</li>
          <li>🖼️ <b>截图答疑</b> — 报错界面、代码截图，Zhipu GLM-4V-Flash 视觉理解</li>
          <li>🎯 <b>BKT 知识追踪</b> — 每次答题后贝叶斯更新掌握概率，发现你的薄弱点</li>
          <li>🗺️ <b>图谱 62 节点 / 69 前置关系</b> — 点击节点直接提问，搜索快速定位</li>
        </ul>
      </div>
      <div class="welcome-toggle" id="welcome-toggle">▾ 展开更多能力</div>
    `;
    // 点击整张卡片或底部按钮都能切换
    const toggleWelcome = () => {
      const body = document.getElementById('welcome-body');
      const btn = document.getElementById('welcome-toggle');
      const expanded = body.classList.contains('expanded');
      if (expanded) {
        body.classList.remove('expanded'); body.classList.add('collapsed');
        wc.classList.remove('expanded');
        btn.textContent = '▾ 展开更多能力';
      } else {
        body.classList.remove('collapsed'); body.classList.add('expanded');
        wc.classList.add('expanded');
        btn.textContent = '▴ 收起';
      }
    };
    wc.onclick = (e) => {
      if (e.target.closest('.welcome-toggle') || e.target.closest('.welcome-title')) toggleWelcome();
    };
    chat.appendChild(wc);
    // 初始化右侧边栏（默认对话 Tab）
    window.updateSidebar('chat');
    // 加载右侧仪表盘
    refreshDashboard();
  }, 300);

  // ---------- 右侧动态仪表盘 ----------
  async function refreshDashboard() {
    try {
      const g = await fetch('/api/knowledge/graph').then(r => r.json()).catch(() => null);
      if (g) {
        document.getElementById('stat-nodes').textContent = g.nodes?.length ?? '-';
        document.getElementById('stat-edges').textContent = g.edges?.length ?? '-';
      }
      try {
        const t = await fetch('/api/teacher/dashboard');
        if (t.ok) {
          const d = await t.json();
          document.getElementById('stat-students').textContent = d.class_summary?.total_students ?? '-';
          const heatmap = d.heatmap || {};
          const weak = Object.values(heatmap).filter(h => h.avg < 0.6).length;
          document.getElementById('stat-weak').textContent = weak;
        }
      } catch (_) { /* 未登录时静默 */ }
    } catch (e) { console.warn('仪表盘数据加载失败:', e); }
  }
  setInterval(refreshDashboard, 30000);

// 导出 + 供 HTML 内联 onclick 使用
export { loadTeacher, refreshDashboard, generateReport, toggleStudentRow, toggleReportExpand };
Object.assign(window, { loadTeacher, refreshDashboard, generateReport, toggleStudentRow, toggleReportExpand });
