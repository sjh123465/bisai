# CodeMentor — 基于 Agent 与 GraphRAG 的计算机自适应助学平台

> 🧠 懂代码、🗺️ 知图谱、⚡ 能动手的 AI 编程导师 | 大赛参赛作品
>
> <p align="center"><img src="https://img.shields.io/badge/Python-3.11+-3776AB?logo=python&logoColor=white">
> <img src="https://img.shields.io/badge/FastAPI-0.115-009688?logo=fastapi&logoColor=white">
> <img src="https://img.shields.io/badge/Tests-39%2F39%20PASS-10b981?logo=pytest">
> <img src="https://img.shields.io/badge/Docker-支持-2496ED?logo=docker&logoColor=white">
> <img src="https://img.shields.io/badge/License-MIT-emerald.svg">
> <a href="https://gitee.com/shijh1216/CodeMentor"><img src="https://img.shields.io/badge/Gitee-ee5253?logo=gitee&logoColor=white&label=Gitee"></a>
> <a href="https://github.com/sjh123465/bisai"><img src="https://img.shields.io/badge/GitHub-181717?logo=github&logoColor=white"></a>
> </p>

<details><summary><b>👀 点击查看截图预览</b></summary>

| 💬 对话 Tab（SSE 流式 + 工具徽章） | 🗺️ 图谱 Tab（62 节点力导向） |
|---|---|
| 截图占位 | 截图占位 |

| 📝 练一练（AI 出题 + 双轨批改） | 📊 学情驾驶舱（BKT 雷达 + 热力图） |
|---|---|
| 截图占位 | 截图占位 |

> 📸 截图：前端单文件 SPA，所有依赖 CDN 引入，零构建。
</details>

---

## ✨ 核心亮点

| 亮点 | 技术 | 解决什么问题 |
|------|------|-------------|
| 🧠 **Agent 工具调用** | LLM Function Calling | 不是纯文本套壳 —— AI 自主调度 4 类工具（知识检索 / AST 分析 / 沙箱执行 / 学情推荐），苏格拉底式引导 |
| 🔗 **GraphRAG 双引擎** | NetworkX + ChromaDB | 单一向量搜索缺乏学科结构 —— 图谱做多跳推理，向量库做教材原文召回，混合回答 |
| ⚙️ **AST + LLM 双轨批改** | Python `ast` 模块 | 大模型"猜答案"不准 —— AST 提取客观特征（嵌套循环/递归/死循环/复杂度），LLM 只负责解释 |
| 🎯 **BKT 式知识追踪** | 简化版掌握度更新 | 静态掌握度不反映真实水平 —— 每次答题后按知识点更新掌握概率（初始 0.3，答对 +0.15，答错 -0.10，夹紧 [0.05, 0.98]） |
| 🖼️ **多模态截图答疑** | Zhipu GLM-4V-Flash | 编程问题常带截图 —— 直接上传报错/代码截图，视觉模型理解后答疑 |
| 📺 **SSE 流式全链路** | FastAPI StreamingResponse | 等待 20 秒才出答案体验差 —— Agent 调度 + 回答全部流式输出，Markdown + 代码高亮实时渲染 |

---

## 🏗️ 系统架构

```
┌─────────────────────────────────────────────────────────────┐
│  💻  前端（单文件 SPA · HTML + TailwindCSS）                   │
│                                                             │
│  📊 ECharts 学情图  ·  🗺️ SVG 力导向图谱  ·  💬 SSE 流式对话  │
│  🧩 Marked.js + Highlight.js 代码块（语言标签 + 一键复制）      │
└────────────────────────┬────────────────────────────────────┘
                         │ HTTP / SSE / WebSocket
┌────────────────────────▼────────────────────────────────────┐
│  🦄  后端（FastAPI · Python 3.11+）                           │
│                                                             │
│  ┌────────────────────────────────────────────────────┐     │
│  │  🧭 Agent 调度器（Function Calling 路由）             │     │
│  │    ├─ search_knowledge  →  GraphRAGService          │     │
│  │    ├─ analyze_code_ast  →  ASTService               │     │
│  │    ├─ execute_code      →  SandboxService           │     │
│  │    └─ get_learning_path →  BKTService + GraphSvc    │     │
│  └────────────────────────────────────────────────────┘     │
│                                                             │
│  ┌─────────────────┐  ┌─────────────────┐  ┌────────────┐  │
│  │ 🔗 GraphRAG     │  │ ⚙️ 代码解析      │  │ 🎯 BKT     │  │
│  │ NetworkX +      │  │ Python AST +    │  │ 简化版      │  │
│  │ ChromaDB (62节点)│  │ subprocess 沙箱 │  │ 掌握度更新  │  │
│  └─────────────────┘  └─────────────────┘  └────────────┘  │
│                                                             │
│  🛡️ L4 安全层：CORS → 滑动窗口限流 → 请求/错误率监控           │
└────────────────────────┬────────────────────────────────────┘
                         │ 文件系统
┌────────────────────────▼────────────────────────────────────┐
│  💾 持久化                                                    │
│                                                             │
│  📄 JSON：知识图谱 / 学情数据 / 错题本 / 用户（PBKDF2）         │
│  🗄️  ChromaDB（嵌入式 SQLite）：教材原文向量                   │
└─────────────────────────────────────────────────────────────┘
```

