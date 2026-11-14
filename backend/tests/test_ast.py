"""AST 分析服务单元测试"""
from app.services.ast_service import analyze_code


def test_nested_loop_complexity():
    code = """
def f(n):
    for i in range(n):
        for j in range(n):
            print(i, j)
"""
    f = analyze_code(code)
    assert f.max_loop_depth >= 2
    assert f.has_nested_loop is True
    assert "O(n^2)" in f.estimated_complexity or "O(n²)" in f.estimated_complexity


def test_recursion_detected():
    code = """
def fib(n):
    if n < 2:
        return n
    return fib(n-1) + fib(n-2)
"""
    f = analyze_code(code)
    assert f.has_recursion is True
    assert "fib" in f.recursive_funcs


def test_infinite_loop_detection():
    code = """
def f():
    while True:
        pass
"""
    f = analyze_code(code)
    assert f.possible_infinite_loop is True


def test_loop_variable_not_updated():
    code = """
def f():
    i = 0
    while i < 10:
        print(i)
"""
    f = analyze_code(code)
    assert f.possible_infinite_loop is True


def test_syntax_error_reported():
    f = analyze_code("def broken(:")
    assert f.syntax_ok is False
    assert f.syntax_error


def test_bad_naming():
    code = "def MyFunc(n):\n    return n"
    f = analyze_code(code)
    assert len(f.bad_names) >= 1


def test_sequential_loops_not_nested():
    """回归：两个顺序 for 不应被误判为嵌套（_after_loop 修复验证）"""
    code = """
def f(n):
    for i in range(n):
        print(i)
    for j in range(n):
        print(j)
"""
    f = analyze_code(code)
    assert f.max_loop_depth == 1
    assert f.has_nested_loop is False
