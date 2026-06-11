"""成绩服务 —— 从 db.repositories.score 重导出"""
from app.db.repositories.score import (
    get_student_course_scores,
    get_all_course_scores,
    get_course_score_distribution,
    get_student_detail_score,
)
