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
