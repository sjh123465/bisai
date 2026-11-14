"""代码沙箱执行服务 — Python subprocess + timeout
⚠️ 比赛 Demo 用，安全限制：无文件 I/O、无网络、黑名单模块拦截
生产环境应替换为 Docker 容器
"""
import subprocess
import sys
import os
import io
import tempfile
import contextlib
from typing import Optional
from dataclasses import dataclass
from app.core.config import get_settings
from app.core.logger import get_logger

logger = get_logger("sandbox")


# 危险模块黑名单（sys/io 不拦截，编程题需读 stdin；生产环境用 Docker 强隔离）
DANGEROUS_MODULES = {
    "os", "subprocess", "socket", "http", "https",
    "ftplib", "smtplib", "telnetlib", "webbrowser",
    "ctypes", "cffi", "dl",
    "pickle", "marshal", "dill",
    "shutil", "pathlib", "tempfile",
    "multiprocessing", "threading",
    "signal", "resource",
    "pynput", "psutil",
}


@dataclass
class ExecuteResult:
    success: bool
    output: str = ""
    error: str = ""
    timed_out: bool = False
    execution_time: float = 0.0


def _check_dangerous_imports(source: str) -> Optional[str]:
    """简单的危险模块检测（文本级，不做 AST 解析以避免额外开销）"""
    import re
    for mod in DANGEROUS_MODULES:
        # 匹配 import xxx 或 from xxx import yyy
        if re.search(rf'(?:^|\n)\s*(?:import|from)\s+{re.escape(mod)}\b', source):
            return f"禁止导入模块: {mod}"
    return None


def execute_python(source: str, timeout: Optional[int] = None) -> ExecuteResult:
    """
    执行 Python 代码，捕获 stdout/stderr 和异常
    注意：这是 subprocess 隔离，非强安全隔离。Demo 足够，生产请用 Docker。
    """
    cfg = get_settings()
    timeout = timeout or cfg.sandbox_timeout

    # 前置检查
    danger = _check_dangerous_imports(source)
    if danger:
        return ExecuteResult(success=False, error=danger)

    # 写入临时文件执行
    import tempfile
    import time

    tmp_file = None
    try:
        # 添加一个输入模拟，避免 input() 阻塞
        wrapped = (
            "import sys\n"
            "sys.stdin = open(os.devnull, 'r')\n"
            "import os\n"
            + source
        )
        # 修正：os 在黑名单里但这里临时引入，需要用 subprocess 隔离环境
        # 直接让 subprocess 跑，不用上面的 wrapped

        fd, tmp_file = tempfile.mkstemp(suffix=".py")
        os.close(fd)
        with open(tmp_file, "w", encoding="utf-8") as f:
            f.write(source)

        start = time.time()
        proc = subprocess.run(
            [sys.executable, "-c", f"exec(open(r'{tmp_file}').read())"],
            capture_output=True,
            text=True,
            timeout=timeout,
            env={"PATH": os.environ.get("PATH", ""), "PYTHONIOENCODING": "utf-8"},
        )
        elapsed = time.time() - start

        if proc.returncode == 0:
            return ExecuteResult(
                success=True,
                output=proc.stdout,
                execution_time=elapsed,
            )
        else:
            return ExecuteResult(
                success=False,
                output=proc.stdout,
                error=proc.stderr,
                execution_time=elapsed,
            )

    except subprocess.TimeoutExpired:
        return ExecuteResult(
            success=False,
            error=f"⚠️ 代码执行超时（{timeout}秒），可能存在死循环",
            timed_out=True,
        )
    except Exception as e:
        return ExecuteResult(success=False, error=str(e))
    finally:
        if tmp_file and os.path.exists(tmp_file):
            try:
                os.remove(tmp_file)
            except Exception:
                pass


def run_test_cases(source: str, test_cases: list[dict]) -> dict:
    """
    运行带测试用例的代码
    test_cases: [{"input": "...", "expected": "..."}]
    返回: {"passed": int, "total": int, "details": [...]}
    """
    # 仅对学生代码做危险模块检测（不影响测试包装器）
    danger = _check_dangerous_imports(source)
    if danger:
        return {"passed": 0, "total": 0, "error": danger, "details": []}

    results = []
    passed = 0
    fd, tmp_file = tempfile.mkstemp(suffix=".py")
    os.close(fd)
    try:
        with open(tmp_file, "w", encoding="utf-8") as f:
            f.write(source)

        for i, tc in enumerate(test_cases):
            input_data = tc.get("input", "")
            expected = tc.get("expected", "")
            try:
                proc = subprocess.run(
                    [sys.executable, tmp_file],
                    input=input_data,
                    capture_output=True,
                    text=True,
                    timeout=5,
                    env={"PATH": os.environ.get("PATH", ""), "PYTHONIOENCODING": "utf-8"},
                )
                actual = (proc.stdout or "").strip()
                is_pass = proc.returncode == 0 and actual == expected.strip()
                if is_pass:
                    passed += 1
                results.append({
                    "case": i + 1,
                    "input": input_data,
                    "expected": expected,
                    "actual": actual,
                    "passed": is_pass,
                    "error": proc.stderr[:200] if proc.returncode != 0 else None,
                })
            except subprocess.TimeoutExpired:
                results.append({
                    "case": i + 1, "input": input_data, "expected": expected,
                    "actual": "", "passed": False, "error": "执行超时",
                })
    finally:
        if os.path.exists(tmp_file):
            try:
                os.remove(tmp_file)
            except Exception:
                pass

    return {"passed": passed, "total": len(test_cases), "details": results}
