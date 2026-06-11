"""作业服务（课程路径版）"""
import os
from datetime import datetime

from fastapi import HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.assignment import Assignment
from app.models.grade import AIGradingResult
from app.models.submission import Submission
from app.models.user import User
from app.services.course_service import _require_enrollment, _require_teacher_course


def _section_info(section_id: str | None, db: Session) -> tuple[str | None, str | None]:
    """返回 (section_id, section_title)"""
    if not section_id:
        return None, None
    from app.models.section import Section
    s = db.get(Section, section_id)
    return (s.id, s.title) if s else (None, None)


def _require_assignment(assignment_id: str, course_id: str, db: Session) -> Assignment:
    a = db.get(Assignment, assignment_id)
    if not a or a.course_id != course_id:
        raise HTTPException(status_code=404, detail="作业不存在")
    return a


# ── 教师端：发布作业 ──────────────────────────────────────────

async def publish_assignment(
    course_id: str, section_id: str, teacher_id: str,
    title: str, description: str, due_at: datetime,
    reference_answer: str | None, rubric: str | None,
    full_score: float, attachment: UploadFile | None, db: Session,
) -> Assignment:
    _require_teacher_course(course_id, teacher_id, db)
    from app.models.course import Course
    course = db.get(Course, course_id)
    attachment_path = None
    attachment_text = None
    if attachment:
        ext = attachment.filename.rsplit(".", 1)[-1].lower() if "." in attachment.filename else "bin"
        import uuid
        fname = f"assignment_{uuid.uuid4()}.{ext}"
        fpath = os.path.join(settings.upload_dir, fname)
        content = await attachment.read()
        with open(fpath, "wb") as f:
            f.write(content)
        attachment_path = fpath
        # C++ 文件处理提取文本
        try:
            from app.services.file_processor_client import extract_text
            attachment_text = extract_text(fpath)
        except Exception:
            pass
    a = Assignment(
        teacher_id=teacher_id, course_id=course_id, section_id=section_id,
        title=title, course=course.name if course else "", full_score=full_score,
        description=description, reference_answer=reference_answer, rubric=rubric,
        attachment_path=attachment_path, attachment_text=attachment_text, due_at=due_at,
    )
    db.add(a)
    db.commit()
    db.refresh(a)
    return a


# ── 教师端：列表/详情/更新/关闭 ──────────────────────────────

def list_teacher_assignments(course_id: str, teacher_id: str,
                              section_id: str | None, status: str | None, db: Session) -> dict:
    _require_teacher_course(course_id, teacher_id, db)
    q = db.query(Assignment).filter(Assignment.course_id == course_id)
    if section_id:
        q = q.filter(Assignment.section_id == section_id)
    if status:
        q = q.filter(Assignment.status == status)
    assignments = q.order_by(Assignment.created_at.desc()).all()
    items = []
    for a in assignments:
        sid, stitle = _section_info(a.section_id, db)
        sub_count = db.query(Submission).filter(Submission.assignment_id == a.id).count()
        from app.models.course import CourseEnrollment
        student_count = db.query(CourseEnrollment).filter(CourseEnrollment.course_id == course_id).count()
        items.append({
            "id": a.id, "title": a.title, "section_id": sid, "section_title": stitle,
            "due_at": a.due_at, "full_score": a.full_score, "status": a.status,
            "submission_count": sub_count, "total_students": student_count,
        })
    return {"course_id": course_id, "items": items, "total": len(items)}


def get_teacher_assignment(course_id: str, assignment_id: str, teacher_id: str, db: Session) -> dict:
    _require_teacher_course(course_id, teacher_id, db)
    a = _require_assignment(assignment_id, course_id, db)
    sid, stitle = _section_info(a.section_id, db)
    sub_count = db.query(Submission).filter(Submission.assignment_id == a.id).count()
    attachment_url = f"/files/{os.path.basename(a.attachment_path)}" if a.attachment_path else None
    return {
        "id": a.id, "course_id": course_id, "section_id": sid,
        "title": a.title, "description": a.description,
        "reference_answer": a.reference_answer, "rubric": a.rubric,
        "due_at": a.due_at, "full_score": a.full_score, "status": a.status,
        "attachment_url": attachment_url, "submission_count": sub_count,
        "created_at": a.created_at, "updated_at": a.updated_at,
    }


def update_assignment(course_id: str, assignment_id: str, teacher_id: str,
                      description: str | None, due_at: datetime | None, db: Session) -> Assignment:
    _require_teacher_course(course_id, teacher_id, db)
    a = _require_assignment(assignment_id, course_id, db)
    if description is not None:
        a.description = description
    if due_at is not None:
        a.due_at = due_at
    db.commit()
    db.refresh(a)
    return a


def close_assignment(course_id: str, assignment_id: str, teacher_id: str, db: Session) -> Assignment:
    _require_teacher_course(course_id, teacher_id, db)
    a = _require_assignment(assignment_id, course_id, db)
    a.status = "closed"
    db.commit()
    db.refresh(a)
    return a