### 技术栈一览

| 层级 | 技术 |
|------|------|
| **前端** | HTML5 + TailwindCSS (CDN) + Marked.js + Highlight.js + ECharts 5 + DOMPurify + Vanilla JS |
| **后端** | FastAPI 0.115 + Uvicorn + Pydantic v2 |
| **AI 模型** | DeepSeek Chat（主 LLM）· Zhipu GLM-4V-Flash（多模态） |
| **Agent** | 自研 Function Calling 调度器（直接调用 OpenAI 兼容接口，未依赖 LangChain） |
| **知识图谱** | NetworkX（内存图计算）+ ChromaDB（向量） |
| **沙箱** | Python subprocess + 危险模块黑名单 + 超时强制终止（Docker 模式可选） |
| **鉴权** | PBKDF2 密码哈希 + HMAC 签名 Token |
| **安全** | 滑动窗口限流（60 req/min）· 运行时指标暴露 · **39 单元测试全部通过** |

---

## 🧭 Agent 工具详解 — Function Calling 调度链

Agent 不只是"调用一个 API 然后套壳"。它会**自主决策**调度哪些工具、什么顺序传参、什么时候停下来给人看。下面是 4 类核心工具的输入/输出签名：

### 工具 1：`search_knowledge` — GraphRAG 混合检索

```python
# 输入（function calling 参数）
{ "query": "红黑树删除操作" }

# 内部执行
GraphRAGService.retrieve(query, vector_top_k=…) → 图谱命中 + 向量命中

# 返回给 Agent 的内容
{
  "graph_hits": [
    {"id": "rb_delete", "name": "红黑树删除", "category": "operation",
     "prerequisites": ["rb_insert", "rotation"]}
  ],
  "vector_hits": [
    {"chunk": "红黑树删除后的平衡恢复分 4 种情况...", "score": 0.78}
  ]
}
# 🔗 图谱返回"结构关系"，向量库返回"教材原文"
```

### 工具 2：`analyze_code_ast` — AST 静态分析

```python
# 输入
{ "code": "def quicksort(arr):\n    while True:\n        arr = arr + [1]" }

# 输出（ASTFeatures 数据类字段）
{
  "loop_count": 1,
  "max_loop_depth": 1,               # 最大嵌套循环深度
  "has_recursion": False,
  "possible_infinite_loop": True,    # while True 且循环变量未更新
  "infinite_loop_hint": "⚠️ 检测到 while True 且循环变量未被修改，可能是死循环",
  "estimated_complexity": "O(n)",    # 基于嵌套层数 + 递归的启发式估算
  "complexity_reason": "单层循环，通常为线性复杂度"
}
# 🔗 纯 AST 提取，不调用 LLM，结果客观稳定
```

### 工具 3：`execute_code` — 安全执行

```python
# 输入
{ "code": "print(sum([1,2,3]))" }

# 输出（ExecuteResult 数据类字段）
{
  "success": True,
  "output": "6\n",
  "error": "",
  "timed_out": False,
  "execution_time": 0.08
}
# 🔗 默认 subprocess，DANGEROUS_MODULES 黑名单拦截 22 个模块
#    （os / subprocess / socket / ctypes / pickle / shutil / multiprocessing …）
#    Docker 模式下替换为容器隔离（--network none + 资源限制）
```

### 工具 4：`get_learning_path` — BKT + 图谱联合推荐

```python
# 输入
{ "student_id": "demo_student", "topic": "动态规划" }

# 输出
{
  "prereqs": ["递归基础", "分治思想", "快速排序"],  # 图谱前置关系
  "weak_prereqs": ["递归基础"],                     # BKT 掌握度 < 0.6
  "suggested_path": [
    {"step": 1, "concept": "递归基础", "mastery": 0.35, "action": "先补这个"},
    {"step": 2, "concept": "分治思想", "mastery": 0.60, "action": "练 2 道快排变体"},
    {"step": 3, "concept": "动态规划入门", "mastery": 0.0, "action": "开始 DP"}
  ]
}
# 🔗 图谱决定"先学什么"，BKT 决定"谁需要补"
```

### Agent 调度流程（实际运行时）

```
用户: "我写的快排为啥超时了？"
  │
  ▼
🧠 Agent 判断意图 → "代码调试 + 复杂度分析"
  │
  ├─ Step 1 调用 search_knowledge("快排超时原因")
  │         → 拿到 O(n²) 最坏情况、退化成链表的例子
  │
  ├─ Step 2 调用 analyze_code_ast(用户代码)
  │         → max_loop_depth=0, has_recursion=True
  │         → estimated_complexity 提示递归带来的高复杂度
  │
  ├─ Step 3 调用 execute_code(用户代码)
  │         → success=True，但 execution_time 明显偏长
  │
  └─ Step 4 综合回答（苏格拉底式）：
           "你选的 pivot 是 arr[0] 对吧？
            当数组已经有序时，每次只排除一个元素 → 递推式 T(n)=T(n-1)+n → O(n²)
            试试 random pivot 或三数取中 pivot？"
```

---

## 🎮 5 分钟极速体验

```bash
# Clone + 后端 + 启动 —— 就这三步
git clone https://github.com/sjh123465/bisai.git && cd bisai/backend
python -m venv .venv && .venv\Scripts\activate
pip install -r requirements.txt && copy .env.example .env && python -m uvicorn app.main:app --port 8080

# 另开终端跑 pytest 看 39/39
cd bisai/backend && .venv\Scripts\activate && pytest tests/ -v
```

