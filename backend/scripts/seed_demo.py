"""生成教师班级作业演示数据（不需要任何 API Key）。

用法（在 backend/ 目录）：
    python scripts/seed_demo.py

会创建/复用：
- 教师 teacher 的「演示班（自动生成）」
- 学生 student + demo_01..demo_08 的班级成员关系
- 一份统一作业（选择 + 判断 + 编程），以及 8 名演示学生的提交
- student 账号保留未提交状态，便于现场演示“学生作答 → 教师看板”闭环
"""
import os
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
os.chdir(BACKEND)

from app.core.security import get_user_store  # noqa: E402
from app.plugins.base import GradingCriterion, GradingPlan, Question, TestCase  # noqa: E402
from app.services.classroom_service import ClassroomError, get_classroom  # noqa: E402

CLASS_NAME = "演示班（自动生成）"
ASSIGNMENT_TITLE = "演示作业：排序与 BST"
DEMO_STUDENTS = ["student"] + [f"demo_{i:02d}" for i in range(1, 9)]


def _questions() -> list[Question]:
    q1 = Question(
        id="q_demo_quick_sort",
        type="choice",
        concept="快速排序",
        concept_id="quick_sort",
        concept_ids=["quick_sort"],
        question="快速排序的平均时间复杂度是？",
        options=["A. O(n²)", "B. O(n log n)", "C. O(n)", "D. O(1)"],
        answer="B",
        explanation="快速排序平均 O(n log n)，最坏 O(n²)。",
        difficulty="easy",
        grading_plan=GradingPlan(
            method="objective",
            answer_key="B",
            accepted_answers=["B", "B. O(n log n)"],
            pass_threshold=0.6,
            criteria=[GradingCriterion(id="correctness", description="答案是否匹配", weight=1.0, kind="answer")],
        ),
    )
    q2 = Question(
        id="q_demo_bst",
        type="judge",
        concept="二叉搜索树",
        concept_id="binary_search_tree",
        concept_ids=["binary_search_tree"],
        question="二叉搜索树的中序遍历结果是有序的。",
        answer=True,
        explanation="BST 中序遍历按左-根-右访问，得到升序序列。",
        difficulty="easy",
        grading_plan=GradingPlan(
            method="objective",
            answer_key=True,
            accepted_answers=["正确", "true"],
            pass_threshold=0.6,
            criteria=[GradingCriterion(id="correctness", description="答案是否匹配", weight=1.0, kind="answer")],
        ),
    )
    q3 = Question(
        id="q_demo_double",
        type="code",
        concept="输入输出",
        concept_id="array",
        concept_ids=["array"],
        question="读入一个整数 n，输出它的两倍。",
        function_name="solve",
        input_desc="一个整数 n",
        output_desc="2n",
        test_cases=[TestCase(input="3", expected="6"), TestCase(input="10", expected="20")],
        hint="读取 input() 后转 int。",
        difficulty="easy",
        grading_plan=GradingPlan(
            method="test_cases",
            pass_threshold=0.6,
            criteria=[
                GradingCriterion(id="tests_pass", description="通过测试用例比例", weight=0.8, kind="tests_pass"),
                GradingCriterion(id="no_infinite_loop", description="无死循环", weight=0.1, kind="no_infinite_loop"),
                GradingCriterion(id="pep8", description="基础风格", weight=0.1, kind="pep8"),
            ],
        ),
    )
    return [q1, q2, q3]


def main():
    get_user_store()  # 确保 teacher/student 演示账号存在
    store = get_classroom()

    classes = store.list_classes_for_teacher("teacher")
    cls = next((c for c in classes if c.get("name") == CLASS_NAME), None)
    if not cls:
        cls = store.create_class("teacher", CLASS_NAME)
        print(f"创建班级: {cls['name']} / 邀请码 {cls['join_code']}")
    else:
        print(f"复用班级: {cls['name']} / 邀请码 {cls['join_code']}")

    for sid in DEMO_STUDENTS:
        try:
            store.join_class(cls["join_code"], sid)
        except ClassroomError:
            pass

    assignments = store.list_assignments_for_teacher("teacher", cls["id"])
    row = next((a for a in assignments if a.get("title") == ASSIGNMENT_TITLE), None)
    if row:
        aid = row["id"]
        print(f"复用作业: {ASSIGNMENT_TITLE} ({aid})")
    else:
        assignment = store.create_assignment(
            teacher_id="teacher",
            title=ASSIGNMENT_TITLE,
            class_ids=[cls["id"]],
            questions=[q.model_dump(mode="json") for q in _questions()],
            scenario="demo",
            generator="llm_default@1",
            grader="plan_based@1",
        )
        aid = assignment["id"]
        print(f"创建作业: {ASSIGNMENT_TITLE} ({aid})")

    detail = store.get_assignment_for_teacher(aid, "teacher")
    submitted = set(detail.get("submissions", {}).keys())
    correct_code = "n = int(input())\nprint(n * 2)\n"
    wrong_code = "print(0)\n"

    for idx, sid in enumerate(DEMO_STUDENTS):
        if sid == "student" or sid in submitted:
            continue
        # 制造不同正确率，便于演示热力图/错题榜
        answers = {
            "q_demo_quick_sort": "B" if idx % 3 else "A",
            "q_demo_bst": "正确" if idx % 4 else "错误",
            "q_demo_double": correct_code if idx % 3 else wrong_code,
        }
        try:
            result = store.submit_assignment(aid, sid, answers)
            print(f"  演示提交 {sid}: {result['score']} 分")
        except ClassroomError as e:
            print(f"  跳过 {sid}: {e}")

    print("\n✅ 演示数据就绪")
    print(f"   教师: teacher / 123456")
    print(f"   学生: student / 123456（保留未提交统一作业，便于现场作答）")
    print(f"   班级邀请码: {cls['join_code']}")
    print("   打开前端 → 配置自己的模型 Key（仅用于 AI 对话/出题）→ 登录体验")


if __name__ == "__main__":
    main()
