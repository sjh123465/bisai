"""Agent 核心服务 — 意图识别 + Function Calling 工具调度 + 苏格拉底式引导
核心思路：
1. LLM 判断用户意图（理论问答 / 代码调试 / 代码批改 / 知识推荐）
2. 根据意图调用对应工具（GraphRAG / 沙箱 / AST / BKT）
3. 工具结果 + 检索上下文 → 苏格拉底式 Prompt → 流式输出
"""
import json
from typing import AsyncGenerator, Optional
from app.services.llm_service import get_llm
from app.services.graphrag_service import get_graphrag
from app.services.sandbox_service import execute_python
from app.services.ast_service import analyze_code, features_to_text
from app.services.bkt_service import get_bkt
from app.services.graph_service import get_graph
from app.core.logger import get_logger

logger = get_logger("agent")

# 单次对话内最多允许的「工具调度轮次」——超过后强制收口出答案
MAX_TOOL_ROUNDS = 3
# 思考状态旁路哨兵：以它开头的片段不进入正文，由路由层拦截为 SSE status 事件
STATUS_SENTINEL = "\x00STATUS\x00"


def _status(stage: str, detail: str = "") -> str:
    """构造一条旁路状态事件（不会展示给学生，仅供前端渲染思考进度）"""
    return STATUS_SENTINEL + json.dumps({"stage": stage, "detail": detail}, ensure_ascii=False)


