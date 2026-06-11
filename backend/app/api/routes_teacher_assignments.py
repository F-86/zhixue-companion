import os
from datetime import datetime

from fastapi import APIRouter, Depends, Form, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.teacher_assignment import (
    AnalyzeRequest,
    AssignmentUpdateRequest,
    GradeConfirmRequest,
    GradeRequest,
)
from app.services import analyze_service, grading_service, teacher_assignment_service as svc
from app.services.auth_service import require_teacher

router = APIRouter(tags=["教师端作业"])


def _ok(data, message="ok"):
    return {"success": True, "data": data, "message": message}


# ── 发布与管理作业 ────────────────────────────────────────────

@router.post("/teacher/courses/{course_id}/assignments", status_code=201)
async def publish_assignment(
    course_id: str,
    title: str = Form(...),
    course: str = Form(...),
    description: str = Form(...),
    due_at: str = Form(...),
    reference_answer: str | None = Form(None),
    rubric: str | None = Form(None),
    attachment_file_id: str | None = Form(None),
    current_user=Depends(require_teacher),
    db: Session = Depends(get_db),
):
    try:
        due_dt = datetime.fromisoformat(due_at)
    except ValueError:
        raise HTTPException(status_code=400, detail="due_at 格式不合法，请使用 ISO 8601")

    a = svc.publish_assignment(
        course_id, course, current_user.id, title, description,
        due_dt, reference_answer, rubric, 100.0, attachment_file_id, db,
    )
    attachment_url = f"/files/{os.path.basename(a.attachment_path)}" if a.attachment_path else None
    return _ok({
        "id": a.id, "title": a.title, "course": a.course,
        "description": a.description, "due_at": a.due_at,
        "status": a.status, "attachment_url": attachment_url,
        "created_at": a.created_at,
    }, "published")


@router.get("/teacher/courses/{course_id}/assignments")
def list_assignments(
    course_id: str,
    course: str | None = None,
    status: str | None = None,
    current_user=Depends(require_teacher),
    db: Session = Depends(get_db),
):
    return _ok(svc.list_assignments(course_id, current_user.id, course, status, db))


@router.get("/teacher/courses/{course_id}/assignments/{assignment_id}")
def get_assignment(
    course_id: str,
    assignment_id: str,
    current_user=Depends(require_teacher),
    db: Session = Depends(get_db),
):
    return _ok(svc.get_assignment(course_id, assignment_id, current_user.id, db))


@router.patch("/teacher/courses/{course_id}/assignments/{assignment_id}")
def update_assignment(
    course_id: str,
    assignment_id: str,
    req: AssignmentUpdateRequest,
    current_user=Depends(require_teacher),
    db: Session = Depends(get_db),
):
    a = svc.update_assignment(course_id, assignment_id, current_user.id, req.description, req.due_at, db)
    return _ok({"id": a.id, "description": a.description, "due_at": a.due_at, "updated_at": a.updated_at}, "updated")


@router.post("/teacher/courses/{course_id}/assignments/{assignment_id}/close")
def close_assignment(
    course_id: str,
    assignment_id: str,
    current_user=Depends(require_teacher),
    db: Session = Depends(get_db),
):
    a = svc.close_assignment(course_id, assignment_id, current_user.id, db)
    return _ok({"id": a.id, "status": a.status}, "closed")


@router.get("/teacher/courses/{course_id}/assignments/{assignment_id}/submissions")
def list_submissions(
    course_id: str,
    assignment_id: str,
    current_user=Depends(require_teacher),
    db: Session = Depends(get_db),
):
    return _ok(svc.list_submissions(course_id, assignment_id, current_user.id, db))


@router.get("/teacher/courses/{course_id}/assignments/{assignment_id}/submissions/{submission_id}")
def get_submission_detail(
    course_id: str,
    assignment_id: str,
    submission_id: str,
    current_user=Depends(require_teacher),
    db: Session = Depends(get_db),
):
    result = svc.list_submissions(course_id, assignment_id, current_user.id, db)
    for item in result["items"]:
        if item["id"] == submission_id:
            return _ok(item)
    raise HTTPException(status_code=404, detail="提交不存在")


@router.patch("/teacher/courses/{course_id}/assignments/{assignment_id}/submissions/{submission_id}")
def update_submission_grade(
    course_id: str,
    assignment_id: str,
    submission_id: str,
    req: GradeConfirmRequest,
    current_user=Depends(require_teacher),
    db: Session = Depends(get_db),
):
    """确认/调整单份提交的评分（与 /teacher/submissions/{submission_id}/grade 等效）。"""
    grade = grading_service.confirm_grade(submission_id, req.final_score, req.confirmed, req.teacher_comment, db)
    return _ok({"submission_id": submission_id, "final_score": grade.final_score, "confirmed": grade.confirmed}, "updated")


# ── AI 批改 ───────────────────────────────────────────────────

@router.post("/teacher/courses/{course_id}/assignments/{assignment_id}/grade")
def grade(
    course_id: str,
    assignment_id: str,
    req: GradeRequest,
    current_user=Depends(require_teacher),
    db: Session = Depends(get_db),
):
    result = grading_service.grade_submissions(assignment_id, req.submission_ids, current_user.id, db)
    return _ok(result, "graded")


@router.patch("/teacher/submissions/{submission_id}/grade")
def confirm_grade(
    submission_id: str,
    req: GradeConfirmRequest,
    current_user=Depends(require_teacher),
    db: Session = Depends(get_db),
):
    grade = grading_service.confirm_grade(submission_id, req.final_score, req.confirmed, req.teacher_comment, db)
    return _ok({"submission_id": submission_id, "final_score": grade.final_score, "confirmed": grade.confirmed}, "updated")


@router.get("/teacher/courses/{course_id}/assignments/{assignment_id}/grading-report")
def grading_report(
    course_id: str,
    assignment_id: str,
    current_user=Depends(require_teacher),
    db: Session = Depends(get_db),
):
    return _ok(grading_service.get_grading_report(assignment_id, current_user.id, db))


# ── 查重与比对 ────────────────────────────────────────────────

@router.post("/teacher/courses/{course_id}/assignments/{assignment_id}/analyze")
def analyze(
    course_id: str,
    assignment_id: str,
    req: AnalyzeRequest,
    current_user=Depends(require_teacher),
    db: Session = Depends(get_db),
):
    report = analyze_service.analyze(
        assignment_id, req.submission_ids, current_user.id,
        req.similarity_threshold, req.compare_dimensions, db,
    )
    return _ok({
        "report_id": report.id,
        "assignment_id": report.assignment_id,
        "suspicious_pairs": report.suspicious_pairs,
        "comparison_details": report.comparison_details,
        "common_issues": report.common_issues,
        "teaching_suggestions": report.teaching_suggestions,
        "created_at": report.created_at,
    }, "analyzed")


@router.get("/teacher/courses/{course_id}/assignments/{assignment_id}/analyze-report")
def get_analyze_report(
    course_id: str,
    assignment_id: str,
    current_user=Depends(require_teacher),
    db: Session = Depends(get_db),
):
    report = analyze_service.get_report(assignment_id, current_user.id, db)
    return _ok({
        "report_id": report.id,
        "assignment_id": report.assignment_id,
        "suspicious_pairs": report.suspicious_pairs,
        "comparison_details": report.comparison_details,
        "common_issues": report.common_issues,
        "created_at": report.created_at,
    })
