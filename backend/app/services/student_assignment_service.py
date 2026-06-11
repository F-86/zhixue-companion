"""学生端作业服务：查看作业、提交作业"""
import os

from fastapi import HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.assignment import Assignment
from app.models.grade import AIGradingResult
from app.models.submission import Submission, SubmissionFile
from app.services import file_processor_client


def list_assignments(student_id: str, course: str | None, status: str | None, db: Session) -> dict:
    q = db.query(Assignment)
    if course:
        q = q.filter(Assignment.course == course)
    if status:
        q = q.filter(Assignment.status == status)
    assignments = q.order_by(Assignment.due_at).all()

    # 查询该学生已提交的作业 ID 集合
    submitted_ids = {
        s.assignment_id
        for s in db.query(Submission.assignment_id)
        .filter(Submission.student_id == student_id)
        .all()
    }

    items = []
    for a in assignments:
        items.append({
            "id": a.id,
            "title": a.title,
            "course": a.course,
            "due_at": a.due_at,
            "status": a.status,
            "submitted": a.id in submitted_ids,
        })
    return {"items": items, "total": len(items)}


def get_assignment_detail(assignment_id: str, student_id: str, db: Session) -> dict:
    a = db.get(Assignment, assignment_id)
    if not a:
        raise HTTPException(status_code=404, detail="作业不存在")
    submitted = bool(
        db.query(Submission)
        .filter(Submission.assignment_id == assignment_id, Submission.student_id == student_id)
        .first()
    )
    attachment_url = f"/files/{os.path.basename(a.attachment_path)}" if a.attachment_path else None
    return {
        "id": a.id,
        "title": a.title,
        "course": a.course,
        "description": a.description,
        "due_at": a.due_at,
        "status": a.status,
        "attachment_url": attachment_url,
        "submitted": submitted,
    }


def submit_text(assignment_id: str, student_id: str, content: str, db: Session) -> Submission:
    _check_can_submit(assignment_id, student_id, db)
    sub = Submission(
        assignment_id=assignment_id,
        student_id=student_id,
        submit_type="text",
        content=content,
    )
    db.add(sub)
    db.commit()
    db.refresh(sub)
    return sub


def submit_file(assignment_id: str, student_id: str, files: list[UploadFile], db: Session) -> Submission:
    _check_can_submit(assignment_id, student_id, db)
    for file in files:
        _validate_file(file)

    sub = Submission(
        assignment_id=assignment_id,
        student_id=student_id,
        submit_type="file",
    )
    db.add(sub)
    db.flush()  # 获取 sub.id

    for file in files:
        filename = f"{student_id}_{assignment_id}_{sub.id}_{file.filename}"
        save_path = os.path.join(settings.upload_dir, filename)
        content_bytes = file.file.read()
        with open(save_path, "wb") as f:
            f.write(content_bytes)
        # C++ pybind11 提取文本
        extracted = file_processor_client.extract_text(save_path)
        db.add(SubmissionFile(
            submission_id=sub.id,
            filename=file.filename or "unknown",
            file_path=save_path,
            file_size=len(content_bytes),
            extracted_text=extracted,
        ))
    db.commit()
    db.refresh(sub)
    return sub


def get_my_submission(assignment_id: str, student_id: str, db: Session) -> dict:
    sub = (
        db.query(Submission)
        .filter(Submission.assignment_id == assignment_id, Submission.student_id == student_id)
        .first()
    )
    if not sub:
        raise HTTPException(status_code=404, detail="尚未提交")
    sf_records = db.query(SubmissionFile).filter(SubmissionFile.submission_id == sub.id).all()
    file_urls = [f"/files/{os.path.basename(f.file_path)}" for f in sf_records]
    files_detail = [{
        "filename": f.filename,
        "file_url": f"/files/{os.path.basename(f.file_path)}",
        "file_size": f.file_size,
    } for f in sf_records]
    grade = db.query(AIGradingResult).filter(AIGradingResult.submission_id == sub.id).first()
    return {
        "id": sub.id,
        "assignment_id": sub.assignment_id,
        "submit_type": sub.submit_type,
        "content": sub.content,
        "file_urls": file_urls,
        "files": files_detail,
        "submitted_at": sub.submitted_at,
        "status": sub.status,
        "score": grade.final_score if grade and grade.confirmed else None,
        "ai_score": grade.ai_score if grade else None,
        "comments": grade.comments if grade else None,
        "deductions": grade.deductions if grade else [],
        "suggestions": grade.suggestions if grade else [],
        "teacher_comment": grade.teacher_comment if grade else None,
        "graded_at": grade.created_at if grade else None,
    }


# ── 内部工具 ──────────────────────────────────────────────────

def _check_can_submit(assignment_id: str, student_id: str, db: Session) -> None:
    a = db.get(Assignment, assignment_id)
    if not a:
        raise HTTPException(status_code=404, detail="作业不存在")
    if a.status == "closed":
        raise HTTPException(status_code=400, detail="作业已关闭，不可提交")
    if db.query(Submission).filter(
        Submission.assignment_id == assignment_id,
        Submission.student_id == student_id,
    ).first():
        raise HTTPException(status_code=400, detail="已提交过，不可重复提交")


def _validate_file(file: UploadFile) -> None:
    ext = (file.filename or "").rsplit(".", 1)[-1].lower()
    if ext not in settings.allowed_extensions:
        raise HTTPException(status_code=400, detail=f"不支持的文件格式：{ext}")
    file.file.seek(0, 2)
    size = file.file.tell()
    file.file.seek(0)
    if size > settings.max_upload_bytes:
        raise HTTPException(status_code=400, detail="文件超过 10 MB 限制")
