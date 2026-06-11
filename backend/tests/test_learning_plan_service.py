"""
个性化学习计划服务测试。

测试目标：
  - _collect_signals：8 类信号采集（各信号独立覆盖，组合场景）
  - _rag_retrieve_for_plan：向量检索，含降级
  - create_plan：端到端计划生成主流程
  - 进度跟踪：mark_task / get_progress
  - 效果反馈：get_plan_effect
  - 多轮调整：adjust_plan

外部依赖（MiniMax API、向量库）全部 Mock。
"""
import uuid
from datetime import datetime, timezone, timedelta

import pytest

from app.services import learning_plan_service
from app.services import plan_progress_service
from app.models.learning_plan import LearningPlan
from app.models.plan_progress import PlanTaskProgress


# ─────────────────────────────────────────────────────────────
# 辅助：构造一个已有计划的场景
# ─────────────────────────────────────────────────────────────

def _make_plan(db, student_id: str, course_id: str, plan_items: list | None = None) -> LearningPlan:
    plan = LearningPlan(
        student_id=student_id,
        course_id=course_id,
        course="测试课程",
        version=1,
        parent_plan_id=None,
        status="active",
        data_sources=["scores", "profile"],
        basis={"available_time_per_day": 60},
        plan=plan_items or [
            {"day": 1, "task": "复习进程管理", "duration_minutes": 60, "section_id": "s1"},
            {"day": 2, "task": "完成调度算法练习", "duration_minutes": 60, "section_id": "s1"},
        ],
        analysis={"current_level": "基础", "weak_points": ["进程调度"]},
    )
    db.add(plan)
    db.commit()
    db.refresh(plan)
    return plan


# ─────────────────────────────────────────────────────────────
# _collect_signals 测试
# ─────────────────────────────────────────────────────────────

