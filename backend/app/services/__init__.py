"""
服务层 —— 业务逻辑编排。
纯数据库操作已迁移至 app.db.repositories，
本层仅保留需要跨模块协调或调用外部 API 的业务逻辑。
为保持向后兼容，从 db.repositories 重导出常用函数。
"""
# ── 认证（包含 FastAPI Depends） ───────────────────────────────
from app.db.repositories.user import (
    get_current_user,
    register_student,
    register_teacher,
    login,
    require_student,
    require_teacher,
)

# ── 课程 ─────────────────────────────────────────────────────
from app.db.repositories.course import (
    create_course,
    list_teacher_courses,
    get_teacher_course,
    update_course,
    archive_course,
    regenerate_code,
    list_course_students,
    add_students_by_username,
    remove_student,
    join_course,
    list_student_courses,
    get_student_course,
    quit_course,
    require_enrollment,
    require_teacher_course,
)

# ── 公告 ─────────────────────────────────────────────────────
from app.db.repositories.announcement import (
    create_announcement,
    list_teacher_announcements,
    update_announcement,
    get_teacher_announcement,
    delete_announcement,
    list_student_announcements,
    get_student_announcement,
)

# ── 作业 ─────────────────────────────────────────────────────
from app.db.repositories.assignment import (
    publish_assignment,
    list_teacher_assignments,
    get_teacher_assignment,
    update_assignment,
    close_assignment,
    list_submissions,
    list_student_assignments,
    get_student_assignment,
)

# ── 提交 ─────────────────────────────────────────────────────
from app.db.repositories.submission import (
    submit_assignment,
    get_my_submission,
)

# ── 讨论 ─────────────────────────────────────────────────────
from app.db.repositories.discussion import (
    create_discussion,
    list_discussions,
    get_discussion,
    add_reply,
    delete_reply,
    update_discussion_status,
    delete_discussion,
)

# ── 提问 ─────────────────────────────────────────────────────
from app.db.repositories.question import (
    create_question,
    list_questions,
    get_question,
    answer_question,
    update_visibility,
    delete_question,
)

# ── 小节 ─────────────────────────────────────────────────────
from app.db.repositories.section import (
    create_section,
    list_teacher_sections,
    update_section,
    delete_section,
    list_student_sections,
    get_student_section,
)

# ── 测试 ─────────────────────────────────────────────────────
from app.db.repositories.quiz import (
    create_quiz,
    list_teacher_quizzes,
    update_quiz_status,
    get_quiz_attempts_summary,
    list_student_quizzes,
    get_quiz_for_student,
    start_attempt,
    submit_attempt,
    save_answer,
    get_attempt_for_resume,
    get_attempt_result,
)

# ── 成绩 ─────────────────────────────────────────────────────
from app.db.repositories.score import (
    get_student_course_scores,
    get_all_course_scores,
    get_course_score_distribution,
    get_student_detail_score,
)

# ── 聊天（业务逻辑在 chat_service.py） ────────────────────────
from app.db.repositories.chat import (
    save_messages,
    get_session_messages,
    list_sessions,
)

# ── 知识点总结（业务逻辑在 summary_service.py） ──────────────
from app.db.repositories.summary import (
    create_summary_obj,
    list_summaries,
    get_summary_obj,
    delete_summary,
)

# ── 学习计划（业务逻辑在 learning_plan_service.py） ──────────
from app.db.repositories.learning_plan import (
    create_plan_obj,
    list_plans,
    get_plan,
    update_plan_status,
    archive_plan,
    create_new_version_plan,
)

# ── 计划进度（业务逻辑在 plan_progress_service.py） ──────────
from app.db.repositories.plan_progress import (
    mark_task,
    get_progress_map,
    list_progress_records,
)

# ── 批改结果 ─────────────────────────────────────────────────
from app.db.repositories.grade import (
    grade_submission_db,
    upsert_grade_result,
    confirm_grade,
    get_grading_report,
)

# ── 分析报告 ─────────────────────────────────────────────────
from app.db.repositories.analysis_report import (
    get_report_by_assignment,
    upsert_report,
)

# ── 文件 ─────────────────────────────────────────────────────
from app.db.repositories.file import (
    get_file,
    create_file_record,
)

# ── 外部客户端（保持在 services 层） ──────────────────────────
from app.services import minimax_client  # noqa: F401