浏览器打开 `http://localhost:8080/static/index.html` → 点「👩‍🏫 教师演示」一键填充 → 登录。

---

## 🚀 快速开始

### 方式一：Docker Compose（推荐）

```bash
git clone https://github.com/sjh123465/bisai.git
cd bisai
# 编辑 backend/.env 填入 LLM_API_KEY，然后：
docker compose -f docker/docker-compose.yml up -d --build
# 前端已打包进镜像（/app/frontend），无需额外挂载
# 访问 http://localhost:8080/static/index.html
```

### 方式二：源码运行

```bash
# 1. 克隆仓库
git clone https://github.com/sjh123465/bisai.git
cd bisai/backend

# 2. 创建虚拟环境
python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS/Linux:
source .venv/bin/activate

# 3. 安装依赖
pip install -r requirements.txt

# 4. 配置 API Key
copy .env.example .env          # Windows
# cp .env.example .env          # macOS/Linux
# 编辑 .env，填入 LLM_API_KEY（必需）、MULTIMODAL_API_KEY（可选）

# 5. 启动后端
python -m uvicorn app.main:app --host 0.0.0.0 --port 8080

# 6. 打开浏览器
#    前端界面：http://localhost:8080/static/index.html
#    API 文档：http://localhost:8080/docs
#    健康检查：http://localhost:8080/health
```

### 方式三：一键脚本（Windows PowerShell）

```powershell
cd bisai/backend
pip install -r requirements.txt
@"
LLM_API_KEY=sk-你的deepseekkey
LLM_BASE_URL=https://api.deepseek.com/v1
LLM_MODEL=deepseek-chat
MULTIMODAL_API_KEY=你的智谱key  # 可选
"@ | Out-File -FilePath .env -Encoding utf8
python -m uvicorn app.main:app --host 0.0.0.0 --port 8080
```

### 🌐 访问地址

| 资源 | URL |
|------|-----|
| 前端界面 | `http://localhost:8080/static/index.html` |
| OpenAPI 文档 | `http://localhost:8080/docs` |
| 健康检查 | `http://localhost:8080/health` |
| 运行指标（教师） | `http://localhost:8080/api/metrics` |

### 🔑 演示账号

| 角色 | 用户名 | 密码 | 权限 |
|------|--------|------|------|
| 👩‍🏫 教师 | `teacher` | `123456` | 学情驾驶舱 + LLM 报告 + 指标监控 |
| 👨‍🎓 学生 | `student` | `123456` | 对话 + 练一练 + 错题本 |

> 💡 登录弹窗支持**一键填充** —— 点击「👩‍🏫 教师演示」或「👨‍🎓 学生演示」按钮自动填入账号密码。

---

## 🧩 功能地图

### 💬 对话 Tab — Agent Function Calling

| 能力 | 触发方式 | Agent 内部调度 |
|------|---------|---------------|
| 📖 理论问答 | "什么是红黑树？" | GraphRAG（图谱 + 向量混合检索） |
| 🐛 代码调试 | 贴入报错代码 | 沙箱运行 → AST 静态分析 → 苏格拉底引导 |
| 🖼️ 截图答疑 | 点击"截图提问"上传图片 | 多模态视觉模型理解图片 → 结合图谱讲解 |
| 📚 学习路径 | "图论我该先学什么？" | BKT 薄弱点 + 图谱前置关系 → 推荐序列 |
| 🔗 图谱节点点击 | 在图谱 Tab 点击节点 | 自动跳转到对话 Tab，发送该节点提问 |

### 📝 练一练 Tab — AI 出题 + 双轨批改

| 能力 | 说明 |
|------|------|
| 🎲 单题生成 | 选择知识点 + 题型（选择/判断/编程）→ AI 自动出题 |
| 📄 批量试卷 | 一次生成 5 题，逐题作答，进度条实时显示 |
| ✅ 双轨批改 | **沙箱运行结果** + **AST 特征分析** → LLM 结构化评分 |
| 📕 错题重做 | 自动收集错题到错题本，支持针对性重做 |
| 💡 查看提示 | 不想直接看答案？让 AI 逐步引导 |

### 🗺️ 图谱 Tab — 学科知识图谱

- **62 节点**覆盖 6 大类别（章节 / 数据结构 / 算法 / 操作 / 范式 / 概念）
- **69 条前置关系**（学习路径推理）
- SVG 力导向布局 · 节点拖拽 · 节点大小按度数加权 · 点击节点直接提问
- **快速搜索**（右侧栏）：实时搜索 → 高亮匹配字符 → 一键在图谱中定位 🎯

### 📊 学情 Tab — BKT 驾驶舱

| 组件 | 数据源 | 说明 |
|------|--------|------|
| 📈 掌握度雷达图 | BKT | 学生各知识点掌握概率（简化版增量更新） |
| 🔥 薄弱热力图 | 班级聚合 | 全班各知识点薄弱率（< 60% 为薄弱） |
| 📕 高频错题榜 | 错题本 | 按知识点聚合全班答错次数排名 |
| 👥 学生学情列表 | BKT + 错题本 | 按薄弱程度升序，点击查看详情雷达 |
| 🤖 LLM 学情报告 | 全部数据 + LLM | 自动生成 Markdown 报告（概述/薄弱点/改进建议） |

