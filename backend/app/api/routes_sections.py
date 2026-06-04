"""课程小节路由"""
import os
from datetime import datetime

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.services import section_service as svc
from app.services.auth_service import require_student, require_teacher

router = APIRouter(tags=["课程小节"])


def _ok(data, message="ok"):
    return {"success": True, "data": data, "message": message}


class SectionUpdateRequest(BaseModel):
    title: str | None = None
    description: str | None = None
    order: int | None = None


# ── 教师端 ────────────────────────────────────────────────────

@router.post("/teacher/courses/{course_id}/sections", status_code=201)
def create_section(
    course_id: str,
    title: str = Form(...),
    description: str | None = Form(None),
    order: int | None = Form(None),
    material: UploadFile | None = File(None),
    current_user=Depends(require_teacher),
    db: Session = Depends(get_db),
):
    s = svc.create_section(course_id, current_user.id, title, description, order, material, db)
    material_url = f"/files/{os.path.basename(s.material_path)}" if s.material_path else None
    return _ok({
        "id": s.id, "course_id": course_id, "title": s.title,
        "description": s.description, "order": s.order,
        "material_url": material_url, "assignment_count": 0,
        "created_at": s.created_at,
    }, "created")


@router.get("/teacher/courses/{course_id}/sections")
def list_teacher_sections(course_id: str, current_user=Depends(require_teacher), db: Session = Depends(get_db)):
    return _ok(svc.list_teacher_sections(course_id, current_user.id, db))


@router.patch("/teacher/courses/{course_id}/sections/{section_id}")
def update_section(course_id: str, section_id: str, req: SectionUpdateRequest,
                    current_user=Depends(require_teacher), db: Session = Depends(get_db)):
    s = svc.update_section(course_id, current_user.id, section_id, req.title, req.description, req.order, db)
    return _ok({"id": s.id, "title": s.title, "updated_at": s.updated_at}, "updated")


@router.delete("/teacher/courses/{course_id}/sections/{section_id}")
def delete_section(course_id: str, section_id: str,
                    current_user=Depends(require_teacher), db: Session = Depends(get_db)):
    svc.delete_section(course_id, current_user.id, section_id, db)
    return _ok({"id": section_id}, "deleted")


# ── 教师为小节发布作业 ────────────────────────────────────────

@router.post("/teacher/courses/{course_id}/sections/{section_id}/assignments", status_code=201)
async def publish_assignment(
    course_id: str,
    section_id: str,
    title: str = Form(...),
    description: str = Form(...),
    due_at: str = Form(...),
    reference_answer: str | None = Form(None),
    rubric: str | None = Form(None),
    full_score: float = Form(100.0),
    attachment: UploadFile | None = File(None),
    current_user=Depends(require_teacher),
    db: Session = Depends(get_db),
):
    try:
        due_dt = datetime.fromisoformat(due_at)
    except ValueError:
        raise HTTPException(status_code=400, detail="due_at 格式不合法，请使用 ISO 8601")
    from app.services.assignment_service import publish_assignment as pub
    a = await pub(course_id, section_id, current_user.id, title, description,
                  due_dt, reference_answer, rubric, full_score, attachment, db)
    attachment_url = f"/files/{os.path.basename(a.attachment_path)}" if a.attachment_path else None
    from app.models.section import Section
    sec = db.get(Section, section_id)
    return _ok({
        "id": a.id, "course_id": course_id, "section_id": section_id,
        "section_title": sec.title if sec else None,
        "title": a.title, "description": a.description,
        "due_at": a.due_at, "full_score": a.full_score,
        "status": a.status, "attachment_url": attachment_url,
        "created_at": a.created_at,
    }, "published")


# ── 学生端 ────────────────────────────────────────────────────

@router.get("/student/courses/{course_id}/sections")
def list_student_sections(course_id: str, current_user=Depends(require_student), db: Session = Depends(get_db)):
    return _ok(svc.list_student_sections(course_id, current_user.id, db))


@router.get("/student/courses/{course_id}/sections/{section_id}")
def get_student_section(course_id: str, section_id: str,
                         current_user=Depends(require_student), db: Session = Depends(get_db)):
    return _ok(svc.get_student_section(course_id, current_user.id, section_id, db))
