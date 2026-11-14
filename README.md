# CodeMentor — 基于 Agent 与 GraphRAG 的计算机自适应助学平台

> 懂代码、知图谱、能动手的 AI 智能导师 | 大赛参赛作品

## 核心亮点

- **Agent 工具调用（非纯文本套壳）**：LLM 通过 Function Calling 自主调度 4 类工具（知识检索 / AST 静态分析 / 沙箱执行 / 学情推荐），苏格拉底式引导教学
- **GraphRAG 双引擎**：NetworkX 知识图谱（多跳邻居推理）+ ChromaDB 向量检索（教材原文召回）混合检索，回答具备学科全局视野
- **AST + 大模型双轨批改**：Python AST 提取代码特征（嵌套循环/递归/死循环/命名规范/复杂度估算），大模型只负责"解释"不负责"猜"
- **BKT 知识追踪**：贝叶斯知识追踪算法计算知识点掌握概率，驱动个性化学习路径推荐
- **SSE 流式全链路**：Agent 调度过程与回答全部流式输出，Markdown + 代码高亮实时渲染

## 技术架构

```text
[前端] HTML + TailwindCSS + Marked + Highlight.js + ECharts + SVG力导向图谱
   ↕ SSE 流式
[后端] FastAPI + Agent 调度器（Function Calling 路由）
   ├─ GraphRAG 引擎（NetworkX 图谱 + ChromaDB 向量库）
   ├─ 代码解析引擎（Python AST 静态分析）
   ├─ Python 沙箱（subprocess 隔离 + 危险模块拦截 + 超时保护）
   └─ 学情追踪模型（BKT 贝叶斯知识追踪）
[数据] JSON 持久化 + ChromaDB 嵌入式存储
```

## 快速开始

### 1. 安装依赖

```bash
cd backend
pip install -r requirements.txt
```

### 2. 配置 LLM API Key

复制 `.env.example` 为 `.env`，填入你的 Key（推荐 DeepSeek）：

```env
LLM_PROVIDER=deepseek
LLM_API_KEY=sk-xxxx
LLM_BASE_URL=https://api.deepseek.com/v1
LLM_MODEL=deepseek-chat
```

### 3. 启动

```bash
cd backend
python -m uvicorn app.main:app --host 0.0.0.0 --port 8080
```

### 4. 访问

- 前端界面：http://localhost:8080/static/index.html
- API 文档：http://localhost:8080/docs

## 演示场景（答辩推荐）

| 步骤 | 操作 | 展示能力 |
|------|------|---------|
| 1 | 打开前端，切到"图谱"Tab | 62 节点学科知识图谱，点击节点直接提问 |
| 2 | 问"什么是红黑树？和 AVL 有什么区别？" | Agent 自动调用 GraphRAG，流式输出带图谱节点引用 |
| 3 | 附加一段含死循环的快排代码，点击"AI 辅导" | 沙箱超时捕获 → AST 定位死循环 → 苏格拉底式引导（不给答案给启发） |
| 4 | 切到"学情"Tab，点击"LLM 生成报告" | BKT 掌握度雷达图 + 班级热力图 + AI 学情分析报告 |

## 项目结构

```
CodeMentor/
├── backend/
│   ├── app/
│   │   ├── main.py                  # FastAPI 主入口
│   │   ├── core/
│   │   │   ├── config.py            # .env 配置
│   │   │   ├── logger.py            # 日志
│   │   │   └── seed_knowledge.py    # 学科知识图谱种子数据
│   │   ├── services/
│   │   │   ├── llm_service.py       # LLM 调用 + Embedding（含降级）
│   │   │   ├── graph_service.py     # NetworkX 知识图谱
│   │   │   ├── vector_service.py    # ChromaDB 向量检索
│   │   │   ├── graphrag_service.py  # 图谱+向量混合检索
│   │   │   ├── ast_service.py       # AST 静态分析
│   │   │   ├── sandbox_service.py   # Python 沙箱
│   │   │   └── bkt_service.py       # BKT 知识追踪
│   │   ├── agents/
│   │   │   └── agent_service.py     # Agent Function Calling 调度
│   │   └── routers/                 # chat / knowledge / code / bkt / teacher
│   ├── frontend/                    #（由根目录 frontend 提供）
│   └── requirements.txt
└── frontend/
    └── index.html                   # 单页前端（CDN 引入依赖）
```

## 安全说明

- 沙箱为 subprocess 隔离 + 危险模块黑名单 + 超时强制终止，仅适用于演示环境；生产部署建议替换为 Docker 容器隔离
- `.env` 含 API Key，已加入 `.gitignore`，请勿提交
