"""教师端作业发布与管理服务"""
import os

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.assignment import Assignment
from app.models.file import File as FileModel
from app.models.grade import AIGradingResult
from app.models.submission import Submission, SubmissionFile
from app.models.user import User
from app.schemas.teacher_assignment import AssignmentUpdateRequest


def publish_assignment(
    teacher_id: str,
    title: str,
    course: str,
    description: str,
    due_at,
    reference_answer: str | None,
    rubric: str | None,
    attachment_file_id: str | None,
    db: Session,
) -> Assignment:
    attachment_path = None
    attachment_text = None

    if attachment_file_id:
        file_record = db.get(FileModel, attachment_file_id)
        if not file_record:
            raise HTTPException(status_code=400, detail="附件文件不存在，请先通过 /api/upload 上传")
        attachment_path = file_record.file_path
        attachment_text = file_record.extracted_text

    a = Assignment(
        teacher_id=teacher_id,
        title=title,
        course=course,
        description=description,
        reference_answer=reference_answer,
        rubric=rubric,
        attachment_file_id=attachment_file_id,
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
            "submission_count": sub_count, "total_students": 0,
        })
    return {"items": items, "total": len(items)}


def get_assignment(assignment_id: str, teacher_id: str, db: Session) -> dict:
    a = _get_own_assignment(assignment_id, teacher_id, db)
    sub_count = db.query(Submission).filter(Submission.assignment_id == a.id).count()
    attachment_url = _file_url(a.attachment_path) if a.attachment_path else None
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

        # 通过关联表拿到所有文件
        sf_records = (
            db.query(SubmissionFile)
            .filter(SubmissionFile.submission_id == s.id)
            .all()
        )
        file_ids = [sf.file_id for sf in sf_records]
        file_records = db.query(FileModel).filter(FileModel.id.in_(file_ids)).all() if file_ids else []
        file_map = {f.id: f for f in file_records}

        file_urls = [_file_url(file_map[fid].file_path) for fid in file_ids if fid in file_map]
        files_detail = [{
            "filename": file_map[fid].filename,
            "file_url": _file_url(file_map[fid].file_path),
            "file_size": file_map[fid].file_size,
        } for fid in file_ids if fid in file_map]
        extracted_text = "\n".join(
            file_map[fid].extracted_text for fid in file_ids
            if fid in file_map and file_map[fid].extracted_text
        ) or None

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


def _file_url(file_path: str) -> str:
    return f"/files/{os.path.basename(file_path)}"


def _get_own_assignment(assignment_id: str, teacher_id: str, db: Session) -> Assignment:
    a = db.get(Assignment, assignment_id)
    if not a:
        raise HTTPException(status_code=404, detail="作业不存在")
    if a.teacher_id != teacher_id:
        raise HTTPException(status_code=403, detail="无权操作此作业")
    return a
