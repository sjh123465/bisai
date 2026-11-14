"""AST 代码分析服务 — Python 内置 ast 模块
提取：嵌套循环深度、递归、复杂度特征、命名规范、函数结构
⚠️ 只支持 Python（比赛 Demo 足够）
"""
import ast
import re
from typing import Optional
from dataclasses import dataclass, field


@dataclass
class ASTFeatures:
    syntax_ok: bool = True
    syntax_error: str = ""
    # 结构特征
    function_count: int = 0
    class_count: int = 0
    line_count: int = 0
    # 复杂度相关
    max_loop_depth: int = 0
    has_recursion: bool = False
    recursive_funcs: list = field(default_factory=list)
    has_nested_loop: bool = False
    loop_count: int = 0
    if_count: int = 0
    has_list_comp: bool = False
    # 命名规范
    bad_names: list = field(default_factory=list)
    # 死循环检测
    possible_infinite_loop: bool = False
    infinite_loop_hint: str = ""
    # 复杂度估算
    estimated_complexity: str = "O(1)"
    complexity_reason: str = ""


class ASTAnalyzer(ast.NodeVisitor):
    def __init__(self, source: str):
        self.source = source
        self.features = ASTFeatures()
        self._current_func = None
        self._loop_depth = 0
        self._max_loop_depth = 0
        self._func_calls_in_loop = set()
        self._loop_bodies_const = {}  # node_id -> vars modified in loop body

    def analyze(self) -> ASTFeatures:
        self.features.line_count = len(self.source.strip().split("\n"))
        try:
            tree = ast.parse(self.source)
        except SyntaxError as e:
            self.features.syntax_ok = False
            self.features.syntax_error = f"第 {e.lineno} 行: {e.msg}"
            return self.features
        self.visit(tree)
        self.features.max_loop_depth = self._max_loop_depth
        self._estimate_complexity()
        self._check_possible_infinite_loop()
        return self.features

    # ---------- Visitor ----------
    def visit_FunctionDef(self, node: ast.FunctionDef):
        self.features.function_count += 1
        prev = self._current_func
        self._current_func = node.name
        # 命名规范：snake_case
        if not re.match(r'^[a-z_][a-z0-9_]*$', node.name) and node.name != "__init__":
            self.features.bad_names.append(f"函数 '{node.name}' 不符合 snake_case 规范")
        self.generic_visit(node)
        self._current_func = prev

    def visit_ClassDef(self, node: ast.ClassDef):
        self.features.class_count += 1
        if not re.match(r'^[A-Z][a-zA-Z0-9]*$', node.name):
            self.features.bad_names.append(f"类 '{node.name}' 不符合 PascalCase 规范")
        self.generic_visit(node)

    def visit_For(self, node: ast.For):
        self._handle_loop(node)
        self.generic_visit(node)

    def visit_While(self, node: ast.While):
        self._handle_loop(node)
        self.generic_visit(node)

    def _handle_loop(self, node):
        self.features.loop_count += 1
        self._loop_depth += 1
        self._max_loop_depth = max(self._max_loop_depth, self._loop_depth)
        if self._loop_depth >= 2:
            self.features.has_nested_loop = True

    def _after_loop(self, node):
        self._loop_depth -= 1

    def visit_If(self, node: ast.If):
        self.features.if_count += 1
        self.generic_visit(node)

    def visit_ListComp(self, node: ast.ListComp):
        self.features.has_list_comp = True
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call):
        # 递归检测
        if isinstance(node.func, ast.Name) and node.func.id == self._current_func:
            self.features.has_recursion = True
            if self._current_func not in self.features.recursive_funcs:
                self.features.recursive_funcs.append(self._current_func)
        self.generic_visit(node)

    # ---------- 死循环检测 ----------
    def _check_possible_infinite_loop(self):
        """简单启发式：while 循环条件为 True，且循环体内无 break"""
        try:
            tree = ast.parse(self.source)
        except SyntaxError:
            return

        for node in ast.walk(tree):
            if isinstance(node, ast.While):
                # 条件是常量 True
                if isinstance(node.test, ast.Constant) and node.test.value is True:
                    has_break = any(isinstance(s, ast.Break) for s in ast.walk(node))
                    if not has_break:
                        self.features.possible_infinite_loop = True
                        self.features.infinite_loop_hint = (
                            f"检测到 while True 循环（第 {node.lineno} 行），循环体内未发现 break 语句，"
                            "这可能导致死循环"
                        )

    # ---------- 复杂度估算 ----------
    def _estimate_complexity(self):
        f = self.features
        reason_parts = []

        if f.has_recursion:
            f.estimated_complexity = "O(2ⁿ) 或 O(n log n)"
            reason_parts.append(f"存在递归调用({', '.join(f.recursive_funcs)})，若递归树深度未控制，复杂度可能指数级增长")
        elif f.has_nested_loop:
            f.estimated_complexity = "O(n²) ~ O(n³)"
            reason_parts.append(f"嵌套循环最大深度 {f._max_loop_depth}，通常意味着平方/立方级复杂度")
        elif f.loop_count > 0:
            f.estimated_complexity = "O(n)"
            reason_parts.append(f"{f.loop_count} 层线性循环")
        else:
            f.estimated_complexity = "O(1)"
            reason_parts.append("无循环，常数时间复杂度")

        f.complexity_reason = "；".join(reason_parts)


def analyze_code(source: str) -> ASTFeatures:
    """对外入口"""
    analyzer = ASTAnalyzer(source)
    return analyzer.analyze()


def features_to_text(features: ASTFeatures) -> str:
    """将 AST 特征转换为可读文本（喂给 LLM 做解释）"""
    lines = []
    if not features.syntax_ok:
        lines.append(f"❌ 语法错误: {features.syntax_error}")
        return "\n".join(lines)

    lines.append(f"📊 代码统计: {features.line_count} 行, {features.function_count} 个函数, {features.class_count} 个类")
    lines.append(f"🔁 循环: {features.loop_count} 个, 最大嵌套深度 {features.max_loop_depth}")

    if features.has_recursion:
        lines.append(f"🌀 递归函数: {', '.join(features.recursive_funcs)}")

    if features.possible_infinite_loop:
        lines.append(f"⚠️ {features.infinite_loop_hint}")

    lines.append(f"📈 估算复杂度: {features.estimated_complexity}")
    lines.append(f"   依据: {features.complexity_reason}")

    if features.bad_names:
        lines.append(f"📝 命名规范: {'; '.join(features.bad_names[:3])}")

    return "\n".join(lines)