### ⚡ 右侧栏 — 实时数据仪表盘

- 4 张渐变统计卡：图谱节点 / 知识关联 / 薄弱知识点 / 活跃学生
- 每 **30 秒自动刷新** · 手动 🔄 刷新按钮
- 图谱图例（6 种类别配色说明）
- 图谱节点快速搜索

---

## 📖 API 速查表

所有 API 前缀 `/api`，需鉴权的接口在表中标注 🔐（登录后自动注入 `Authorization: Bearer <token>`）。

### 🔐 鉴权

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/auth/login` | 登录，返回 `token` |
| POST | `/api/auth/register` | 注册（student / teacher 角色） |
| GET | `/api/auth/me` 🔐 | 当前登录用户信息 |

### 💬 Agent 对话（SSE 流式）

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/chat/stream` | Agent 流式对话，SSE 事件类型：`start` / `chunk` / `end` |
| POST | `/api/chat/quick` | 非流式快速问答（一次性返回完整答案） |

### 🗺️ 知识图谱

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/knowledge/graph` | 获取完整图谱（节点 + 边 + 统计） |
| GET | `/api/knowledge/stats` | 图谱统计（节点数 / 边数 / 分类分布） |
| GET | `/api/knowledge/nodes` | 节点列表（可按分类过滤） |
| GET | `/api/knowledge/search?query=` | 关键词搜索节点 |
| GET | `/api/knowledge/node/{node_id}` | 节点详情 + 前置 / 后继 |
| POST | `/api/knowledge/nodes` | 新增节点 |
| POST | `/api/knowledge/edges` | 新增边 |

### ⚙️ 代码分析

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/code/analyze` | AST 静态分析（死循环 / 嵌套 / 递归 / 复杂度） |
| POST | `/api/code/execute` | 沙箱执行 Python 代码 |
| POST | `/api/code/test` | 沙箱执行 + 测试用例比对 |

### 📝 出题与批改

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/exam/generate` | AI 单题生成（字段：`concept` + `qtype`） |
| POST | `/api/exam/paper` | AI 批量生成试卷（字段：`concepts` + `count` + `qtypes`） |
| POST | `/api/exam/grade` | 双轨批改（代码 + 测试用例 → 沙箱 + AST + LLM 评分） |

### 🎯 BKT 知识追踪

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/bkt/mastery/{student_id}` | 学生各知识点掌握概率 |
| GET | `/api/bkt/weak/{student_id}` | 学生薄弱知识点 Top-N |
| GET | `/api/bkt/heatmap` | 班级掌握度热力图数据 |
| POST | `/api/bkt/record` | 答题后更新掌握度（`student_id` + `concept_id` + `correct`） |

### 👩‍🏫 教师端 🔐（整组需 teacher 角色）

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/teacher/dashboard` | 班级聚合数据（热力图 + 统计 + 概览） |
| GET | `/api/teacher/wrong-top` | 高频错题榜（按知识点聚合） |
| GET | `/api/teacher/students` | 学生列表（按薄弱度排序） |
| GET | `/api/teacher/student/{student_id}` | 单个学生详情（BKT + 错题） |
| GET | `/api/teacher/report` | LLM 自动生成学情 Markdown 报告 |

### 🖼️ 多模态

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/multimodal/analyze` | 图片理解（`image` Base64 data URL + `question`），内部结合 GraphRAG |

### 📕 错题本

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/wrongbook/list/{student_id}` | 学生错题列表 |
| GET | `/api/wrongbook/retry/{student_id}?limit=10` | 获取可重做错题 |
| GET | `/api/wrongbook/counts/{student_id}` | 各知识点错题计数 |
| POST | `/api/wrongbook/add` | 记录错题 |
| POST | `/api/wrongbook/record` | 答题结果记录（前端主用） |
| DELETE | `/api/wrongbook/clear/{student_id}` | 清空学生错题本 |

### 🛠️ 系统

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/health` | 健康检查（含运行指标） |
| GET | `/api/metrics` 🔐 | 运行指标快照（teacher 角色） |

### 💾 数据文件

后端首次启动时自动初始化：

| 文件 | 来源 | 说明 |
|------|------|------|
| `data/knowledge_graph.json` | 种子脚本生成 | 62 节点 + 69 边 |
| `data/chroma/` | 种子脚本生成 | ChromaDB 向量库（教材原文） |
| `data/users.json` | 内置 + 注册 | teacher / student 两个演示账号 |
| `data/bkt_data.json` | 内置 | demo_student / test_user 的初始 BKT 数据 |
| `data/wrong_book.json` | 运行时生成 | 错题记录 |

---

## 📂 项目结构

