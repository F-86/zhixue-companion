"""数据库操作层 —— 提交与文件查询"""
import logging
import os
from datetime import datetime

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.assignment import Assignment
from app.models.file import File as FileModel
from app.models.grade import AIGradingResult
from app.models.submission import Submission, SubmissionFile
from app.models.user import User

logger = logging.getLogger(__name__)


def file_url(file_path: str) -> str:
    if not file_path:
        return None
    return f"/files/{os.path.basename(file_path)}"


def require_assignment(assignment_id: str, course_id: str, db: Session) -> Assignment:
    a = db.get(Assignment, assignment_id)
    if not a or a.course_id != course_id:
        raise HTTPException(status_code=404, detail="作业不存在")
    return a


# ── 提交查询 ──────────────────────────────────────────────────

def submit_assignment(
    course_id: str, assignment_id: str, student_id: str,
    submit_type: str, content: str | None, file_ids: list[str], db: Session,
) -> Submission:
    a = require_assignment(assignment_id, course_id, db)
    if a.status == "closed":
        raise HTTPException(status_code=400, detail="作业已关闭，不能提交")
    existing = db.query(Submission).filter(
        Submission.assignment_id == assignment_id,
        Submission.student_id == student_id,
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="已提交过该作业，不能重复提交")
    sub = Submission(
        assignment_id=assignment_id, student_id=student_id,
        submit_type=submit_type, content=content,
    )
    db.add(sub)
    db.flush()
    if submit_type == "file" and file_ids:
        for file_id in file_ids:
            file_record = db.get(FileModel, file_id)
            if not file_record:
                raise HTTPException(status_code=400, detail=f"文件不存在：{file_id}，请先通过 /api/upload 上传")
            db.add(SubmissionFile(submission_id=sub.id, file_id=file_id))
    db.commit()
    db.refresh(sub)
    return sub


def submit_text(assignment_id: str, student_id: str, content: str, db: Session) -> Submission:
    check_can_submit(assignment_id, student_id, db)
    sub = Submission(
        assignment_id=assignment_id, student_id=student_id,
        submit_type="text", content=content,
    )
    db.add(sub)
    db.commit()
    db.refresh(sub)
    return sub


def submit_file_submission(assignment_id: str, student_id: str, file_ids: list[str],
                           db: Session, content: str | None = None) -> Submission:
    check_can_submit(assignment_id, student_id, db)
    actual_type = "mixed" if content else "file"
    sub = Submission(
        assignment_id=assignment_id, student_id=student_id,
        submit_type=actual_type, content=content,
    )
    db.add(sub)
    db.flush()
    logger.info("submit_file: assignment_id=%s, student_id=%s, file_ids=%s", assignment_id, student_id, file_ids)
    for file_id in file_ids:
        file_record = db.get(FileModel, file_id)
        if not file_record:
            raise HTTPException(status_code=400, detail=f"文件不存在：{file_id}，请先通过 /api/upload 上传")
        db.add(SubmissionFile(submission_id=sub.id, file_id=file_id))
    db.commit()
    db.refresh(sub)
    return sub


def get_my_submission(course_id: str, assignment_id: str, student_id: str, db: Session) -> dict:
    require_assignment(assignment_id, course_id, db)
    sub = db.query(Submission).filter(
        Submission.assignment_id == assignment_id,
        Submission.student_id == student_id,
    ).first()
    if not sub:
        raise HTTPException(status_code=404, detail="尚未提交该作业")
    grade = db.query(AIGradingResult).filter(AIGradingResult.submission_id == sub.id).first()
    sf_records = db.query(SubmissionFile).filter(SubmissionFile.submission_id == sub.id).all()
    file_ids = [sf.file_id for sf in sf_records]
    file_records = db.query(FileModel).filter(FileModel.id.in_(file_ids)).all() if file_ids else []
    file_map = {f.id: f for f in file_records}
    file_urls = [file_url(file_map[fid].file_path) for fid in file_ids if fid in file_map]
    files_detail = [{
        "filename": file_map[fid].filename,
        "file_url": file_url(file_map[fid].file_path),
        "file_size": file_map[fid].file_size,
    } for fid in file_ids if fid in file_map]
    return {
        "id": sub.id, "assignment_id": assignment_id,
        "submit_type": sub.submit_type,
        "content": sub.content,
        "file_urls": file_urls,
        "files": files_detail,
        "submitted_at": sub.submitted_at, "status": sub.status,
        "score": grade.final_score if grade and grade.confirmed else None,
        "ai_score": grade.ai_score if grade else None,
        "comments": grade.comments if grade else None,
        "deductions": grade.deductions if grade else [],
        "suggestions": grade.suggestions if grade else [],
        "teacher_comment": grade.teacher_comment if grade else None,
        "graded_at": grade.created_at if grade else None,
    }


def get_submission_for_student(assignment_id: str, student_id: str, db: Session) -> dict:
    sub = db.query(Submission).filter(
        Submission.assignment_id == assignment_id,
        Submission.student_id == student_id,
    ).first()
    if not sub:
        raise HTTPException(status_code=404, detail="尚未提交")
    sf_records = db.query(SubmissionFile).filter(SubmissionFile.submission_id == sub.id).all()
    file_ids = [sf.file_id for sf in sf_records]
    file_records = db.query(FileModel).filter(FileModel.id.in_(file_ids)).all() if file_ids else []
    file_map = {f.id: f for f in file_records}
    file_urls = [file_url(file_map[fid].file_path) for fid in file_ids if fid in file_map]
    files_detail = [{
        "filename": file_map[fid].filename,
        "file_url": file_url(file_map[fid].file_path),
        "file_size": file_map[fid].file_size,
    } for fid in file_ids if fid in file_map]
    grade = db.query(AIGradingResult).filter(AIGradingResult.submission_id == sub.id).first()
    return {
        "id": sub.id, "assignment_id": sub.assignment_id,
        "submit_type": sub.submit_type, "content": sub.content,
        "file_urls": file_urls, "files": files_detail,
        "submitted_at": sub.submitted_at, "status": sub.status,
        "score": grade.final_score if grade and grade.confirmed else None,
        "ai_score": grade.ai_score if grade else None,
        "comments": grade.comments if grade else None,
        "deductions": grade.deductions if grade else [],
        "suggestions": grade.suggestions if grade else [],
        "teacher_comment": grade.teacher_comment if grade else None,
        "graded_at": grade.created_at if grade else None,
    }


def check_can_submit(assignment_id: str, student_id: str, db: Session) -> None:
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


def list_submitted_assignment_ids(student_id: str, db: Session) -> set[str]:
    return {
        s.assignment_id
        for s in db.query(Submission.assignment_id)
        .filter(Submission.student_id == student_id)
        .all()
    }
