"""代码沙箱执行服务 — 双模式：Docker 强隔离 / subprocess 兜底

模式由 .env 的 SANDBOX_MODE 控制：
  - docker:     强制 Docker（不可用则报错）
  - subprocess: 直接本机执行（Windows Demo 默认）
  - auto:       检测到 Docker 可用就用 Docker，否则降级 subprocess
Docker 隔离参数：无网络、128MB 内存、0.5 CPU、64 进程数上限、只读挂载。
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


# 危险模块黑名单（subprocess 模式的软防线；Docker 模式另有强隔离）
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


# ---------------- Docker 可用性检测（带缓存） ----------------
_docker_ok: Optional[bool] = None


def _docker_available() -> bool:
    global _docker_ok
    if _docker_ok is None:
        try:
            r = subprocess.run(
                ["docker", "info"], capture_output=True, text=True, timeout=10
            )
            _docker_ok = (r.returncode == 0)
        except Exception:
            _docker_ok = False
        if _docker_ok:
            logger.info("🐳 检测到 Docker，沙箱启用容器强隔离")
        else:
            logger.warning("⚠️ Docker 不可用，沙箱降级为 subprocess 模式")
    return _docker_ok


def _pick_mode() -> str:
    mode = get_settings().sandbox_mode.lower()
    if mode == "docker":
        return "docker"
    if mode == "subprocess":
        return "subprocess"
    return "docker" if _docker_available() else "subprocess"


def _docker_cmd(tmp_file: str, image: str) -> list[str]:
    """构造 docker run 命令：无网络 + 资源限制 + 只读挂载"""
    host_path = os.path.abspath(tmp_file).replace("\\", "/")
    return [
        "docker", "run", "--rm", "-i",
        "--network", "none",
        "--memory", "128m",
        "--cpus", "0.5",
        "--pids-limit", "64",
        "--security-opt", "no-new-privileges",
        "-v", f"{host_path}:/code/user_code.py:ro",
        "-w", "/code",
        image,
        "python", "/code/user_code.py",
    ]


def _run(cmd: list[str], input_data: str, timeout: int) -> ExecuteResult:
    """统一执行入口，返回 ExecuteResult"""
    import time as _time
    start = _time.time()
    try:
        proc = subprocess.run(
            cmd,
            input=input_data,
            capture_output=True,
            text=True,
            timeout=timeout,
            env={"PATH": os.environ.get("PATH", ""), "PYTHONIOENCODING": "utf-8"},
        )
        elapsed = _time.time() - start
        if proc.returncode == 0:
            return ExecuteResult(success=True, output=proc.stdout, execution_time=elapsed)
        return ExecuteResult(
            success=False, output=proc.stdout, error=proc.stderr, execution_time=elapsed
        )
    except subprocess.TimeoutExpired:
        return ExecuteResult(
            success=False,
            error=f"⚠️ 代码执行超时（{timeout}秒），可能存在死循环",
            timed_out=True,
        )
    except Exception as e:
        return ExecuteResult(success=False, error=str(e))


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
    执行 Python 代码，捕获 stdout/stderr 和异常。
    Docker 模式下黑名单检查跳过（容器内无网络无文件系统可破坏），
    subprocess 模式下保留黑名单作为软防线。
    """
    cfg = get_settings()
    timeout = timeout or cfg.sandbox_timeout

    mode = _pick_mode()
    if mode == "subprocess":
        danger = _check_dangerous_imports(source)
        if danger:
            return ExecuteResult(success=False, error=danger)

    fd, tmp_file = tempfile.mkstemp(suffix=".py")
    os.close(fd)
    try:
        with open(tmp_file, "w", encoding="utf-8") as f:
            f.write(source)
        if mode == "docker":
            cmd = _docker_cmd(tmp_file, cfg.sandbox_docker_image)
            result = _run(cmd, "", timeout)
            # Docker 镜像缺失等场景：自动降级 subprocess
            err_l = (result.error or "").lower()
            if not result.timed_out and ("unable to find image" in err_l or "no such image" in err_l):
                logger.warning("Docker 镜像不可用，降级 subprocess 模式")
                global _docker_ok
                _docker_ok = False
                return _fallback_exec(source, timeout)
            return result
        return _fallback_exec(source, timeout)
    finally:
        if os.path.exists(tmp_file):
            try:
                os.remove(tmp_file)
            except Exception:
                pass


def _fallback_exec(source: str, timeout: int) -> ExecuteResult:
    """subprocess 直接执行（Windows Demo 模式）"""
    fd, tmp_file = tempfile.mkstemp(suffix=".py")
    os.close(fd)
    try:
        with open(tmp_file, "w", encoding="utf-8") as f:
            f.write(source)
        return _run([sys.executable, tmp_file], "", timeout)
    finally:
        if os.path.exists(tmp_file):
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
    mode = _pick_mode()
    if mode == "subprocess":
        danger = _check_dangerous_imports(source)
        if danger:
            return {"passed": 0, "total": 0, "error": danger, "details": []}

    cfg = get_settings()
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
            if mode == "docker":
                res = _run(_docker_cmd(tmp_file, cfg.sandbox_docker_image), input_data, 5)
                stdout, stderr, code, timed_out = res.output, res.error, (0 if res.success else 1), res.timed_out
            else:
                try:
                    proc = subprocess.run(
                        [sys.executable, tmp_file],
                        input=input_data,
                        capture_output=True,
                        text=True,
                        timeout=5,
                        env={"PATH": os.environ.get("PATH", ""), "PYTHONIOENCODING": "utf-8"},
                    )
                    stdout, stderr, code, timed_out = proc.stdout, proc.stderr, proc.returncode, False
                except subprocess.TimeoutExpired:
                    stdout, stderr, code, timed_out = "", "执行超时", 1, True

            actual = (stdout or "").strip()
            is_pass = code == 0 and actual == expected.strip() and not timed_out
            if is_pass:
                passed += 1
            results.append({
                "case": i + 1,
                "input": input_data,
                "expected": expected,
                "actual": actual,
                "passed": is_pass,
                "error": (stderr or "")[:200] if code != 0 or timed_out else None,
            })
    finally:
        if os.path.exists(tmp_file):
            try:
                os.remove(tmp_file)
            except Exception:
                pass

    return {"passed": passed, "total": len(test_cases), "details": results}