```
CodeMentor/
├── 🐳 docker/
│   ├── Dockerfile.backend       # 后端镜像（python:3.11-slim + 依赖预装）
│   ├── Dockerfile.sandbox       # 沙箱镜像（non-root + 最小 Python）
│   └── docker-compose.yml       # 一键编排
│
├── ⚙️ backend/
│   ├── app/
│   │   ├── main.py              # FastAPI 入口（CORS / 限流 / 监控 / 路由注册 / 静态挂载）
│   │   │
│   │   ├── core/
│   │   │   ├── config.py        # pydantic-settings 配置（.env 加载）
│   │   │   ├── security.py      # PBKDF2 密码哈希 + HMAC Token + 角色鉴权
│   │   │   ├── ratelimit.py     # 滑动窗口限流（默认 60 req/min）
│   │   │   ├── metrics.py       # 请求计数 / 错误率 / 延迟监控
│   │   │   ├── logger.py        # 统一日志（带 uvicorn 兼容）
│   │   │   └── seed_knowledge.py # 62 节点 / 69 边种子数据 + 向量库初始化
│   │   │
│   │   ├── agents/
│   │   │   └── agent_service.py # Agent Function Calling 调度器（4 类工具 + 历史压缩）
│   │   │
│   │   ├── services/
│   │   │   ├── llm_service.py   # DeepSeek 调用（Chat + Embedding，本地哈希降级）
│   │   │   ├── graph_service.py  # NetworkX 图谱 CRUD + 搜索 + 前置推理
│   │   │   ├── vector_service.py # ChromaDB 向量检索
│   │   │   ├── graphrag_service.py # 图谱 + 向量混合检索
│   │   │   ├── ast_service.py    # Python AST 分析（死循环/嵌套/递归/复杂度）
│   │   │   ├── sandbox_service.py # subprocess 沙箱（黑名单 + 超时 + Docker 模式）
│   │   │   ├── bkt_service.py    # 掌握度更新（简化版 BKT：初始 0.3 / 正确 +0.15 / 错误 -0.10）
│   │   │   ├── exam_service.py   # AI 题目生成
│   │   │   ├── grading_service.py # 双轨批改（沙箱 + AST + LLM 解释）
│   │   │   ├── multimodal_service.py # Zhipu GLM-4V-Flash 图片理解
│   │   │   └── wrongbook_service.py  # 错题本
│   │   │
│   │   └── routers/              # FastAPI 路由层（按功能拆分）
│   │       ├── auth.py           # 登录 / 注册
│   │       ├── chat.py           # SSE 流式对话
│   │       ├── knowledge.py      # 图谱 CRUD + 搜索
│   │       ├── code.py           # 沙箱运行 / AST 分析 / 批改
│   │       ├── exam.py           # 出题 + 试卷
│   │       ├── bkt.py            # 掌握度查询 + 更新
│   │       ├── teacher.py        # 驾驶舱 + LLM 学情报告（🔐 teacher）
│   │       ├── multimodal.py     # 图片理解
│   │       ├── wrongbook.py      # 错题本
│   │       └── metrics_router.py # 运行指标暴露
│   │
│   ├── data/                     # 💾 运行时数据（.gitignore 忽略）
│   │   ├── knowledge_graph.json
│   │   ├── chroma/
│   │   ├── bkt_data.json
│   │   ├── wrong_book.json
│   │   └── users.json
│   │
│   ├── tests/                     # 🧪 测试套件（39 项）
│   │   ├── conftest.py           # 临时数据目录 fixture
│   │   ├── test_api.py           # API 端点测试
│   │   ├── test_ast.py           # AST 分析正确性
│   │   ├── test_bkt.py           # BKT 数学更新
│   │   ├── test_sandbox.py       # 沙箱隔离
│   │   ├── test_security.py      # Token / 哈希
│   │   └── test_ratelimit.py     # 限流行为
│   │
│   ├── .env.example              # 📋 配置模板
│   └── requirements.txt          # 📦 依赖（14 项）
│
└── 🎨 frontend/
    └── index.html                # 🖼️ 单页前端（约 2200 行，CDN 引入所有依赖，零构建）
```

---

## 🧪 测试

```bash
cd backend
pytest tests/ -v
```

当前 **39 项测试全部通过**，覆盖：

| 模块 | 测试内容 |
|------|---------|
| `test_api` | 对话 / 图谱 / 学情 / 登录端点可达性 |
| `test_ast` | 死循环检测 / 嵌套循环计数 / 递归识别 / 复杂度估算 |
| `test_bkt` | 掌握度更新正确性 / 边界夹紧 [0.05, 0.98] |
| `test_sandbox` | subprocess 执行 / 危险模块拦截 / 超时强制终止 |
| `test_security` | PBKDF2 哈希 / HMAC Token 签名 + 验证 |
| `test_ratelimit` | 滑动窗口限流 / 豁免路径 |

---

## 🎯 答辩演示脚本（推荐）

| # | 操作 | 展示能力 | 预估时长 |
|---|------|---------|---------|
| 1 | 打开前端 → 登录 teacher/123456 | 一键填充 + 角色路由 | 10s |
| 2 | 切到 🗺️ 图谱 Tab | 62 节点力导向图 · 点击节点 | 30s |
| 3 | 切回 💬 对话 → 问"红黑树和 AVL 有什么区别？" | Agent 自动 GraphRAG · 流式输出 · 图谱节点引用 🏷️ | 60s |
| 4 | 附加代码 → 粘一段含死循环的快排 → 点"AI 辅导" | 沙箱超时 → AST 定位死循环 → 苏格拉底引导 | 45s |
| 5 | 切到 📝 练一练 → 选"快速排序" + "编程题" → 生成 | AI 出题 · 代码编辑器 | 30s |
| 6 | 写答案 → 点"提交批改" | 双轨批改 · AST 特征 + LLM 解释 | 30s |
| 7 | 切到 📊 学情 → 点"🤖 LLM 生成报告" | BKT 雷达图 + 热力图 + AI 学情报告（Markdown） | 60s |
| 8 | 右侧栏搜索"红黑树" → 点 🎯 定位 | 搜索高亮 → 图谱自动聚焦 + 脉冲动画 | 15s |
| 9 | 右侧栏数据卡（节点 62 / 关联 69 / 薄弱 1 / 活跃 2） | 实时仪表盘 · 每 30s 自动刷新 | 10s |