class TestCollectSignals:
    def test_empty_student_returns_empty_basis(self, db, make_user, make_course, enroll):
        """新学生没有任何数据，basis 应为空字典，data_sources 为空列表。"""
        teacher = make_user(role="teacher")
        student = make_user(role="student")
        course = make_course(teacher_id=teacher.id)
        enroll(course.id, student.id)

        basis, sources = learning_plan_service._collect_signals(course.id, student.id, db)
        assert basis == {}
        assert sources == []

    def test_profile_signal_collected(self, db, make_user, make_course, enroll):
        """学生有兴趣/岗位方向时，profile 信号应被采集。"""
        teacher = make_user(role="teacher")
        student = make_user(role="student", extra={
            "interests": ["算法", "数据库"],
            "career_direction": "backend",
        })
        course = make_course(teacher_id=teacher.id)
        enroll(course.id, student.id)

        basis, sources = learning_plan_service._collect_signals(course.id, student.id, db)
        assert "profile" in sources
        assert basis["profile"]["career_direction"] == "backend"
        assert "interests" in basis["profile"]

    def test_extra_fields_not_in_profile(self, db, make_user, make_course, enroll):
        """只有 interests 和 career_direction 被采集，其他 extra 字段应被过滤。"""
        teacher = make_user(role="teacher")
        student = make_user(role="student", extra={
            "career_direction": "frontend",
            "phone": "13800000000",  # 不应被采集
        })
        course = make_course(teacher_id=teacher.id)
        enroll(course.id, student.id)

        basis, _ = learning_plan_service._collect_signals(course.id, student.id, db)
        assert "phone" not in basis.get("profile", {})

    def test_chat_sessions_signal_collected(self, db, make_user, make_course, enroll):
        """有 AI 问答历史时，chat_sessions 信号应被采集。"""
        from app.models.chat import ChatMessage
        teacher = make_user(role="teacher")
        student = make_user(role="student")
        course = make_course(teacher_id=teacher.id)
        enroll(course.id, student.id)

        db.add(ChatMessage(
            user_id=student.id, session_id=str(uuid.uuid4()),
            course_id=course.id, section_id=None,
            role="user", content="进程调度算法有哪些？",
        ))
        db.commit()

        basis, sources = learning_plan_service._collect_signals(course.id, student.id, db)
        assert "chat_sessions" in sources
        assert "进程调度算法有哪些？" in basis["recent_questions"]

    def test_questions_signal_collected(self, db, make_user, make_course, enroll):
        """学生有向教师提问时，questions 信号应被采集。"""
        from app.models.question import Question
        teacher = make_user(role="teacher")
        student = make_user(role="student")
        course = make_course(teacher_id=teacher.id)
        enroll(course.id, student.id)

        db.add(Question(
            course_id=course.id, asked_by=student.id,
            title="阻塞态和挂起态有什么区别？",
            content="详细内容", visibility="public",
        ))
        db.commit()

        basis, sources = learning_plan_service._collect_signals(course.id, student.id, db)
        assert "questions" in sources
        assert "阻塞态和挂起态有什么区别？" in basis["questions_asked"]

    def test_summaries_signal_collected(self, db, make_user, make_course, enroll):
        """学生有知识点总结时，summaries 信号应被采集。"""
        from app.models.summary import Summary
        teacher = make_user(role="teacher")
        student = make_user(role="student")
        course = make_course(teacher_id=teacher.id)
        enroll(course.id, student.id)

        db.add(Summary(
            user_id=student.id, course_id=course.id, section_id=None,
            title="第一章总结", summary_type="structured",
            source_text="原始内容", result={}, rag_used=False,
        ))
        db.commit()

        basis, sources = learning_plan_service._collect_signals(course.id, student.id, db)
        assert "summaries" in sources
        assert "第一章总结" in basis["summaries"]

    def test_discussions_signal_collected(self, db, make_user, make_course, enroll):
        """学生参与讨论时，discussions 信号应被采集。"""
        from app.models.discussion import Discussion, DiscussionReply
        teacher = make_user(role="teacher")
        student = make_user(role="student")
        course = make_course(teacher_id=teacher.id)
        enroll(course.id, student.id)

        disc = Discussion(
            course_id=course.id, created_by=teacher.id,
            title="进程调度算法讨论", content="请分享你的理解。",
        )
        db.add(disc)
        db.flush()
        db.add(DiscussionReply(
            discussion_id=disc.id, author_id=student.id, content="我认为 SJF 更高效。",
        ))
        db.commit()

        basis, sources = learning_plan_service._collect_signals(course.id, student.id, db)
        assert "discussions" in sources
        assert "进程调度算法讨论" in basis["discussions_participated"]

    def test_quiz_records_signal_collected(self, db, make_user, make_course, enroll, mocker):
        """测试成绩信号应被采集（通过 mock quiz_service）。"""
        teacher = make_user(role="teacher")
        student = make_user(role="student")
        course = make_course(teacher_id=teacher.id)
        enroll(course.id, student.id)

        fake_quiz_records = [{
            "quiz_title": "进程管理小测",
            "score": 75.0,
            "full_score": 100.0,
            "wrong_questions": ["进程调度的基本单位是？"],
        }]
        mocker.patch(
            "app.db.repositories.quiz.get_quiz_scores_for_signals",
            return_value=fake_quiz_records,
        )

        basis, sources = learning_plan_service._collect_signals(course.id, student.id, db)
        assert "quizzes" in sources
        assert basis["quiz_records"][0]["quiz_title"] == "进程管理小测"

    def test_data_sources_only_includes_present_signals(self, db, make_user, make_course, enroll):
        """data_sources 中只应包含实际有数据的信号类型，不应包含空信号。"""
        teacher = make_user(role="teacher")
        student = make_user(role="student", extra={"career_direction": "backend"})
        course = make_course(teacher_id=teacher.id)
        enroll(course.id, student.id)

        _, sources = learning_plan_service._collect_signals(course.id, student.id, db)
        # 只有 profile，没有其他数据
        assert "profile" in sources
        assert "scores" not in sources
        assert "chat_sessions" not in sources


# ─────────────────────────────────────────────────────────────
# _rag_retrieve_for_plan 测试
# ─────────────────────────────────────────────────────────────

