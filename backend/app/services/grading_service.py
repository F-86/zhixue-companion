"""AI 批改服务 —— 业务编排层"""
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.db.repositories.grade import (
    grade_submission_db,
    upsert_grade_result,
    confirm_grade,
    get_grading_report,
)
from app.services.minimax_client import grade_submission as ai_grade


def grade_submissions(
    assignment_id: str,
    submission_ids: list[str],
    teacher_id: str,
    db: Session,
) -> dict:
    submissions_data = grade_submission_db(assignment_id, submission_ids, teacher_id, db)

    results = []
    for data in submissions_data:
        sub_id = data["submission_id"]
        content = data["content"]
        if not content:
            results.append({
                "submission_id": sub_id,
                "student_id": data["student_id"],
                "student_name": data["student_name"],
                "ai_score": None,
                "comments": "无法提取文本内容，请确认提交内容格式正确",
                "deductions": [],
                "suggestions": [],
                "confirmed": False,
                "error": "no_content",
            })
            continue

        ai_result = ai_grade(content, data["reference_answer"], data["rubric"], data["max_score"])
        grade = upsert_grade_result(sub_id, ai_result, db)
        results.append({
            "submission_id": sub_id,
            "student_id": data["student_id"],
            "student_name": data["student_name"],
            "ai_score": grade.ai_score,
            "comments": grade.comments,
            "deductions": grade.deductions,
            "suggestions": grade.suggestions,
            "confirmed": grade.confirmed,
        })

    return {"assignment_id": assignment_id, "results": results}