**总时长：约 5 分钟**

---

## ⚙️ 配置参数

所有参数通过 `backend/.env` 配置，完整模板见 `.env.example`：

| 变量 | 默认值 | 必填 | 说明 |
|------|--------|------|------|
| `LLM_PROVIDER` | `deepseek` | 可选 | 提供商标识（仅作标记，实际走 OpenAI 兼容协议） |
| `LLM_API_KEY` | — | ✅ | 大模型 API Key（主 LLM） |
| `LLM_BASE_URL` | `https://api.deepseek.com/v1` | ✅ | 主 LLM 地址 |
| `LLM_MODEL` | `deepseek-chat` | ✅ | 主 LLM 名称 |
| `EMBEDDING_LOCAL` | `false` | 可选 | `true` 则用本地 sentence-transformers |
| `EMBEDDING_MODEL` | `text-embedding-v3` | 可选 | Embedding 模型名（接口不可用时自动降级本地哈希向量） |
| `MULTIMODAL_API_KEY` | — | 可选 | 视觉模型 Key（主模型不支持视觉时必填） |
| `MULTIMODAL_BASE_URL` | — | 可选 | 视觉模型地址（如 `https://open.bigmodel.cn/api/paas/v4`） |
| `MULTIMODAL_MODEL` | — | 可选 | 视觉模型名称（如 `glm-4v-flash`） |
| `SANDBOX_TIMEOUT` | `5` | 可选 | 沙箱执行超时秒数 |
| `SANDBOX_ALLOWED_LANGS` | `python` | 可选 | 允许执行的语言 |
| `SANDBOX_MODE` | `auto` | 可选 | `auto` / `docker` / `subprocess` |
| `SANDBOX_DOCKER_IMAGE` | `python:3.11-slim` | 可选 | Docker 沙箱镜像 |
| `AUTH_SECRET` | 空（用开发默认值） | 可选 | HMAC 签名密钥，**生产必须设置** |
| `RATE_LIMIT_PER_MIN` | `60` | 可选 | 每 IP 每分钟请求上限 |
| `DATA_DIR` | `./data` | 可选 | 运行时数据目录 |
| `CHROMA_DIR` | `./data/chroma` | 可选 | 向量库目录 |
| `GRAPH_FILE` | `./data/knowledge_graph.json` | 可选 | 图谱文件路径 |
| `PORT` | `8000` | 可选 | 服务端口（启动时用 `--port 8080` 覆盖为 8080） |
| `HOST` | `0.0.0.0` | 可选 | 服务监听地址 |

### 推荐供应商

| 用途 | 推荐 | 费用 |
|------|------|------|
| 主 LLM（Function Calling） | DeepSeek Chat | 💰 便宜（约 ¥1/M tokens） |
| 多模态（截图答疑） | Zhipu GLM-4V-Flash | 🆓 免费额度 |
| Embedding | 本地 sentence-transformers | 🆓 零成本 |

---

## 🐳 Docker 部署

```yaml
# docker/docker-compose.yml（实际内容）
services:
  codementor:                     # ← 服务名是 codementor
    build:
      context: ..
      dockerfile: docker/Dockerfile.backend
    container_name: codementor-api
    ports:
      - "8080:8080"
    env_file:
      - ../backend/.env
    environment:
      - SANDBOX_MODE=auto         # 有 docker.sock → 用容器隔离，否则 subprocess
      - RATE_LIMIT_PER_MIN=60
    volumes:
      - codementor-data:/app/data
      # 挂载 docker CLI 与 socket，使后端可启动沙箱容器（嵌套调用）
      - /var/run/docker.sock:/var/run/docker.sock
    restart: unless-stopped

volumes:
  codementor-data:
```

启动：

```bash
docker compose -f docker/docker-compose.yml up -d --build
```

> 💡 只有 **一个服务**：沙箱不是独立容器，而是由后端在运行时按需 `docker run` 起临时容器（`Dockerfile.sandbox` 即该镜像）。所以挂载 `docker.sock` 是必须的。
> 构建上下文是**仓库根目录**（因为要同时拷贝 `backend/` 和 `frontend/`）。

---

## 🔒 安全说明

| 风险 | 当前措施 | 生产建议 |
|------|---------|---------|
| 沙箱执行任意代码 | subprocess + 危险模块黑名单 (`os.system`, `subprocess`, `eval`) + 5s 超时 | 替换为 Docker 容器隔离（compose 已预留） |
| API Key 泄露 | `.env` gitignore · PBKDF2 哈希存储密码 | 使用密钥管理服务（Vault / K8s Secrets） |
| 暴力登录 | 滑动窗口限流 60 req/min · /auth 路径豁免过高频率 | 加验证码 / IP 黑名单 |
| Markdown XSS | **DOMPurify** 消毒所有 LLM 输出（marked v5+ 已移除内置 sanitize）· 用户消息用 `textContent` 写入 | 后端也做输入长度限制 |