class TestRagRetrieveForPlan:
    def test_returns_results_for_weak_points(self, db, mocker):
        """薄弱知识点非空时，应调用向量检索并返回结果。"""
        fake_embedding = [0.1] * 1536
        fake_refs = [
            {"section_id": "s1", "section_title": "第一章", "file_name": "ch1.pdf",
             "excerpt": "进程状态相关内容", "score": 0.88},
        ]
        mocker.patch("app.services.minimax_client.embed_query", return_value=fake_embedding)
        mocker.patch("app.db.vector_store.query_chunks", return_value=fake_refs)

        result = learning_plan_service._rag_retrieve_for_plan(
            "course_1", ["进程状态转换", "调度算法"], db
        )
        assert result == fake_refs

    def test_returns_empty_for_empty_weak_points(self, db, mocker):
        """薄弱知识点为空时，不调用向量库，直接返回空列表。"""
        mock_embed = mocker.patch("app.services.minimax_client.embed_query")
        result = learning_plan_service._rag_retrieve_for_plan("course_1", [], db)
        assert result == []
        mock_embed.assert_not_called()

    def test_returns_empty_on_api_failure(self, db, mocker):
        """API 异常时，静默降级返回空列表。"""
        mocker.patch(
            "app.services.minimax_client.embed_query",
            side_effect=RuntimeError("API 超时"),
        )
        result = learning_plan_service._rag_retrieve_for_plan(
            "course_1", ["进程调度"], db
        )
        assert result == []

    def test_weak_points_joined_into_single_query(self, db, mocker):
        """多个薄弱知识点应拼接成一个查询字符串发给 Embedding API。"""
        mock_embed = mocker.patch(
            "app.services.minimax_client.embed_query",
            return_value=[0.1] * 1536,
        )
        mocker.patch("app.db.vector_store.query_chunks", return_value=[])

        learning_plan_service._rag_retrieve_for_plan(
            "course_1", ["进程调度", "内存分页"], db
        )
        # embed_query 被调用一次，参数包含两个薄弱点
        call_args = mock_embed.call_args[0][0]
        assert "进程调度" in call_args
        assert "内存分页" in call_args


# ─────────────────────────────────────────────────────────────
# create_plan 测试
# ─────────────────────────────────────────────────────────────

