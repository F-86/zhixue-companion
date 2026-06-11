"""教师端作业发布与管理服务"""
import os

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.assignment import Assignment
from app.models.submission import Submission, SubmissionFile
from app.models.user import User
from app.schemas.teacher_assignment import AssignmentUpdateRequest
from app.services import file_processor_client
from app.models.grade import AIGradingResult


def publish_assignment(
    teacher_id: str,
    title: str,
    course: str,
    description: str,
    due_at,
    reference_answer: str | None,
    rubric: str | None,
    attachment_url: str | None,
    db: Session,
) -> Assignment:
    attachment_path = None
    attachment_text = None

    if attachment_url:
        # 从 file_url（如 /files/uuid_name.pdf）解析出物理路径
        basename = os.path.basename(attachment_url)
        save_path = os.path.join(settings.upload_dir, basename)
        if not os.path.isfile(save_path):
            raise HTTPException(status_code=400, detail="附件文件不存在，请先通过 /api/upload 上传")
        attachment_path = save_path
        # C++ pybind11 解析题目文本
        attachment_text = file_processor_client.extract_text(save_path)

    a = Assignment(
        teacher_id=teacher_id,
        title=title,
        course=course,
        description=description,
        reference_answer=reference_answer,
        rubric=rubric,
        attachment_path=attachment_path,
        attachment_text=attachment_text,
        due_at=due_at,
    )
    db.add(a)
    db.commit()
    db.refresh(a)
    return a


def list_assignments(teacher_id: str, course: str | None, status: str | None, db: Session) -> dict:
    q = db.query(Assignment).filter(Assignment.teacher_id == teacher_id)
    if course:
        q = q.filter(Assignment.course == course)
    if status:
        q = q.filter(Assignment.status == status)
    assignments = q.order_by(Assignment.created_at.desc()).all()

    items = []
    for a in assignments:
        sub_count = db.query(Submission).filter(Submission.assignment_id == a.id).count()
        items.append({
            "id": a.id, "title": a.title, "course": a.course,
            "due_at": a.due_at, "status": a.status,
            "submission_count": sub_count, "total_students": 0,  # 可扩展班级人数
        })
    return {"items": items, "total": len(items)}


def get_assignment(assignment_id: str, teacher_id: str, db: Session) -> dict:
    a = _get_own_assignment(assignment_id, teacher_id, db)
    sub_count = db.query(Submission).filter(Submission.assignment_id == a.id).count()
    attachment_url = f"/files/{os.path.basename(a.attachment_path)}" if a.attachment_path else None
    return {
        "id": a.id, "title": a.title, "course": a.course,
        "description": a.description, "reference_answer": a.reference_answer,
        "rubric": a.rubric, "due_at": a.due_at, "status": a.status,
        "attachment_url": attachment_url, "submission_count": sub_count,
        "created_at": a.created_at, "updated_at": a.updated_at,
    }


def update_assignment(assignment_id: str, teacher_id: str, req: AssignmentUpdateRequest, db: Session) -> Assignment:
    a = _get_own_assignment(assignment_id, teacher_id, db)
    for field, value in req.model_dump(exclude_none=True).items():
        setattr(a, field, value)
    db.commit()
    db.refresh(a)
    return a


def close_assignment(assignment_id: str, teacher_id: str, db: Session) -> Assignment:
    a = _get_own_assignment(assignment_id, teacher_id, db)
    a.status = "closed"
    db.commit()
    db.refresh(a)
    return a


def list_submissions(assignment_id: str, teacher_id: str, db: Session) -> dict:
    _get_own_assignment(assignment_id, teacher_id, db)
    subs = db.query(Submission).filter(Submission.assignment_id == assignment_id).all()
    items = []
    for s in subs:
        student = db.get(User, s.student_id)
        grade = db.query(AIGradingResult).filter(AIGradingResult.submission_id == s.id).first()
        sf_records = db.query(SubmissionFile).filter(SubmissionFile.submission_id == s.id).all()
        file_urls = [f"/files/{os.path.basename(f.file_path)}" for f in sf_records]
        files_detail = [{
            "filename": f.filename,
            "file_url": f"/files/{os.path.basename(f.file_path)}",
            "file_size": f.file_size,
        } for f in sf_records]
        extracted_text = "\n".join(f.extracted_text for f in sf_records if f.extracted_text) or None
        items.append({
            "id": s.id, "student_id": s.student_id,
            "student_name": student.name if student else "未知",
            "submit_type": s.submit_type,
            "content": s.content,
            "extracted_text": extracted_text,
            "file_urls": file_urls,
            "files": files_detail,
            "submitted_at": s.submitted_at, "status": s.status,
            "score": grade.final_score if grade and grade.confirmed else None,
            "ai_score": grade.ai_score if grade else None,
            "confirmed": grade.confirmed if grade else False,
        })
    return {"assignment_id": assignment_id, "items": items, "total": len(items)}


def _get_own_assignment(assignment_id: str, teacher_id: str, db: Session) -> Assignment:
    a = db.get(Assignment, assignment_id)
    if not a:
        raise HTTPException(status_code=404, detail="作业不存在")
    if a.teacher_id != teacher_id:
        raise HTTPException(status_code=403, detail="无权操作此作业")
    return a
