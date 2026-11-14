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
        2. LLM 返回 → 若请求工具调用则执行 → 把结果喂回 → 再次请求 → 流式输出
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

        # 第一轮：LLM 决定是否调工具
        try:
            resp = await self.llm.chat(messages, tools=TOOLS, temperature=0.6)
        except Exception as e:
            yield f"[LLM 初始化失败: {e}]"
            return

        choice = resp["choices"][0]
        message = choice["message"]

        # ---- 判断是否需要工具调用 ----
        tool_calls = message.get("tool_calls") or []

        if not tool_calls:
            # 无工具调用 → 直接流式输出
            messages.append(message)  # assistant 消息
            async for chunk in self.llm.chat_stream(messages, temperature=0.6):
                yield chunk
            return

        # ---- 有工具调用 → 执行工具，然后流式输出最终回答 ----
        yield f"<!--thinking: 正在调用工具 {', '.join(tc['function']['name'] for tc in tool_calls)} -->\n"

        messages.append(message)  # assistant 消息（包含 tool_calls）

        # 执行每个工具
        for tc in tool_calls:
            func_name = tc["function"]["name"]
            try:
                func_args = json.loads(tc["function"]["arguments"])
            except json.JSONDecodeError:
                func_args = {}
            tool_result = await self._run_tool(func_name, func_args)
            messages.append({
                "role": "tool",
                "tool_call_id": tc["id"],
                "content": tool_result,
            })
            # 给前端发一个 tool_result 标记
            yield f"\n> *📎 工具 `{func_name}` 返回结果已获取*\n\n"

        # 工具结果喂回 → 第二次 LLM 调用 → 流式输出最终引导
        async for chunk in self.llm.chat_stream(messages, temperature=0.6):
            yield chunk

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