> ⚠️ 本项目为**竞赛演示**用途，未经过生产环境安全审计。禁止直接用于生产部署。

---

## 🎨 前端打磨亮点

前端为单文件 SPA（`frontend/index.html`，约 2200 行），所有依赖通过 CDN 引入（TailwindCSS + Marked.js + Highlight.js + ECharts + DOMPurify），**零构建、零 node_modules**。

### 已实现的 40+ 项交互打磨

| 轮次 | 打磨项 |
|------|--------|
| 1 | 📋 动态仪表盘（4 张渐变统计卡 + 30s 自动刷新）· 🔖 胶囊快捷问题（3→5）· 🔐 登录弹窗一键填充 · ✨ Tab 淡入动画 · 🗺️ 图谱自适应高度 |
| 2 | 📝 代码块语言标签（18 种映射）+ hover 一键复制 · 🔍 图谱搜索高亮匹配字符 + 🎯 定位节点 + 回车直达 |
| 3 | 🎨 滚动条品牌色 · 🌈 Tab 选中态底部紫色指示线 · 🏷️ 图表标题左侧色条 · 🔄 图谱 spinner · 📖 报告展开/收起 · ✅ 批改主次按钮区分 · 🔧 TOOL 编号隐藏 |
| 4 | 👋 欢迎语卡片折叠 · 💬 消息气泡 hover 显示角色+时间+复制 · 🏅 错题榜奖牌🥇🥈🥉 + 红色徽章 + 彩色进度条 |
| 5 | 🔐 登录后自动欢迎 + 角色推荐 · 🗺️ 图谱节点 hover tooltip + 紫色辉光 · 📝 练一练快速启动按钮 · 👥 学生列表展开箭头 + 进度条颜色分段 |
| 6 | 👋 欢迎卡片升级：标题栏倒三角 ▼ 旋转 + 底部胶囊按钮始终可见 · 🗺️ 图谱标签三层渲染（圆/标签分离）+ 8 方位智能选位择优 + 半透明深色底衬 · 📐 图谱画布高度自适应（读 clientHeight 替代写死 600px） |
| 7 | 🎯 **右侧边栏按 Tab 动态显隐**（通用 `data-tabs` 机制） |
| 8 | 🎯 **底部快捷操作栏仅对话 Tab 显示**（📎 附加代码 / 🖼️ 截图提问 / 5 个快捷胶囊） |
| 9 | 💬 **对话 Tab flex column 布局让输入栏吸底** · 📝 **练一练按钮主次区分**（主按钮阴影加大、次按钮幽灵样式） · 📊 **学情 LLM 报告按钮渐变大号** |
| 10 | 📝 **练一练批改反馈彩色渐变卡片**（emoji 大图标 + 对错分色渐变背景 + 正确性徽章 + 🔁 再来一道 / 💬 问 AI 按钮） |
| 11 | 📊 **学情学生行内联雷达图展开**（点击 ▶ → accordion 展开小雷达图 + 薄弱知识点彩色进度条 + 再点收起） |
| 12 | 🗺️ **图谱节点鲜艳色升级 + 同类型群体高亮**（6 类节点换更饱和的亮紫/亮玫紫/亮翡翠/亮琥珀/亮玫红/亮天蓝；hover 同族节点同步亮+辉光、异族节点灰化 opacity=0.35） |

**右侧边栏 × Tab 显示矩阵**：

| 边栏卡片 | 💬 对话 | 📝 练一练 | 🗺️ 图谱 | 📊 学情 |
|---------|:------:|:--------:|:------:|:------:|
| ⚡ 实时数据（仪表盘） | ✅ | ✅ | ✅ | ✅ |
| 📎 快捷操作栏 | ✅ | ❌ | ❌ | ❌ |
| 🔍 图谱节点搜索 | ✅ | ❌ | ✅ | ❌ |
| 🏷️ 节点类型图例 | ❌ | ❌ | ✅ | ❌ |
| ⚡ 热门知识点一键出题 | ❌ | ✅ | ❌ | ❌ |
| 🔥 薄弱知识点 Top 3 | ❌ | ❌ | ❌ | ✅ |

### 关键交互细节

- **代码块**：hover 显示"复制"按钮 → 点击变绿"✓ 已复制" → 1.5s 后恢复
- **消息气泡**：hover 显示 `👤 你 · 18:44 · 📋 复制` / `🤖 CodeMentor · 18:44 · 📋 复制`
- **图谱搜索定位**：输入"红黑树" → 紫色高亮匹配字符 → 点 🎯 切图谱 Tab → viewBox 自动居中 → 3s 黄色脉冲辉光
- **登录角色分流**：学生登录 → 聊天推荐 3 条学生操作；教师登录 → 自动切学情 Tab + 学情推荐
- **报告展开**：默认 max-h-96 折叠 → 点"展开 ▼" → max-h-none 完整展开 → 点"收起 ▲"
- **键盘快捷键**：Enter 快速登录、Esc 关闭弹窗

---

## ❓ FAQ

<details><summary><b>Q: 必须用 DeepSeek 吗？可以换其他模型吗？</b></summary>

