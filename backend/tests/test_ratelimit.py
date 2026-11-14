"""限流器单元测试"""
from app.core.ratelimit import RateLimiter


def test_allows_within_limit():
    rl = RateLimiter(3)
    assert rl.check("ip1")[0] is True
    assert rl.check("ip1")[0] is True
    assert rl.check("ip1")[0] is True


def test_blocks_over_limit():
    rl = RateLimiter(3)
    for _ in range(3):
        rl.check("ip2")
    ok, _ = rl.check("ip2")
    assert ok is False


def test_per_ip_isolation():
    rl = RateLimiter(1)
    assert rl.check("a")[0] is True
    assert rl.check("b")[0] is True      # 另一个 IP 不受影响
    assert rl.check("a")[0] is False     # a 已达上限