class TestCreatePlan:
    def _setup(self, db, make_user, make_course, enroll):
        teacher = make_user(role="teacher")
        student = make_user(role="student", extra={
            "career_direction": "backend",
            "interests": ["算法"],
        })
        course = make_course(teacher_id=teacher.id)
        enroll(course.id, student.id)
        return student, course

    def _mock_externals(self, mocker):
        mocker.patch("app.services.minimax_client.embed_query", return_value=[0.1] * 1536)
        mocker.patch("app.db.vector_store.query_chunks", return_value=[])
        mocker.patch(
            "app.db.repositories.quiz.get_quiz_scores_for_signals",
            return_value=[],
        )
        mocker.patch(
            "app.services.minimax_client.generate_learning_plan",
            return_value={
                "analysis": {
                    "current_level": "基础",
                    "weak_points": ["进程调度"],
                    "priority": "先复习进程调度",
                },
                "plan": [
                    {"day": 1, "task": "复习进程管理", "duration_minutes": 60},
                    {"day": 2, "task": "完成练习", "duration_minutes": 60},
                ],
            },
        )

    def test_create_plan_returns_plan_fields(self, db, make_user, make_course, enroll, mocker):
        """create_plan 应返回包含 id、plan、analysis 等字段的完整结果。"""
        student, course = self._setup(db, make_user, make_course, enroll)
        self._mock_externals(mocker)

        result = learning_plan_service.create_plan(
            course_id=course.id,
            student_id=student.id,
            goal="提升进程管理知识",
            available_time_per_day=60,
            db=db,
        )
        assert "id" in result
        assert result["course_id"] == course.id
        assert len(result["plan"]) == 2
        assert "analysis" in result
        assert "data_sources" in result

    def test_create_plan_persisted_to_db(self, db, make_user, make_course, enroll, mocker):
        """create_plan 应将计划写入数据库。"""
        student, course = self._setup(db, make_user, make_course, enroll)
        self._mock_externals(mocker)

        result = learning_plan_service.create_plan(
            course_id=course.id,
            student_id=student.id,
            goal=None,
            available_time_per_day=60,
            db=db,
        )
        plan_in_db = db.get(LearningPlan, result["id"])
        assert plan_in_db is not None
        assert plan_in_db.student_id == student.id
        assert plan_in_db.course_id == course.id

    def test_create_plan_includes_profile_in_data_sources(self, db, make_user, make_course, enroll, mocker):
        """有 career_direction 的学生，data_sources 应包含 profile。"""
        student, course = self._setup(db, make_user, make_course, enroll)
        self._mock_externals(mocker)

        result = learning_plan_service.create_plan(
            course_id=course.id,
            student_id=student.id,
            goal=None,
            available_time_per_day=60,
            db=db,
        )
        assert "profile" in result["data_sources"]

    def test_create_plan_includes_course_materials_when_rag_hits(self, db, make_user, make_course, enroll, mocker):
        """RAG 检索到材料时，data_sources 应包含 course_materials。"""
        student, course = self._setup(db, make_user, make_course, enroll)
        mocker.patch("app.services.minimax_client.embed_query", return_value=[0.1] * 1536)
        mocker.patch("app.db.vector_store.query_chunks", return_value=[
            {"section_id": "s1", "section_title": "第一章", "file_name": "ch1.pdf",
             "excerpt": "相关材料内容", "score": 0.9},
        ])
        mocker.patch("app.db.repositories.quiz.get_quiz_scores_for_signals", return_value=[
            {"quiz_title": "小测", "score": 60.0, "full_score": 100.0,
             "wrong_questions": ["进程调度基础题"]}
        ])
        mocker.patch(
            "app.services.minimax_client.generate_learning_plan",
            return_value={"analysis": {}, "plan": [{"day": 1, "task": "任务", "duration_minutes": 60}]},
        )

        result = learning_plan_service.create_plan(
            course_id=course.id,
            student_id=student.id,
            goal=None,
            available_time_per_day=60,
            db=db,
        )
        assert "course_materials" in result["data_sources"]

    def test_create_plan_raises_404_when_not_enrolled(self, db, make_user, make_course):
        """未加入课程时，create_plan 应抛出 HTTPException。"""
        from fastapi import HTTPException
        teacher = make_user(role="teacher")
        student = make_user(role="student")
        course = make_course(teacher_id=teacher.id)

        with pytest.raises(HTTPException):
            learning_plan_service.create_plan(
                course_id=course.id,
                student_id=student.id,
                goal=None,
                available_time_per_day=60,
                db=db,
            )


# ─────────────────────────────────────────────────────────────
# 进度跟踪：mark_task / get_progress
# ─────────────────────────────────────────────────────────────

