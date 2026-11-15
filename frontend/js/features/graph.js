/**
 * @file 知识图谱力导向可视化与节点检索定位
 * @module features/graph
 */
import { API, currentStudentId } from '../core/env.js';

  // ---------- 知识图谱可视化（力导向布局） ----------
  let graphData = null;
  let graphDragState = null;    // 当前拖拽的节点及渲染引用
  let graphJustDragged = false; // 拖拽后抑制误触发节点点击
  // 图谱增强：缩放 / 分类筛选 / hover 数据联动
  let graphNodeEls = {};        // id -> {circle, text, bg, category}
  let graphEdgeEls = [];        // [{source, target, line}]
  let graphDegree = {};         // id -> 连接度
  let graphHiddenCats = new Set();
  let graphMastery = {};        // id -> 掌握度
  let graphWrong = {};          // id -> 错题次数
  let graphPrereq = {};         // id -> [前置节点名]
  let graphZoom = 1;

  /** 拉取图谱 hover 需要的联动数据（掌握度 + 错题次数），失败不影响渲染 */
  async function loadGraphMeta() {
    const sid = currentStudentId();
    try {
      graphMastery = await fetch(API + '/bkt/mastery-map/' + encodeURIComponent(sid)).then(r => r.json());
    } catch (e) { graphMastery = {}; }
    try {
      graphWrong = await fetch(API + '/wrongbook/counts/' + encodeURIComponent(sid)).then(r => r.json());
    } catch (e) { graphWrong = {}; }
  }

  async function loadGraph() {
    const statsEl = document.getElementById('graph-stats');
    const loader = document.getElementById('graph-loader');
    const svg = document.getElementById('graph-svg');
    statsEl.textContent = '加载中...';
    // 显示 loader
    loader.classList.remove('hidden');
    try {
      const resp = await fetch(API + '/knowledge/graph');
      graphData = await resp.json();
      statsEl.textContent = `共 ${graphData.nodes.length} 节点 · ${graphData.edges.length} 边`;
      await loadGraphMeta();
      rebuildPrereq();
      renderGraph(graphData);
    } catch(e) { statsEl.textContent = '加载失败: ' + e.message; }
    finally {
      loader.classList.add('hidden');
    }
  }

  // 6 类节点颜色 —— 鲜艳饱和色 + hover 高亮用
  const categoryColors = {
    chapter:    '#818cf8', // 章节 —— 亮紫
    structure:  '#c084fc', // 数据结构 —— 亮玫紫
    algorithm:  '#34d399', // 算法 —— 亮翡翠
    operation:  '#fbbf24', // 操作 —— 亮琥珀
    paradigm:   '#fb7185', // 范式 —— 亮玫红
    concept:    '#38bdf8', // 概念 —— 亮天蓝
  };
  // 同类型高亮用的辉光颜色（与 categoryColors 同色系但更亮）
  const categoryGlow = {
    chapter:    'rgba(129,140,248,0.9)',
    structure:  'rgba(192,132,252,0.9)',
    algorithm:  'rgba(52,211,153,0.9)',
    operation:  'rgba(251,191,36,0.9)',
    paradigm:   'rgba(251,113,133,0.9)',
    concept:    'rgba(56,189,248,0.9)',
  };

  /**
   * 力导向布局渲染知识图谱（边 → 圆 → 标签 三层，避免标签被节点遮挡）。
   * @param {{nodes: Array<{id:string,name?:string,category?:string}>, edges: Array<{source:string,target:string}>}} data
   * @returns {void}
   */
  function renderGraph(data) {
    const svg = document.getElementById('graph-svg');
    const width = svg.clientWidth || 900;
    // 用实际渲染高度，避免布局按 600px 计算导致底部节点被容器裁掉
    const height = svg.clientHeight || 600;
    svg.innerHTML = '';

    // 为每个节点分配位置（圆形布局 + 轻微随机偏移）
    const nodes = data.nodes.map(n => {
      const angle = Math.random() * Math.PI * 2;
      const radius = 180 + Math.random() * 60;
      return {
        id: n.id, name: n.name || n.id, category: n.category || 'concept',
        x: width/2 + Math.cos(angle) * radius,
        y: height/2 + Math.sin(angle) * radius,
        vx: 0, vy: 0, r: 7,
      };
    });
    const nodeMap = Object.fromEntries(nodes.map(n => [n.id, n]));
    const edges = data.edges
      .map(e => ({source: e.source, target: e.target}))
      .filter(e => nodeMap[e.source] && nodeMap[e.target]);

    // 连接度 → 节点半径（枢纽节点更大）
    const degree = {};
    for (const e of edges) {
      degree[e.source] = (degree[e.source] || 0) + 1;
      degree[e.target] = (degree[e.target] || 0) + 1;
    }
    for (const n of nodes) n.r = 6 + Math.min(9, (degree[n.id] || 0) * 1.1);

    // 力导向模拟（斥力 + 弹簧 + 中心引力，180 次迭代）
    for (let iter = 0; iter < 180; iter++) {
      const cooling = 1 - iter / 200;  // 逐步冷却防震荡
      // 排斥力（库仑斥力，距离截断避免无限大）
      for (let i = 0; i < nodes.length; i++) {
        for (let j = i + 1; j < nodes.length; j++) {
          const a = nodes[i], b = nodes[j];
          let dx = a.x - b.x, dy = a.y - b.y;
          let dist = Math.sqrt(dx*dx + dy*dy) || 1;
          if (dist < 1) { dx = Math.random() - 0.5; dy = Math.random() - 0.5; dist = 1; }
          const force = Math.min(3000 / (dist * dist), 2.5);
          a.vx += dx/dist * force * cooling; a.vy += dy/dist * force * cooling;
          b.vx -= dx/dist * force * cooling; b.vy -= dy/dist * force * cooling;
        }
      }
      // 弹簧引力（边）
      for (const e of edges) {
        const a = nodeMap[e.source], b = nodeMap[e.target];
        const dx = b.x - a.x, dy = b.y - a.y;
        const dist = Math.sqrt(dx*dx + dy*dy) || 1;
        const rest = 118 + a.r + b.r;
        const force = (dist - rest) * 0.02;
        a.vx += dx/dist * force; a.vy += dy/dist * force;
        b.vx -= dx/dist * force; b.vy -= dy/dist * force;
      }
      // 中心引力（弱） + 阻尼 + 应用
      const cx = width/2, cy = height/2;
      for (const n of nodes) {
        n.vx += (cx - n.x) * 0.003;
        n.vy += (cy - n.y) * 0.003;
        n.vx *= 0.82; n.vy *= 0.82;
        n.x += n.vx; n.y += n.vy;
      }
    }
    // 碰撞分离：保证节点 + 标签互不重叠
    for (let pass = 0; pass < 60; pass++) {
      for (let i = 0; i < nodes.length; i++) {
        for (let j = i + 1; j < nodes.length; j++) {
          const a = nodes[i], b = nodes[j];
          const minDist = a.r + b.r + 26;
          let dx = a.x - b.x, dy = a.y - b.y;
          let dist = Math.sqrt(dx*dx + dy*dy) || 0.01;
          if (dist < minDist) {
            const push = (minDist - dist) / 2;
            const ux = dx/dist, uy = dy/dist;
            a.x += ux * push; a.y += uy * push;
            b.x -= ux * push; b.y -= uy * push;
          }
        }
      }
    }
    // 标签避让交给渲染阶段的智能选位处理，这里只做边界收缩
    for (const n of nodes) {
      n.x = Math.max(34, Math.min(width - 34, n.x));
      n.y = Math.max(30, Math.min(height - n.r - 32, n.y));
    }

    // 渲染边
    const edgeEls = [];
    for (const e of edges) {
      const a = nodeMap[e.source], b = nodeMap[e.target];
      const line = document.createElementNS('http://www.w3.org/2000/svg', 'line');
      line.setAttribute('x1', a.x); line.setAttribute('y1', a.y);
      line.setAttribute('x2', b.x); line.setAttribute('y2', b.y);
      line.setAttribute('class', 'graph-edge');
      svg.appendChild(line);
      edgeEls.push({...e, line});
    }
    // 渲染节点：分两层绘制 —— 先画全部圆形，再统一画全部标签
    // 这样任何节点的圆都不会盖住其他节点的文字
    const nodeEls = {};
    const catLabels = {chapter:'章节', structure:'数据结构', algorithm:'算法', operation:'操作', paradigm:'范式', concept:'概念'};

    // ---- 第一层：圆形节点 ----
    for (const n of nodes) {
      const color = categoryColors[n.category] || '#6366f1';
      const circle = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
      circle.setAttribute('cx', n.x); circle.setAttribute('cy', n.y);
      circle.setAttribute('r', n.r);
      circle.setAttribute('fill', color);
      circle.setAttribute('stroke', 'rgba(255,255,255,0.35)');
      circle.setAttribute('stroke-width', 1.5);
      circle.setAttribute('class', 'graph-node');
      circle.setAttribute('data-id', n.id);
      circle.setAttribute('data-name', n.name);
      circle.setAttribute('data-category', n.category);
      // 原生 SVG tooltip（hover 显示类型和连接度）
      const deg = degree[n.id] || 0;
      circle.innerHTML = `<title>📌 ${n.name}\n📂 类型：${catLabels[n.category]||n.category}\n🔗 连接度：${deg}（前置/后继）</title>`;
      circle.onmouseenter = (ev) => {
        circle.style.filter = `brightness(1.25) drop-shadow(0 0 6px ${categoryGlow[n.category]})`;
        // 同类型节点同步变亮（群体高亮）
        Object.values(nodeEls).forEach(ne => {
          if (ne.circle && ne.circle.dataset.category === n.category) {
            ne.circle.style.filter = `brightness(1.2) drop-shadow(0 0 4px ${categoryGlow[n.category]})`;
            ne.circle.style.opacity = '1';
          } else if (ne.circle) {
            ne.circle.style.opacity = '0.35';
          }
        });
        showGraphTooltip(ev, n, deg, catLabels);
      };
      circle.onmousemove = (ev) => showGraphTooltip(ev, n, deg, catLabels);
      circle.onmouseleave = () => {
        circle.style.filter = '';
        Object.values(nodeEls).forEach(ne => {
          if (ne.circle) { ne.circle.style.filter = ''; ne.circle.style.opacity = '1'; }
        });
        hideGraphTooltip();
      };
      circle.onclick = () => {
        if (graphJustDragged) { graphJustDragged = false; return; }
        window.sendQuick(n.name);
      };
      svg.appendChild(circle);
      nodeEls[n.id] = {circle, text: null, category: n.category};

      // ---- 拖拽交互 ----
      circle.addEventListener('pointerdown', (ev) => {
        ev.preventDefault(); ev.stopPropagation();
        graphDragState = {node: n, svg, width, height, nodeEls, edgeEls, nodeMap};
      });
      circle.addEventListener('pointerenter', () => {
        circle.setAttribute('stroke', '#fff');
        circle.setAttribute('stroke-width', 2.5);
      });
      circle.addEventListener('pointerleave', () => {
        circle.setAttribute('stroke', 'rgba(255,255,255,0.35)');
        circle.setAttribute('stroke-width', 1.5);
      });
    }

    // ---- 第二层：全部文字标签（永远在所有圆之上，自动避让 + 半透明底衬） ----
    const placed = [];
    // 连接度高的节点优先选位，重要标签优先获得最佳位置
    const labelOrder = [...nodes].sort((a, b) => (degree[b.id] || 0) - (degree[a.id] || 0));

    for (const n of labelOrder) {
      const label = n.name.length > 10 ? n.name.slice(0, 10) + '…' : n.name;
      const w = label.length * 11 + 8;
      const h = 15;
      // 8 个候选方位：下/上/右/左 + 四个对角
      const cands = [
        { x: n.x - w / 2, y: n.y + n.r + 4 },
        { x: n.x - w / 2, y: n.y - n.r - 4 - h },
        { x: n.x + n.r + 4, y: n.y - h / 2 },
        { x: n.x - n.r - 4 - w, y: n.y - h / 2 },
        { x: n.x + n.r * 0.7 + 2, y: n.y + n.r * 0.7 + 2 },
        { x: n.x - n.r * 0.7 - 2 - w, y: n.y + n.r * 0.7 + 2 },
        { x: n.x + n.r * 0.7 + 2, y: n.y - n.r * 0.7 - 2 - h },
        { x: n.x - n.r * 0.7 - 2 - w, y: n.y - n.r * 0.7 - 2 - h },
      ];
      const overlapArea = (a, b) => {
        const ox = Math.min(a.x + a.w, b.x + b.w) - Math.max(a.x, b.x);
        const oy = Math.min(a.y + a.h, b.y + b.h) - Math.max(a.y, b.y);
        return ox > 0 && oy > 0 ? ox * oy : 0;
      };
      // 逐候选计算惩罚分，取重叠最少的位置（而不是硬塞第一个）
      let box = cands[0], bestPenalty = Infinity;
      for (const c of cands) {
        const rr = { ...c, w, h };
        let penalty = 0;
        // 越界惩罚
        penalty += (Math.max(0, 2 - c.x) + Math.max(0, c.x + w - (width - 2))) * 400;
        penalty += (Math.max(0, 2 - c.y) + Math.max(0, c.y + h - (height - 2))) * 400;
        // 与其他已放置标签的重叠面积
        for (const p of placed) penalty += overlapArea(rr, p) * 3;
        // 与其他节点圆的重叠
        for (const o of nodes) {
          if (o === n) continue;
          const nx = Math.max(c.x, Math.min(o.x, c.x + w));
          const ny = Math.max(c.y, Math.min(o.y, c.y + h));
          const ddx = o.x - nx, ddy = o.y - ny;
          if (ddx * ddx + ddy * ddy < (o.r + 1) * (o.r + 1)) penalty += 300;
        }
        if (penalty < bestPenalty) { bestPenalty = penalty; box = c; }
        if (penalty === 0) break;
      }
      placed.push({ ...box, w, h });

      // 半透明底衬：即使节点密集，文字也清晰可读
      const bg = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
      bg.setAttribute('x', box.x); bg.setAttribute('y', box.y);
      bg.setAttribute('width', w); bg.setAttribute('height', h);
      bg.setAttribute('rx', 4);
      bg.setAttribute('fill', 'rgba(15,23,42,0.8)');
      bg.setAttribute('stroke', 'rgba(99,102,241,0.25)');
      bg.setAttribute('stroke-width', 0.8);
      bg.setAttribute('class', 'graph-label-bg');
      svg.appendChild(bg);

      const text = document.createElementNS('http://www.w3.org/2000/svg', 'text');
      text.setAttribute('x', box.x + w / 2);
      text.setAttribute('y', box.y + h / 2 + 4);
      text.setAttribute('class', 'graph-node label');
      text.setAttribute('text-anchor', 'middle');
      text.textContent = label;
      svg.appendChild(text);
      nodeEls[n.id].text = text;
      nodeEls[n.id].bg = bg;
    }


    // 全局拖拽监听（只挂载一次）
    if (!svg._dragInit) {
      svg._dragInit = true;
      svg.addEventListener('pointermove', (ev) => {
        if (!graphDragState) return;
        const st = graphDragState, n = st.node;
        const pt = st.svg.createSVGPoint();
        pt.x = ev.clientX; pt.y = ev.clientY;
        const p = pt.matrixTransform(st.svg.getScreenCTM().inverse());
        if (Math.abs(p.x - n.x) > 1 || Math.abs(p.y - n.y) > 1) graphJustDragged = true;
        n.x = Math.max(34, Math.min(st.width - 34, p.x));
        n.y = Math.max(30, Math.min(st.height - 46, p.y));
        const els = st.nodeEls[n.id];
        els.circle.setAttribute('cx', n.x); els.circle.setAttribute('cy', n.y);
        // 拖拽时标签固定在节点下方，底衬同步移动
        const tw = els.text.textContent.length * 11 + 8;
        els.text.setAttribute('x', n.x);
        els.text.setAttribute('y', n.y + n.r + 15.5);
        if (els.bg) {
          els.bg.setAttribute('x', n.x - tw / 2);
          els.bg.setAttribute('y', n.y + n.r + 4);
          els.bg.setAttribute('width', tw);
        }
        for (const e of st.edgeEls) {
          const a = st.nodeMap[e.source], b = st.nodeMap[e.target];
          if (e.source === n.id) { e.line.setAttribute('x1', a.x); e.line.setAttribute('y1', a.y); }
          if (e.target === n.id) { e.line.setAttribute('x2', b.x); e.line.setAttribute('y2', b.y); }
        }
      });
      svg.addEventListener('pointerup', () => { graphDragState = null; });
      svg.addEventListener('pointerleave', () => { graphDragState = null; });
    }

    // 暴露渲染结果给筛选 / 缩放 / hover 模块
    graphNodeEls = nodeEls;
    graphEdgeEls = edgeEls;
    graphDegree = degree;
    initGraphZoom(svg, width, height);
    applyGraphFilter();
    applyLabelDensity();
  }

  /** 从边关系推导每个节点的前置知识点（边的 source → target） */
  function rebuildPrereq() {
    if (!graphData) return;
    const byId = Object.fromEntries((graphData.nodes || []).map(n => [n.id, n.name || n.id]));
    graphPrereq = {};
    for (const e of (graphData.edges || [])) {
      (graphPrereq[e.target] = graphPrereq[e.target] || []).push(byId[e.source] || e.source);
    }
  }

  /** 分类筛选：点击图例隐藏 / 显示某一类节点（连带隐藏其边） */
  function toggleGraphCategory(cat) {
    if (graphHiddenCats.has(cat)) graphHiddenCats.delete(cat);
    else graphHiddenCats.add(cat);
    applyGraphFilter();
  }

  function resetGraphFilter() {
    graphHiddenCats.clear();
    applyGraphFilter();
  }

  function applyGraphFilter() {
    for (const [id, els] of Object.entries(graphNodeEls)) {
      const hidden = graphHiddenCats.has(els.category);
      const disp = hidden ? 'none' : '';
      if (els.circle) els.circle.style.display = disp;
      if (els.text) els.text.style.display = disp;
      if (els.bg) els.bg.style.display = disp;
    }
    for (const e of graphEdgeEls) {
      const a = graphNodeEls[e.source], b = graphNodeEls[e.target];
      const hidden = (a && graphHiddenCats.has(a.category)) || (b && graphHiddenCats.has(b.category));
      if (e.line) e.line.style.display = hidden ? 'none' : '';
    }
    document.querySelectorAll('.legend-item').forEach(el => {
      const off = graphHiddenCats.has(el.dataset.cat);
      el.style.opacity = off ? '0.35' : '1';
      el.style.textDecoration = off ? 'line-through' : '';
    });
  }

  /** 缩小视图只保留高权重（连接度高）节点标签，放大后全部展示 */
  function applyLabelDensity() {
    const entries = Object.entries(graphNodeEls);
    if (!entries.length) return;
    const sorted = entries.slice().sort((a, b) => (graphDegree[b[0]] || 0) - (graphDegree[a[0]] || 0));
    const limit = graphZoom < 0.9 ? 10 : graphZoom < 1.3 ? 22 : graphZoom < 1.8 ? 40 : sorted.length;
    const keep = new Set(sorted.slice(0, limit).map(x => x[0]));
    for (const [id, els] of entries) {
      if (!els.text) continue;
      const show = keep.has(id);
      els.text.style.display = show ? '' : 'none';
      if (els.bg) els.bg.style.display = show ? '' : 'none';
    }
    // 被分类筛选隐藏的节点保持隐藏
    if (graphHiddenCats.size) applyGraphFilter();
  }

  /** 滚轮缩放（以鼠标位置为中心），viewBox 越大=越缩小 */
  function initGraphZoom(svg, width, height) {
    if (svg._zoomInit) return;
    svg._zoomInit = true;
    svg.addEventListener('wheel', (ev) => {
      ev.preventDefault();
      const rect = svg.getBoundingClientRect();
      const vb = (svg.getAttribute('viewBox') || `0 0 ${width} ${height}`).split(/\s+/).map(Number);
      let [x, y, w, h] = vb;
      const factor = ev.deltaY > 0 ? 1.15 : 0.87;
      const nw = w * factor;
      const minW = width / 4, maxW = width * 1.5;
      if (nw < minW || nw > maxW) return;
      const mx = x + ((ev.clientX - rect.left) / rect.width) * w;
      const my = y + ((ev.clientY - rect.top) / rect.height) * h;
      const ratio = nw / w;
      x = mx - (mx - x) * ratio;
      y = my - (my - y) * ratio;
      h = h * ratio;
      svg.setAttribute('viewBox', `${x} ${y} ${nw} ${h}`);
      graphZoom = width / nw;
      applyLabelDensity();
    }, { passive: false });
  }

  /** hover 浮层：掌握度 + 前置知识点 + 错题次数 / 连接度 */
  function showGraphTooltip(ev, node, deg, catLabels) {
    const tip = document.getElementById('graph-tooltip');
    const panel = document.getElementById('panel-graph');
    if (!tip || !panel) return;
    const score = graphMastery[node.id];
    const mastery = (score === undefined || score === null)
      ? '<span class="text-slate-500">未练习</span>'
      : `<span class="${score >= 0.6 ? 'text-emerald-300' : 'text-rose-300'} font-semibold">${Math.round(score * 100)}%</span>`;
    const wrong = graphWrong[node.id] || 0;
    const prereqs = (graphPrereq[node.id] || []).slice(0, 3);
    tip.innerHTML = `
      <div class="font-semibold text-slate-100 mb-1">${node.name}</div>
      <div class="text-slate-400 mb-1.5">${catLabels[node.category] || node.category} · 连接度 ${deg}</div>
      <div class="flex items-center justify-between gap-3"><span class="text-slate-400">BKT 掌握度</span>${mastery}</div>
      <div class="flex items-center justify-between gap-3"><span class="text-slate-400">累计错题</span><span class="${wrong ? 'text-rose-300' : 'text-slate-500'}">${wrong ? wrong + ' 次' : '0 次'}</span></div>
      <div class="mt-1 text-slate-400">前置：${prereqs.length ? prereqs.join('、') : '<span class="text-slate-600">无</span>'}</div>
      <div class="mt-1.5 text-[10px] text-indigo-300/80">点击 → 让 AI 讲解</div>`;
    tip.classList.remove('hidden');
    const r = panel.getBoundingClientRect();
    const left = Math.min(ev.clientX - r.left + 14, r.width - 250);
    const top = Math.max(8, Math.min(ev.clientY - r.top + 14, r.height - 150));
    tip.style.left = left + 'px';
    tip.style.top = top + 'px';
  }

  function hideGraphTooltip() {
    const tip = document.getElementById('graph-tooltip');
    if (tip) tip.classList.add('hidden');
  }

  // ---------- 图谱快速搜索 ----------
  async function graphQuickSearch(focusOnly) {
    const q = document.getElementById('quick-search').value.trim();
    const box = document.getElementById('search-results');
    if (!q) { box.classList.add('hidden'); return; }
    try {
      const resp = await fetch(API + '/knowledge/search?query=' + encodeURIComponent(q) + '&top_k=8');
      const nodes = await resp.json();
      if (!nodes.length) { box.innerHTML = '<div class="text-xs text-slate-500 p-2">❌ 未找到匹配节点</div>'; box.classList.remove('hidden'); return; }
      const catLabel = {chapter:'章节', structure:'数据结构', algorithm:'算法', operation:'操作', paradigm:'范式', concept:'概念'};
      box.innerHTML = nodes.map(n => `
        <div class="group p-1.5 rounded hover:bg-slate-700/50 text-xs flex items-center gap-2 transition border border-transparent hover:border-indigo-500/30 cursor-pointer"
             onclick="sendQuick('${n.name}是什么？')">
          <span class="w-2 h-2 rounded-full flex-shrink-0" style="background:${categoryColors[n.category]||'#6366f1'}"></span>
          <span class="flex-1 truncate text-slate-200">${highlightMatch(n.name, '${q}')}</span>
          <span class="text-slate-500 text-[10px]">${catLabel[n.category]||n.category}</span>
          <button onclick="event.stopPropagation();focusGraphNode('${n.id}')" title="在图谱中定位"
            class="opacity-0 group-hover:opacity-100 transition px-1.5 py-0.5 rounded bg-indigo-500/20 text-indigo-300 hover:bg-indigo-500/40 text-[10px] border border-indigo-500/30">🎯</button>
          <button onclick="event.stopPropagation();sendQuick('${n.name}是什么？')" title="向 AI 提问"
            class="opacity-0 group-hover:opacity-100 transition px-1.5 py-0.5 rounded bg-slate-600/40 text-slate-300 hover:bg-slate-600 text-[10px]">💬</button>
        </div>
      `).join('');
      box.classList.remove('hidden');
      // 如果是回车搜索 + 只有 1 条结果 → 直接在图谱中定位
      if (focusOnly && nodes.length === 1) focusGraphNode(nodes[0].id);
    } catch(e) {}
  }

  // 高亮搜索匹配字符（大小写不敏感）
  function highlightMatch(text, q) {
    if (!q) return text;
    const re = new RegExp('(' + q.replace(/[.*+?^${}()|[\]\\]/g, '\\$&') + ')', 'gi');
    return text.replace(re, '<mark style="background:rgba(99,102,241,0.4);color:#c7d2fe;padding:0 2px;border-radius:2px;">$1</mark>');
  }

  // 在图谱 Tab 定位节点（切换 Tab → 刷新图谱 → 用脉冲动画标记）
  /**
   * 切到图谱 Tab 并把视口定位到指定节点（3 秒黄色脉冲高亮）。
   * @param {string} nodeId - 图谱节点 ID
   * @returns {void}
   */
  function focusGraphNode(nodeId) {
    window.switchTab('graph');
    setTimeout(() => {
      const svg = document.getElementById('graph-svg');
      if (!svg) return;
      const node = svg.querySelector(`.graph-node[data-id="${nodeId}"]`);
      if (node) {
        node.style.filter = 'drop-shadow(0 0 8px #fbbf24)';
        node.style.transition = 'filter 0.5s';
        try {
          const pt = svg.createSVGPoint();
          pt.x = parseFloat(node.getAttribute('cx')) || 0;
          pt.y = parseFloat(node.getAttribute('cy')) || 0;
          const matrix = svg.getScreenCTM().inverse();
          svg.setAttribute('viewBox', `${pt.x - 300} ${pt.y - 200} 600 400`);
          graphZoom = (svg.clientWidth || 900) / 600;
          applyLabelDensity();
        } catch(_) {}
        setTimeout(() => { node.style.filter = ''; }, 3000);
      } else {
        loadGraph().then(() => setTimeout(() => focusGraphNode(nodeId), 800));
      }
    }, 500);
  }

// 导出 + 供 HTML 内联 onclick 使用
export { loadGraph, renderGraph, graphQuickSearch, focusGraphNode, toggleGraphCategory, resetGraphFilter };
Object.assign(window, { loadGraph, renderGraph, graphQuickSearch, focusGraphNode, toggleGraphCategory, resetGraphFilter, hideGraphTooltip });
