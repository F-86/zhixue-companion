"""数据库操作层 —— 批改结果查询"""
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.assignment import Assignment
from app.models.file import File as FileModel
from app.models.grade import AIGradingResult
from app.models.submission import Submission, SubmissionFile
from app.models.user import User


def grade_submission_db(
    assignment_id: str,
    submission_ids: list[str],
    teacher_id: str,
    db: Session,
) -> list[dict]:
    """从数据库获取待批改的提交内容。"""
    a = db.get(Assignment, assignment_id)
    if not a or a.teacher_id != teacher_id:
        raise HTTPException(status_code=404, detail="作业不存在")
    results = []
    for sub_id in submission_ids:
        sub = db.get(Submission, sub_id)
        if not sub or sub.assignment_id != assignment_id:
            continue
        content = sub.content or ""
        if not content:
            sf_records = db.query(SubmissionFile).filter(
                SubmissionFile.submission_id == sub.id,
            ).all()
            file_ids = [sf.file_id for sf in sf_records]
            file_records = db.query(FileModel).filter(FileModel.id.in_(file_ids)).all() if file_ids else []
            extracted_parts = []
            for f in file_records:
                text = f.extracted_text
                if not text:
                    try:
                        from app.file_processing import extract_text
                        text = extract_text(f.file_path) or ""
                        if text:
                            f.extracted_text = text
                            db.commit()
                    except Exception:
                        pass
                if text:
                    extracted_parts.append(text)
            content = "\n\n".join(extracted_parts)
        student = db.get(User, sub.student_id)
        results.append({
            "submission_id": sub_id,
            "student_id": sub.student_id,
            "student_name": (student or User(name="未知")).name,
            "content": content,
            "reference_answer": a.reference_answer or "（无参考答案）",
            "rubric": a.rubric or "按照完整性、准确性和表达清晰度评分，满分 100 分。",
            "max_score": a.full_score if a.full_score > 0 else 100.0,
        })
    return results


def upsert_grade_result(submission_id: str, ai_result: dict, db: Session) -> AIGradingResult:
    """写入或更新 AI 批改结果。"""
    grade = db.query(AIGradingResult).filter(AIGradingResult.submission_id == submission_id).first()
    if grade:
        grade.ai_score = ai_result.get("ai_score")
        grade.comments = ai_result.get("comments")
        grade.deductions = ai_result.get("deductions", [])
        grade.suggestions = ai_result.get("suggestions", [])
        grade.confirmed = False
    else:
        grade = AIGradingResult(
            submission_id=submission_id,
            ai_score=ai_result.get("ai_score"),
            comments=ai_result.get("comments"),
            deductions=ai_result.get("deductions", []),
            suggestions=ai_result.get("suggestions", []),
        )
        db.add(grade)
    db.commit()
    db.refresh(grade)
    return grade


def confirm_grade(submission_id: str, final_score: float, confirmed: bool,
                   teacher_comment: str | None, db: Session) -> AIGradingResult:
    grade = db.query(AIGradingResult).filter(AIGradingResult.submission_id == submission_id).first()
    if not grade:
        raise HTTPException(status_code=404, detail="批改结果不存在，请先执行 AI 批改")
    grade.final_score = final_score
    grade.confirmed = confirmed
    grade.teacher_comment = teacher_comment
    db.commit()
    db.refresh(grade)
    return grade


def get_grading_report(assignment_id: str, teacher_id: str, db: Session) -> dict:
    a = db.get(Assignment, assignment_id)
    if not a or a.teacher_id != teacher_id:
        raise HTTPException(status_code=404, detail="作业不存在")
    subs = db.query(Submission).filter(Submission.assignment_id == assignment_id).all()
    grades = []
    for s in subs:
        g = db.query(AIGradingResult).filter(AIGradingResult.submission_id == s.id).first()
        if g:
            grades.append(g)
    if not grades:
        return {
            "assignment_id": assignment_id,
            "average_score": None,
            "graded_count": 0,
            "common_mistakes": [],
            "weak_points": [],
            "teaching_suggestions": [],
        }
    scores = [g.final_score or g.ai_score for g in grades if (g.final_score or g.ai_score) is not None]
    avg = sum(scores) / len(scores) if scores else None
    deduction_points = []
    for g in grades:
        for d in (g.deductions or []):
            if isinstance(d, dict):
                deduction_points.append(d.get("point", ""))
    from collections import Counter
    common = [p for p, _ in Counter(deduction_points).most_common(5) if p]
    return {
        "assignment_id": assignment_id,
        "average_score": round(avg, 1) if avg is not None else None,
        "graded_count": len(grades),
        "common_mistakes": common,
        "weak_points": [],
        "teaching_suggestions": [],
    }
