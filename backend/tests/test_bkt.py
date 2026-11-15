"""BKT 知识追踪单元测试"""
import uuid
from app.services.bkt_service import BKTService


def _fresh_bkt():
    """每次用新的 BKTService 实例 + 随机学生 ID，避免测试间污染"""
    return BKTService(), f"t_{uuid.uuid4().hex[:8]}"


def test_initial_mastery():
    bkt, sid = _fresh_bkt()
    bkt.record_answer(sid, "quick_sort", False)
    # 首答错：0.3 - 0.10 = 0.20
    assert abs(bkt.get_mastery(sid)["quick_sort"] - 0.20) < 1e-6


def test_correct_increases():
    bkt, sid = _fresh_bkt()
    bkt.record_answer(sid, "link", True)
    assert abs(bkt.get_mastery(sid)["link"] - 0.45) < 1e-6


def test_clamped_bounds():
    bkt, sid = _fresh_bkt()
    for _ in range(50):
        bkt.record_answer(sid, "graph", False)
    assert bkt.get_mastery(sid)["graph"] >= 0.05
    for _ in range(50):
        bkt.record_answer(sid, "graph", True)
    assert bkt.get_mastery(sid)["graph"] <= 0.98


def test_weak_points_ordering():
    bkt, sid = _fresh_bkt()
    bkt.record_answer(sid, "easy_topic", True)
    bkt.record_answer(sid, "easy_topic", True)
    bkt.record_answer(sid, "hard_topic", False)
    bkt.record_answer(sid, "hard_topic", False)
    weak = bkt.get_weak_points(sid)
    assert weak and weak[0]["concept_id"] == "hard_topic"


def test_history_recorded():
    bkt, sid = _fresh_bkt()
    bkt.record_answer(sid, "dp", True)
    assert len(bkt._history.get(sid, [])) == 1


def test_wrongbook_does_not_double_deduct_bkt():
    """回归：错题本 add() 不应再次联动 BKT，否则答错会扣两次分。"""
    from app.services.wrongbook_service import WrongBookService
    from app.services.bkt_service import get_bkt

    sid = f"t_{uuid.uuid4().hex[:8]}"
    wb = WrongBookService()
    wb.record_result(sid, "quick_sort", {"question": "test"}, "A", False)
    bkt = get_bkt()
    assert abs(bkt.get_mastery(sid)["quick_sort"] - 0.20) < 1e-6
    assert len(bkt._history.get(sid, [])) == 1
