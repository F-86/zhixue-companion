"""测试服务 —— 从 db.repositories.quiz 重导出"""
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
    get_quiz_scores_for_signals,
    # 内部工具函数（测试依赖）
    is_correct as _is_correct,
)
