"""沙箱服务单元测试（subprocess 模式）"""
from app.services.sandbox_service import execute_python, run_test_cases


def test_hello_world():
    r = execute_python("print('hello sandbox')", timeout=5)
    assert r.success is True
    assert "hello sandbox" in r.output


def test_runtime_error_captured():
    r = execute_python("1 / 0", timeout=5)
    assert r.success is False
    assert "ZeroDivisionError" in r.error


def test_timeout_dead_loop():
    r = execute_python("while True:\n    pass", timeout=1)
    assert r.timed_out is True


def test_dangerous_import_blocked():
    r = execute_python("import os", timeout=5)
    assert r.success is False
    assert "禁止导入" in r.error


def test_test_cases_pass():
    code = "n = int(input())\nprint(n * 2)\n"
    res = run_test_cases(code, [
        {"input": "3", "expected": "6"},
        {"input": "10", "expected": "20"},
    ])
    assert res["passed"] == 2 and res["total"] == 2


def test_test_cases_fail_wrong_answer():
    code = "n = int(input())\nprint(n + 1)\n"
    res = run_test_cases(code, [{"input": "3", "expected": "6"}])
    assert res["passed"] == 0
    assert res["details"][0]["actual"] == "4"
