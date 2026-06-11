"""作业管理路由（课程路径版）"""
import os
from datetime import datetime

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.services import assignment_service as svc
from app.services import grading_service, analyze_service
from app.services.auth_service import require_student, require_teacher

router = APIRouter(tags=["作业管理"])


def _ok(data, message="ok"):
    return {"success": True, "data": data, "message": message}


# ── 教师端 ────────────────────────────────────────────────────

@router.get("/teacher/courses/{course_id}/assignments")
def list_teacher_assignments(course_id: str, section_id: str | None = None, status: str | None = None,
                               current_user=Depends(require_teacher), db: Session = Depends(get_db)):
    return _ok(svc.list_teacher_assignments(course_id, current_user.id, section_id, status, db))


@router.get("/teacher/courses/{course_id}/assignments/{assignment_id}")
def get_teacher_assignment(course_id: str, assignment_id: str,
                            current_user=Depends(require_teacher), db: Session = Depends(get_db)):
    return _ok(svc.get_teacher_assignment(course_id, assignment_id, current_user.id, db))


class AssignmentUpdateRequest(BaseModel):
    description: str | None = None
    due_at: str | None = None


@router.patch("/teacher/courses/{course_id}/assignments/{assignment_id}")
def update_assignment(course_id: str, assignment_id: str, req: AssignmentUpdateRequest,
                       current_user=Depends(require_teacher), db: Session = Depends(get_db)):
    due_dt = None
    if req.due_at:
        try:
            due_dt = datetime.fromisoformat(req.due_at)
        except ValueError:
            raise HTTPException(status_code=400, detail="due_at 格式不合法")
    a = svc.update_assignment(course_id, assignment_id, current_user.id, req.description, due_dt, db)
    return _ok({"id": a.id, "description": a.description, "due_at": a.due_at, "updated_at": a.updated_at}, "updated")


@router.post("/teacher/courses/{course_id}/assignments/{assignment_id}/close")
def close_assignment(course_id: str, assignment_id: str,
                      current_user=Depends(require_teacher), db: Session = Depends(get_db)):
    a = svc.close_assignment(course_id, assignment_id, current_user.id, db)
    return _ok({"id": a.id, "status": a.status}, "closed")


@router.get("/teacher/courses/{course_id}/assignments/{assignment_id}/submissions")
def list_submissions(course_id: str, assignment_id: str,
                      current_user=Depends(require_teacher), db: Session = Depends(get_db)):
    return _ok(svc.list_submissions(course_id, assignment_id, current_user.id, db))


# ── AI 批改 ───────────────────────────────────────────────────

class GradeRequest(BaseModel):
    submission_ids: list[str]
    need_teacher_confirm: bool = True


class GradeConfirmRequest(BaseModel):
    final_score: float
    confirmed: bool
    teacher_comment: str | None = None


@router.post("/teacher/courses/{course_id}/assignments/{assignment_id}/grade")
def grade(course_id: str, assignment_id: str, req: GradeRequest,
           current_user=Depends(require_teacher), db: Session = Depends(get_db)):
    result = grading_service.grade_submissions(assignment_id, req.submission_ids, current_user.id, db)
    return _ok(result, "graded")


@router.patch("/teacher/courses/{course_id}/assignments/{assignment_id}/submissions/{submission_id}")
def confirm_grade(course_id: str, assignment_id: str, submission_id: str,
                   req: GradeConfirmRequest, current_user=Depends(require_teacher), db: Session = Depends(get_db)):
    grade = grading_service.confirm_grade(submission_id, req.final_score, req.confirmed, req.teacher_comment, db)
    return _ok({"submission_id": submission_id, "final_score": grade.final_score, "confirmed": grade.confirmed}, "updated")


@router.get("/teacher/courses/{course_id}/assignments/{assignment_id}/grading-report")
def grading_report(course_id: str, assignment_id: str,
                    current_user=Depends(require_teacher), db: Session = Depends(get_db)):
    return _ok(grading_service.get_grading_report(assignment_id, current_user.id, db))


# ── 查重与比对 ────────────────────────────────────────────────

class AnalyzeRequest(BaseModel):
    submission_ids: list[str]
    similarity_threshold: float = 0.8
    compare_dimensions: list[str] = ["structure", "concept", "expression", "conclusion"]


@router.post("/teacher/courses/{course_id}/assignments/{assignment_id}/analyze")
def analyze(course_id: str, assignment_id: str, req: AnalyzeRequest,
             current_user=Depends(require_teacher), db: Session = Depends(get_db)):
    report = analyze_service.analyze(
        assignment_id, req.submission_ids, current_user.id,
        req.similarity_threshold, req.compare_dimensions, db,
    )
    return _ok({
        "report_id": report.id, "assignment_id": report.assignment_id,
        "suspicious_pairs": report.suspicious_pairs,
        "comparison_details": report.comparison_details,
        "common_issues": report.common_issues,
        "teaching_suggestions": report.teaching_suggestions,
        "created_at": report.created_at,
    }, "analyzed")


@router.get("/teacher/courses/{course_id}/assignments/{assignment_id}/analyze-report")
def get_analyze_report(course_id: str, assignment_id: str,
                        current_user=Depends(require_teacher), db: Session = Depends(get_db)):
    report = analyze_service.get_report(assignment_id, current_user.id, db)
    return _ok({
        "report_id": report.id, "assignment_id": report.assignment_id,
        "suspicious_pairs": report.suspicious_pairs,
        "comparison_details": report.comparison_details,
        "common_issues": report.common_issues,
        "created_at": report.created_at,
    })


# ── 学生端 ────────────────────────────────────────────────────

@router.get("/student/courses/{course_id}/assignments")
def list_student_assignments(course_id: str, section_id: str | None = None, status: str | None = None,
                               current_user=Depends(require_student), db: Session = Depends(get_db)):
    return _ok(svc.list_student_assignments(course_id, current_user.id, section_id, status, db))


@router.get("/student/courses/{course_id}/assignments/{assignment_id}")
def get_student_assignment(course_id: str, assignment_id: str,
                            current_user=Depends(require_student), db: Session = Depends(get_db)):
    return _ok(svc.get_student_assignment(course_id, assignment_id, current_user.id, db))


@router.post("/student/courses/{course_id}/assignments/{assignment_id}/submit", status_code=201)
async def submit_assignment(
    course_id: str,
    assignment_id: str,
    submit_type: str = Form(...),
    content: str | None = Form(None),
    files: list[UploadFile] = File([]),
    current_user=Depends(require_student),
    db: Session = Depends(get_db),
):
    sub = await svc.submit_assignment(course_id, assignment_id, current_user.id, submit_type, content, files, db)
    return _ok({
        "id": sub.id, "assignment_id": assignment_id,
        "student_id": current_user.id, "submit_type": sub.submit_type,
        "submitted_at": sub.submitted_at, "status": sub.status,
    }, "submitted")


@router.get("/student/courses/{course_id}/assignments/{assignment_id}/my-submission")
def get_my_submission(course_id: str, assignment_id: str,
                       current_user=Depends(require_student), db: Session = Depends(get_db)):
    return _ok(svc.get_my_submission(course_id, assignment_id, current_user.id, db))