class TestPlanProgress:
    def _setup(self, db, make_user, make_course, enroll):
        teacher = make_user(role="teacher")
        student = make_user(role="student")
        course = make_course(teacher_id=teacher.id)
        enroll(course.id, student.id)
        plan = _make_plan(db, student.id, course.id)
        return student, course, plan

    def test_mark_task_creates_progress_record(self, db, make_user, make_course, enroll):
        student, course, plan = self._setup(db, make_user, make_course, enroll)

        result = plan_progress_service.mark_task(
            course_id=course.id, plan_id=plan.id, student_id=student.id,
            day=1, completed=True, feedback="已掌握", db=db,
        )
        assert result["day"] == 1
        assert result["completed"] is True
        assert result["feedback"] == "已掌握"
        assert result["completed_at"] is not None

    def test_mark_task_updates_existing_record(self, db, make_user, make_course, enroll):
        """重复调用同一天任务应更新而非新建记录。"""
        student, course, plan = self._setup(db, make_user, make_course, enroll)

        plan_progress_service.mark_task(
            course_id=course.id, plan_id=plan.id, student_id=student.id,
            day=1, completed=False, feedback=None, db=db,
        )
        plan_progress_service.mark_task(
            course_id=course.id, plan_id=plan.id, student_id=student.id,
            day=1, completed=True, feedback="已掌握", db=db,
        )
        records = db.query(PlanTaskProgress).filter(
            PlanTaskProgress.plan_id == plan.id,
            PlanTaskProgress.day == 1,
        ).all()
        assert len(records) == 1  # 只有一条，不是两条
        assert records[0].completed is True

    def test_mark_task_invalid_day_raises(self, db, make_user, make_course, enroll):
        """标记不存在的 day 应抛出 HTTPException。"""
        from fastapi import HTTPException
        student, course, plan = self._setup(db, make_user, make_course, enroll)

        with pytest.raises(HTTPException):
            plan_progress_service.mark_task(
                course_id=course.id, plan_id=plan.id, student_id=student.id,
                day=99, completed=True, feedback=None, db=db,
            )

    def test_get_progress_returns_all_tasks(self, db, make_user, make_course, enroll):
        student, course, plan = self._setup(db, make_user, make_course, enroll)

        # 完成第 1 天
        plan_progress_service.mark_task(
            course_id=course.id, plan_id=plan.id, student_id=student.id,
            day=1, completed=True, feedback=None, db=db,
        )

        progress = plan_progress_service.get_progress(
            course_id=course.id, plan_id=plan.id, student_id=student.id, db=db,
        )
        assert progress["total_days"] == 2
        assert progress["completed_days"] == 1
        assert abs(progress["completion_rate"] - 0.5) < 1e-6
        assert len(progress["tasks"]) == 2

    def test_get_progress_uncompleted_task_has_false(self, db, make_user, make_course, enroll):
        """未完成的任务，completed 应为 False，feedback 和 completed_at 为 None。"""
        student, course, plan = self._setup(db, make_user, make_course, enroll)

        progress = plan_progress_service.get_progress(
            course_id=course.id, plan_id=plan.id, student_id=student.id, db=db,
        )
        for task in progress["tasks"]:
            assert task["completed"] is False
            assert task["feedback"] is None
            assert task["completed_at"] is None


# ─────────────────────────────────────────────────────────────
# 多轮调整：adjust_plan
# ─────────────────────────────────────────────────────────────

class TestAdjustPlan:
    def _setup(self, db, make_user, make_course, enroll):
        teacher = make_user(role="teacher")
        student = make_user(role="student")
        course = make_course(teacher_id=teacher.id)
        enroll(course.id, student.id)
        plan = _make_plan(db, student.id, course.id)
        return student, course, plan

    def test_adjust_archives_old_plan(self, db, make_user, make_course, enroll, mocker):
        """调整后旧计划状态应变为 archived。"""
        student, course, plan = self._setup(db, make_user, make_course, enroll)
        mocker.patch(
            "app.services.minimax_client.adjust_learning_plan",
            return_value={
                "analysis": {"adjustment_reason": "太难了", "completed_days": 0},
                "plan": [{"day": 1, "task": "简化任务", "duration_minutes": 45}],
            },
        )

        plan_progress_service.adjust_plan(
            course_id=course.id, plan_id=plan.id, student_id=student.id,
            feedback="太难了，希望简化", available_time_per_day=45, db=db,
        )

        db.refresh(plan)
        assert plan.status == "archived"

    def test_adjust_creates_new_plan_with_incremented_version(self, db, make_user, make_course, enroll, mocker):
        """调整后应创建新计划，version = 旧计划 version + 1。"""
        student, course, plan = self._setup(db, make_user, make_course, enroll)
        mocker.patch(
            "app.services.minimax_client.adjust_learning_plan",
            return_value={
                "analysis": {},
                "plan": [{"day": 1, "task": "新任务", "duration_minutes": 45}],
            },
        )

        result = plan_progress_service.adjust_plan(
            course_id=course.id, plan_id=plan.id, student_id=student.id,
            feedback="调整", available_time_per_day=None, db=db,
        )
        assert result["version"] == 2
        assert result["parent_plan_id"] == plan.id

    def test_adjust_non_active_plan_raises(self, db, make_user, make_course, enroll):
        """对已归档的计划进行调整应抛出 HTTPException。"""
        from fastapi import HTTPException
        student, course, plan = self._setup(db, make_user, make_course, enroll)
        plan.status = "archived"
        db.commit()

        with pytest.raises(HTTPException):
            plan_progress_service.adjust_plan(
                course_id=course.id, plan_id=plan.id, student_id=student.id,
                feedback="调整", available_time_per_day=None, db=db,
            )