def list_submissions(course_id: str, assignment_id: str, teacher_id: str, db: Session) -> dict:
    _require_teacher_course(course_id, teacher_id, db)
    a = _require_assignment(assignment_id, course_id, db)
    subs = db.query(Submission).filter(Submission.assignment_id == assignment_id).all()
    items = []
    for s in subs:
        student = db.get(User, s.student_id)
        grade = db.query(AIGradingResult).filter(AIGradingResult.submission_id == s.id).first()
        items.append({
            "id": s.id, "student_id": s.student_id,
            "student_name": student.name if student else "",
            "submit_type": s.submit_type, "submitted_at": s.submitted_at,
            "status": s.status,
            "score": grade.final_score if grade and grade.confirmed else None,
            "confirmed": grade.confirmed if grade else False,
        })
    return {"assignment_id": assignment_id, "items": items, "total": len(items)}


# ── 学生端：列表/详情/提交/查看提交 ─────────────────────────

def list_student_assignments(course_id: str, student_id: str,
                              section_id: str | None, status: str | None, db: Session) -> dict:
    _require_enrollment(course_id, student_id, db)
    q = db.query(Assignment).filter(Assignment.course_id == course_id)
    if section_id:
        q = q.filter(Assignment.section_id == section_id)
    if status:
        q = q.filter(Assignment.status == status)
    assignments = q.order_by(Assignment.created_at.desc()).all()
    items = []
    for a in assignments:
        sid, stitle = _section_info(a.section_id, db)
        sub = db.query(Submission).filter(
            Submission.assignment_id == a.id,
            Submission.student_id == student_id,
        ).first()
        score = None
        if sub:
            grade = db.query(AIGradingResult).filter(
                AIGradingResult.submission_id == sub.id,
                AIGradingResult.confirmed == True,
            ).first()
            if grade:
                score = grade.final_score
        items.append({
            "id": a.id, "title": a.title, "section_id": sid, "section_title": stitle,
            "due_at": a.due_at, "full_score": a.full_score, "status": a.status,
            "submitted": sub is not None, "score": score,
        })
    return {"course_id": course_id, "items": items, "total": len(items)}


def get_student_assignment(course_id: str, assignment_id: str, student_id: str, db: Session) -> dict:
    _require_enrollment(course_id, student_id, db)
    a = _require_assignment(assignment_id, course_id, db)
    sid, stitle = _section_info(a.section_id, db)
    sub = db.query(Submission).filter(
        Submission.assignment_id == assignment_id,
        Submission.student_id == student_id,
    ).first()
    score = None
    if sub:
        grade = db.query(AIGradingResult).filter(
            AIGradingResult.submission_id == sub.id,
            AIGradingResult.confirmed == True,
        ).first()
        if grade:
            score = grade.final_score
    attachment_url = f"/files/{os.path.basename(a.attachment_path)}" if a.attachment_path else None
    return {
        "id": a.id, "course_id": course_id, "section_id": sid, "section_title": stitle,
        "title": a.title, "description": a.description,
        "due_at": a.due_at, "full_score": a.full_score, "status": a.status,
        "attachment_url": attachment_url, "submitted": sub is not None, "score": score,
    }


async def submit_assignment(
    course_id: str, assignment_id: str, student_id: str,
    submit_type: str, content: str | None, file: UploadFile | None, db: Session,
) -> Submission:
    _require_enrollment(course_id, student_id, db)
    a = _require_assignment(assignment_id, course_id, db)
    if a.status == "closed":
        raise HTTPException(status_code=400, detail="作业已关闭，不能提交")
    existing = db.query(Submission).filter(
        Submission.assignment_id == assignment_id,
        Submission.student_id == student_id,
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="已提交过该作业，不能重复提交")
    file_path = None
    extracted_text = None
    if submit_type == "file" and file:
        ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else "bin"
        import uuid
        fname = f"submission_{uuid.uuid4()}.{ext}"
        fpath = os.path.join(settings.upload_dir, fname)
        data = await file.read()
        with open(fpath, "wb") as f:
            f.write(data)
        file_path = fpath
        try:
            from app.services.file_processor_client import extract_text
            extracted_text = extract_text(fpath)
        except Exception:
            pass
    sub = Submission(
        assignment_id=assignment_id, student_id=student_id,
        submit_type=submit_type, content=content,
        file_path=file_path, extracted_text=extracted_text,
    )
    db.add(sub)
    db.commit()
    db.refresh(sub)
    return sub


def get_my_submission(course_id: str, assignment_id: str, student_id: str, db: Session) -> dict:
    _require_enrollment(course_id, student_id, db)
    _require_assignment(assignment_id, course_id, db)
    sub = db.query(Submission).filter(
        Submission.assignment_id == assignment_id,
        Submission.student_id == student_id,
    ).first()
    if not sub:
        raise HTTPException(status_code=404, detail="尚未提交该作业")
    grade = db.query(AIGradingResult).filter(AIGradingResult.submission_id == sub.id).first()
    file_url = f"/files/{os.path.basename(sub.file_path)}" if sub.file_path else None
    return {
        "id": sub.id, "assignment_id": assignment_id,
        "submit_type": sub.submit_type,
        "content": sub.content,
        "file_url": file_url,
        "file_urls": [file_url] if file_url else [],
        "submitted_at": sub.submitted_at, "status": sub.status,
        "score": grade.final_score if grade and grade.confirmed else None,
        "ai_score": grade.ai_score if grade else None,
        "comments": grade.comments if grade else None,
        "deductions": grade.deductions if grade else [],
        "suggestions": grade.suggestions if grade else [],
        "teacher_comment": grade.teacher_comment if grade else None,
        "graded_at": grade.created_at if grade else None,
    }