A: 后端用的是 OpenAI 兼容接口协议，只要你的模型提供商有 Chat Completions Endpoint 就能直接替换。改 `.env` 里的三项：
```
LLM_API_KEY=你的key
LLM_BASE_URL=https://api.qwen.aliyun.com/v1   # 换成千问
LLM_MODEL=qwen-plus
```
Function Calling 也是标准 OpenAI 格式，只要模型支持 tool_calls 字段就没问题。本地部署 Llama 3 + vLLM 也可以。
</details>

<details><summary><b>Q: 为什么 Embedding 会 404？</b></summary>

A: DeepSeek Chat（`deepseek-chat`）**没有 Embedding Endpoint**。`/embeddings` 请求会返回 404。这不是你的配置问题。解决方案：

1. 换 `deepseek-api` 系列模型（有 Embedding）
2. 或设 `EMBEDDING_LOCAL=true` — 自动降级为本地 bigram-hash 向量（已内置）
3. 或换一个有 Embedding 的提供商（如 OpenAI / Zhipu / Qwen）
</details>

<details><summary><b>Q: 沙箱安全吗？会不会跑恶意代码？</b></summary>

A: 默认 subprocess 模式**有限安全**。黑名单拦截了 `os.system`, `subprocess`, `eval`, `exec`, `__import__`, `pickle`, `socket`, `ctypes` 等 20+ 模块。但 Python 可以用 `importlib` 绕黑名单。

**竞赛演示够用**，**生产必须上 Docker**（compose 已预留 sandbox 服务）。沙箱模式自动检测：检测到 `/var/run/docker.sock` 就启用容器隔离。
</details>

<details><summary><b>Q: 种子数据（62 节点 / 69 边）可以扩展吗？</b></summary>

A: 完全可以。后端 `app/core/seed_knowledge.py` 用 Python 字典定义节点，追加即可。种子脚本会自动：
1. 调用 LLM 生成节点描述（可选，需 API Key）
2. 用 NetworkX 计算 pagerank
3. 生成 ChromaDB 向量（或降级为本地哈希）
4. 写入 `data/knowledge_graph.json`

删除 `data/knowledge_graph.json` 后重启后端会自动重新种子。
</details>

<details><summary><b>Q: 前端为什么不拆成 Vue/React + Vite？</b></summary>

A: 两个考虑：
1. **竞赛便携性**：单文件 HTML 可以直接用浏览器打开或挂在任何静态服务器上（甚至 `python -m http.server`），不用 `npm install`、不用构建、不用担心 node_modules 版本
2. **复杂度可控**：前端只做数据展示和用户交互，业务逻辑全在后端。3 人小团队 5 天冲刺期，单文件维护成本最低

如果后续要做产品化，推荐拆成 Vue 3 + Vite + Pinia。
</details>

<details><summary><b>Q: BKT 参数（0.3 / +0.15 / -0.10）是怎么来的？</b></summary>

A: **本项目实现的是 BKT 的工程简化版，不是严格的贝叶斯公式**。答辩时建议如实说明。

真正的 BKT 会用四个参数做贝叶斯更新：
- p(L0) 初始掌握概率、p(T) 转移概率、p(G) 猜测概率、p(S) 失误概率

本项目的实现（[bkt_service.py](backend/app/services/bkt_service.py)）用线性增量代替：
- 初始掌握度 0.3（新手大概率不会）
- 答对一次 +0.15，答错一次 −0.10
- 结果夹紧到 [0.05, 0.98]，避免"一次答对就满分"和"一次答错就归零"

**为什么这样设计**：竞赛周期内，真正的 BKT 需要按知识点训练 p(T)/p(G)/p(S) 参数，缺少真实答题数据时拟合出的参数没有意义；线性增量在演示数据下更稳定、可解释，也足够驱动"薄弱点排序"和"学习路径推荐"。如需升级为完整 BKT，替换 `update_mastery()` 即可，接口不变。
</details>

---

## 🛠️ 故障排查

| 问题 | 排查 |
|------|------|
| 图谱空节点 | 检查 `.env` 中 `LLM_API_KEY` 是否正确（种子脚本需调用 LLM） |
| 沙箱执行超时 | 调整 `SANDBOX_TIMEOUT` 或检查是否进入无限循环（AST 死循环检测） |
| Embedding 404 | 主模型可能不支持 Embedding，设置 `EMBEDDING_LOCAL=true` 降级为本地哈希向量 |
| `/api/teacher/*` 403 | 教师接口需 `teacher` 角色，用 teacher/123456 登录 |
| 前端 CORS | 后端已 `allow_origins=["*"]`，若开发时跨域仍报错检查启动端口 |

---

## 📜 License

MIT License — 用于竞赛和教育用途。

## 🙏 致谢

- **LangChain / sse-starlette** — 依赖清单中保留，架构参考其编排与 SSE 设计（当前实际实现为自研调度 + FastAPI StreamingResponse）
- **DeepSeek / Zhipu AI** — 模型服务
- **FastAPI Community** — SSE + Metrics 中间件参考
- **知识图谱** — 62 节点由项目组依据计算机专业核心课程体系（数据结构 / 算法 / 操作系统 / 编程范式）手工整理，非直接引用论文数据集

---

<p align="center">
  <strong>🚀 Built with ❤️ for AI + Education</strong><br>
  <a href="https://gitee.com/shijh1216/CodeMentor">Gitee</a> · 
  <a href="https://github.com/sjh123465/bisai">GitHub</a>
</p>