# ---------- 工具定义（Function Calling 格式） ----------
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_knowledge",
            "description": "当用户询问概念、理论、知识点时调用。例如：什么是红黑树？快速排序的原理？",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "用户的问题关键词"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "analyze_code_ast",
            "description": "当用户提交了代码、代码报错、或询问代码质量/复杂度时调用。静态分析代码结构。",
            "parameters": {
                "type": "object",
                "properties": {
                    "code": {"type": "string", "description": "用户提交的源代码"},
                },
                "required": ["code"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "execute_code",
            "description": "当用户提交了代码且想看运行结果、或代码可能有 bug 时调用。在沙箱中执行。",
            "parameters": {
                "type": "object",
                "properties": {
                    "code": {"type": "string", "description": "要执行的 Python 代码"},
                },
                "required": ["code"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_learning_path",
            "description": "当用户询问应该学什么、下一步学习建议时调用。基于学情推荐。",
            "parameters": {
                "type": "object",
                "properties": {
                    "student_id": {"type": "string", "description": "学生 ID，默认 demo_student"},
                    "topic": {"type": "string", "description": "感兴趣的主题，可选"},
                },
                "required": ["student_id"],
            },
        },
    },
]


# ---------- 苏格拉底式系统 Prompt ----------
SYSTEM_PROMPT = """你是 CodeMentor，一个懂代码、知图谱、能引导的 AI 导师。你的教学风格是**苏格拉底式引导**——不给答案，给启发。

## 你的角色定位
- 你是计算机专业的资深助教，熟悉数据结构、算法、编程语言、计算机组成原理等
- 你会**主动调用工具**来帮助学生：检索知识图谱、运行学生代码、静态分析代码结构
- 你**绝不直接给出完整答案或完整代码**，而是通过提问和引导让学生自己发现

## 回答原则
1. **代码调试**：先让工具跑代码看报错 → AST 分析代码结构 → 找到潜在问题 → 引导学生思考，不说出 bug 是什么
2. **理论问答**：先查知识图谱（上下游关联）→ 再查向量文档 → 用自己的话组织，配合代码示例或图表说明
3. **学情推荐**：结合学生历史数据，解释"为什么推荐"的理由
4. **语言风格**：亲切但专业，多用反问和类比，避免枯燥说教

## 防幻觉原则（最高优先级，凌驾于以上所有原则）
- 你的回答必须**严格基于**知识图谱检索结果与向量文档检索结果，不得引入未经验证的内容
- 如果你在提供的资料中找不到答案，请直接回答：“根据当前知识库，我无法回答该问题”
- **绝对禁止胡编乱造**：禁止用通用常识、臆测或"大概是这样"的内容填充回答
- 对于与计算机科学无关的问题（如菜谱、娱乐八卦、时政新闻等），一律按上述话术拒答，不要展开作答、不要举例、不要给替代方案
- 若工具检索结果为空，就明确告知资料不足，而不是凭记忆作答

## 格式要求
- 支持 Markdown：代码用 ```python 包裹，列表用 -，重点用 **加粗**
- 引用知识图谱节点时，用 [节点名](graph:节点ID) 格式（前端会自动高亮）
- 引用文档时，用 > 片段... 引用块
- **重要**：收到工具结果后，直接以导师身份对学生讲话。绝对不要出现"我拿到了工具结果"、"工具返回了..."、"我查了一下"这类过程性叙述，把工具信息自然融入你的引导中即可

现在开始你的教学吧！"""


class AgentService:
    def __init__(self):
        self.llm = get_llm()
        self.graphrag = get_graphrag()

    # ---------- 多轮对话压缩 ----------
    async def _summarize_history(self, history: list[dict]) -> str:
        """对早期对话做摘要，控制 Token 不超限且保留关键上下文"""
        if not history:
            return ""
        text = "\n".join(f"{m['role']}: {m['content'][:300]}" for m in history)
        messages = [
            {"role": "system", "content": "你是对话摘要器。请用 3-5 句话总结以下师生对话的核心内容，保留学生问过的关键知识点、代码问题和导师给出的关键引导。"},
            {"role": "user", "content": text},
        ]
        try:
            resp = await self.llm.chat(messages, temperature=0.2)
            return resp["choices"][0]["message"]["content"]
        except Exception as e:
            logger.error(f"历史摘要失败: {e}")
            return f"（摘要失败，共 {len(history)} 轮历史对话）"

    # ---------- 工具执行 ----------
    async def _run_tool(self, tool_name: str, args: dict) -> str:
        logger.info(f"🔧 执行工具: {tool_name} | args={json.dumps(args, ensure_ascii=False)[:200]}")
        try:
            if tool_name == "search_knowledge":
                query = args.get("query", "")
                retrieved = await self.graphrag.retrieve(query)
                return self.graphrag.format_for_llm(retrieved, max_chunks=5)

            elif tool_name == "analyze_code_ast":
                code = args.get("code", "")
                feats = analyze_code(code)
                return features_to_text(feats)

            elif tool_name == "execute_code":
                code = args.get("code", "")
                result = execute_python(code)
                if result.timed_out:
                    return f"⚠️ 沙箱执行超时（可能死循环）\n{result.error}"
                if result.success:
                    return f"✅ 代码执行成功\n--- 输出 ---\n{result.output}"
                else:
                    return f"❌ 代码执行失败\n--- 输出 ---\n{result.output}\n--- 错误 ---\n{result.error}"

            elif tool_name == "get_learning_path":
                sid = args.get("student_id", "demo_student")
                topic = args.get("topic", "")
                bkt = get_bkt()
                graph = get_graph()
                mastery = bkt.get_mastery(sid)

                # 获取错题数，作为推荐权重因子
                from app.services.wrongbook_service import get_wrongbook
                wrong_counts = get_wrongbook().get_wrong_count_by_student(sid)
                max_wrong = max(wrong_counts.values()) if wrong_counts else 1

                # 综合权重 = 薄弱度(1-mastery)*0.6 + 错题归一化*0.4
                all_concepts = set(mastery.keys()) | set(wrong_counts.keys())
                scored = []
                for cid in all_concepts:
                    m = mastery.get(cid, 0.3)
                    wc = wrong_counts.get(cid, 0)
                    weight = (1 - m) * 0.6 + (wc / max_wrong if max_wrong else 0) * 0.4
                    scored.append((cid, m, wc, weight))

                # 1. 按综合权重排序取最薄弱 3 个
                scored.sort(key=lambda x: x[3], reverse=True)
                weak = scored[:3]
                weak_lines = "\n".join(
                    f"- {cid}: 掌握度 {m:.0%}，错题 {wc} 次，综合优先级 {w:.2f}"
                    for cid, m, wc, w in weak
                ) or "（暂无答题数据，默认推荐算法基础）"

                # 2. 结合图谱：为每个薄弱点找前置知识（先补前置再学当前）
                path_lines = []
                for cid, m, wc, w in weak:
                    node = graph.get_node(cid)
                    if not node:
                        matches = graph.search_nodes(cid, top_k=1)
                        if matches:
                            cid = matches[0]["id"]
                            node = matches[0]
                    if node:
                        prereqs = graph.get_upstream(cid)
                        reason = f"掌握度 {m:.0%}" + (f"，累计答错 {wc} 次" if wc else "")
                        if prereqs:
                            names = "、".join(p.get("name", p["id"]) for p in prereqs[:3])
                            path_lines.append(f"📌 [{node.get('name', cid)}]（{reason}）建议先掌握前置：{names}")
                        else:
                            path_lines.append(f"📌 [{node.get('name', cid)}]（{reason}）无明确前置，可直接开始")

                # 3. 若用户指定了 topic，额外给出该主题的相关节点
                topic_lines = ""
                if topic:
                    path = await self.graphrag.retrieve(topic, graph_depth=1, vector_top_k=2)
                    nodes = path.get("graph_nodes", [])[:4]
                    topic_lines = "\n📚 你感兴趣的主题相关节点:\n" + "\n".join(
                        f"- [{n['id']}] {n.get('name', n['id'])}" for n in nodes
                    )

                return (
                    f"📊 学生 {sid} 学情优先级（综合掌握度+错题数）:\n{weak_lines}\n\n"
                    f"🧭 基于知识图谱前置关系的学习路径:\n" + ("\n".join(path_lines) if path_lines else "暂无薄弱节点") + topic_lines
                )

            return f"未知工具: {tool_name}"
        except Exception as e:
            logger.error(f"工具 {tool_name} 执行异常: {e}")
            return f"[工具执行出错: {str(e)}]"

    # ---------- 流式对话（自动调度工具） ----------
    async def chat_stream(
        self,
        user_message: str,
        code_context: str = "",
        history: Optional[list[dict]] = None,
    ) -> AsyncGenerator[str, None]:
        """
        完整的 Agent 对话流程：
        1. 构建 messages（系统 + 历史 + 当前）
        2. 多轮工具调度（最多 MAX_TOOL_ROUNDS 轮）：LLM 请求工具 → 执行 → 结果喂回 → 再决策
        3. 模型停止请求工具后，流式输出最终引导回答
        """
        # 构建当前消息
        current_content = user_message
        if code_context:
            current_content += f"\n\n📝 学生提交的代码:\n```python\n{code_context}\n```"

        messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        if history:
            # 多轮压缩：超过 8 轮时，对更早的轮次做摘要，保留最近 4 轮原文
            if len(history) > 8:
                recent = history[-4:]
                older = history[:-4]
                summary = await self._summarize_history(older)
                messages.append({"role": "user", "content": f"[历史对话摘要]\n{summary}"})
                messages.append({"role": "assistant", "content": "好的，我已了解之前的对话内容。"})
                messages.extend(recent)
            else:
                messages.extend(history)
        messages.append({"role": "user", "content": current_content})

        # ---- 多轮工具调度：最多 MAX_TOOL_ROUNDS 轮 ----
        for round_idx in range(MAX_TOOL_ROUNDS):
            if round_idx == 0:
                yield _status("planning", "正在理解问题并规划解题思路")
            else:
                yield _status("replanning", f"第 {round_idx + 1} 轮：结合已有结果继续规划")

            try:
                resp = await self.llm.chat(messages, tools=TOOLS, temperature=0.6)
            except Exception as e:
                logger.error(f"LLM 调度失败（第 {round_idx + 1} 轮）: {e}")
                if round_idx == 0:
                    yield f"[LLM 初始化失败: {e}]"
                    return
                yield f"\n\n⚠️ 工具调度中断：{e}\n\n请稍后重试。"
                return

            message = resp["choices"][0]["message"]
            tool_calls = message.get("tool_calls") or []

            # 模型不再请求工具 → 当前内容即最终回答，转流式输出
            if not tool_calls:
                messages.append(message)
                async for chunk in self._stream_answer(messages):
                    yield chunk
                return

            # 有工具调用 → 逐个执行后将结果喂回，进入下一轮决策
            messages.append(message)
            for tc in tool_calls:
                func_name = tc["function"]["name"]
                try:
                    func_args = json.loads(tc["function"]["arguments"])
                except json.JSONDecodeError:
                    func_args = {}
                yield _status("tool", f"正在调用工具 {func_name}")
                tool_result = await self._run_tool(func_name, func_args)
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "content": tool_result,
                })
                yield _status("tool_done", f"工具 {func_name} 执行完成")
                # 给前端发一个 tool_result 标记
                yield f"\n> *📎 工具 `{func_name}` 返回结果已获取*\n\n"

        # ---- 轮次用尽仍有工具请求 → 强制收口，基于已有信息作答 ----
        logger.info(f"工具调度达到上限 {MAX_TOOL_ROUNDS} 轮，强制收口")
        messages.append({
            "role": "user",
            "content": "（工具调用已达上限，请直接基于以上已获取的信息作答，不要再请求工具。）",
        })
        async for chunk in self._stream_answer(messages):
            yield chunk

    async def _stream_answer(self, messages: list[dict]) -> AsyncGenerator[str, None]:
        """把最终答案以流式方式吐出（带中断兜底）"""
        yield _status("answering", "正在整合检索结果，生成引导回答")
        try:
            async for chunk in self.llm.chat_stream(messages, temperature=0.6):
                yield chunk
        except Exception as e:
            logger.error(f"流式回答中断: {e}")
            yield f"\n\n⚠️ 回答中断：{e}\n\n请稍后重试；若持续失败，请检查 `.env` 中的 LLM_API_KEY 与网络连通性。"

    # ---------- 单轮同步对话（不带工具调度，快速响应） ----------
    async def quick_answer(self, query: str) -> str:
        """快速问答：先走 GraphRAG，再喂 LLM 组织语言"""
        retrieved = await self.graphrag.retrieve(query)
        ctx = self.graphrag.format_for_llm(retrieved)
        if not retrieved["graph_nodes"] and not retrieved["vector_chunks"]:
            return "抱歉，我在知识图谱和教材中都没找到相关内容。请尝试换个关键词，或者告诉我你具体在学习哪门课？"

        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"问题: {query}\n\n检索到的上下文:\n{ctx}"}
        ]
        resp = await self.llm.chat(messages, temperature=0.6)
        return resp["choices"][0]["message"]["content"]


_agent = None

def get_agent() -> AgentService:
    global _agent
    if _agent is None:
        _agent = AgentService()
    return _agent
