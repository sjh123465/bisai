"""代码分析 & 沙箱执行路由"""
from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional, List
from app.services.ast_service import analyze_code, features_to_text
from app.services.sandbox_service import execute_python, run_test_cases

router = APIRouter(prefix="/api/code", tags=["代码分析"])


class CodeRequest(BaseModel):
    code: str


class TestCase(BaseModel):
    input: str = ""
    expected: str


class CodeWithTests(BaseModel):
    code: str
    test_cases: List[TestCase]


@router.post("/analyze")
async def analyze(req: CodeRequest):
    """AST 静态分析"""
    feats = analyze_code(req.code)
    return {
        "features": feats.__dict__,
        "text": features_to_text(feats),
    }


@router.post("/execute")
async def execute(req: CodeRequest):
    """沙箱执行 Python 代码"""
    result = execute_python(req.code)
    return {
        "success": result.success,
        "output": result.output,
        "error": result.error,
        "timed_out": result.timed_out,
        "execution_time": round(result.execution_time, 3),
    }


@router.post("/test")
async def run_tests(req: CodeWithTests):
    """运行测试用例"""
    cases = [{"input": tc.input, "expected": tc.expected} for tc in req.test_cases]
    return run_test_cases(req.code, cases)


def _check_pep8(code: str, max_results: int = 20) -> dict:
    """PEP8 风格检查：优先用 pycodestyle，未安装时退回基础规则

    返回 {clean, issues:[{line, col, code, message}], summary}
    """
    try:
        import io
        import contextlib
        import pycodestyle
        out = io.StringIO()
        checker = pycodestyle.Checker(lines=code.splitlines(keepends=True))
        with contextlib.redirect_stdout(out):
            hit = checker.check_all()
        issues = []
        for raw in out.getvalue().splitlines()[:max_results]:
            # 形如：stdin:12:5: E501 line too long (92 > 79 characters)
            parts = raw.split(":", 3)
            if len(parts) == 4:
                issues.append({
                    "line": int(parts[1]) if parts[1].isdigit() else 0,
                    "col": int(parts[2]) if parts[2].isdigit() else 0,
                    "code": parts[3].strip().split(" ")[0],
                    "message": parts[3].strip(),
                })
        return {
            "clean": hit == 0,
            "issues": issues,
            "summary": "✅ 通过 PEP8 检查" if hit == 0 else f"发现 {len(issues)} 处风格问题",
        }
    except ImportError:
        # 降级：只查行宽 / Tab 缩进 / 行尾空格
        issues = []
        for i, line in enumerate(code.splitlines(), 1):
            if len(line) > 79:
                issues.append({"line": i, "col": 80, "code": "E501", "message": f"E501 行过长（{len(line)} > 79）"})
            if "\t" in line:
                issues.append({"line": i, "col": 1, "code": "W191", "message": "W191 使用 Tab 缩进"})
            if line != line.rstrip():
                issues.append({"line": i, "col": len(line.rstrip()) + 1, "code": "W291", "message": "W291 行尾多余空白"})
        issues = issues[:max_results]
        return {
            "clean": not issues,
            "issues": issues,
            "summary": "✅ 通过基础风格检查" if not issues else f"发现 {len(issues)} 处风格问题（基础模式）",
        }


@router.post("/style")
async def style_check(req: CodeRequest):
    """PEP8 风格检查"""
    return _check_pep8(req.code)
