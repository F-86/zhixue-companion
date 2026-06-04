"""提问服务"""
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.question import Question, QuestionAnswer
from app.models.user import User
from app.services.course_service import _require_enrollment, _require_teacher_course


def _section_title(section_id: str | None, db: Session) -> str | None:
    if not section_id:
        return None
    from app.models.section import Section
    s = db.get(Section, section_id)
    return s.title if s else None


def _require_question(question_id: str, course_id: str, db: Session) -> Question:
    q = db.get(Question, question_id)
    if not q or q.course_id != course_id:
        raise HTTPException(status_code=404, detail="问题不存在")
    return q


def _can_see(q: Question, user_id: str, role: str) -> bool:
    """判断当前用户是否有权查看该问题"""
    if role == "teacher":
        return True
    if q.visibility == "public":
        return True
    # 私密问题只有提问者本人可见
    return q.asked_by == user_id


# ── 学生提问 ──────────────────────────────────────────────────

def create_question(course_id: str, student_id: str, title: str,
                    content: str | None, visibility: str,
                    section_id: str | None, db: Session) -> dict:
    _require_enrollment(course_id, student_id, db)
    q = Question(
        course_id=course_id, section_id=section_id,
        asked_by=student_id, title=title, content=content, visibility=visibility,
    )
    db.add(q)
    db.commit()
    db.refresh(q)
    student = db.get(User, student_id)
    return {
        "id": q.id, "course_id": course_id,
        "section_id": section_id, "section_title": _section_title(section_id, db),
        "title": q.title, "content": q.content, "visibility": q.visibility,
        "status": q.status,
        "asked_by": {"id": student.id, "name": student.name},
        "created_at": q.created_at,
    }


# ── 获取问题列表 ──────────────────────────────────────────────

def list_questions(course_id: str, user_id: str, role: str,
                   section_id: str | None, status: str | None,
                   visibility: str | None, db: Session) -> dict:
    if role == "teacher":
        _require_teacher_course(course_id, user_id, db)
    else:
        _require_enrollment(course_id, user_id, db)
    q = db.query(Question).filter(Question.course_id == course_id)
    if section_id:
        q = q.filter(Question.section_id == section_id)
    if status:
        q = q.filter(Question.status == status)
    if role == "teacher" and visibility:
        q = q.filter(Question.visibility == visibility)
    questions = q.order_by(Question.created_at.desc()).all()
    items = []
    for question in questions:
        if not _can_see(question, user_id, role):
            continue
        asker = db.get(User, question.asked_by)
        answer = db.query(QuestionAnswer).filter(
            QuestionAnswer.question_id == question.id
        ).first()
        items.append({
            "id": question.id,
            "section_id": question.section_id,
            "section_title": _section_title(question.section_id, db),
            "title": question.title, "visibility": question.visibility,
            "status": question.status,
            "asked_by": {"id": asker.id, "name": asker.name} if asker else {},
            "created_at": question.created_at,
            "answered_at": answer.answered_at if answer else None,
        })
    return {"course_id": course_id, "items": items, "total": len(items)}


# ── 获取问题详情 ──────────────────────────────────────────────

def get_question(course_id: str, question_id: str, user_id: str, role: str, db: Session) -> dict:
    if role == "teacher":
        _require_teacher_course(course_id, user_id, db)
    else:
        _require_enrollment(course_id, user_id, db)
    q = _require_question(question_id, course_id, db)
    if not _can_see(q, user_id, role):
        raise HTTPException(status_code=403, detail="无权查看此问题")
    asker = db.get(User, q.asked_by)
    answer = db.query(QuestionAnswer).filter(QuestionAnswer.question_id == question_id).first()
    answer_data = None
    if answer:
        answerer = db.get(User, answer.answered_by)
        answer_data = {
            "content": answer.content,
            "answered_by": {"id": answerer.id, "name": answerer.name} if answerer else {},
            "answered_at": answer.answered_at,
        }
    return {
        "id": q.id, "course_id": course_id,
        "section_id": q.section_id, "section_title": _section_title(q.section_id, db),
        "title": q.title, "content": q.content,
        "visibility": q.visibility, "status": q.status,
        "asked_by": {"id": asker.id, "name": asker.name} if asker else {},
        "answer": answer_data, "created_at": q.created_at,
    }


# ── 教师回答 ──────────────────────────────────────────────────

def answer_question(course_id: str, teacher_id: str, question_id: str,
                    content: str, db: Session) -> dict:
    _require_teacher_course(course_id, teacher_id, db)
    q = _require_question(question_id, course_id, db)
    # 已有回答则更新
    existing = db.query(QuestionAnswer).filter(QuestionAnswer.question_id == question_id).first()
    if existing:
        existing.content = content
        from datetime import datetime, timezone
        existing.answered_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(existing)
        answer = existing
    else:
        answer = QuestionAnswer(question_id=question_id, answered_by=teacher_id, content=content)
        db.add(answer)
        q.status = "answered"
        db.commit()
        db.refresh(answer)
    teacher = db.get(User, teacher_id)
    return {
        "question_id": question_id,
        "answer": {
            "content": answer.content,
            "answered_by": {"id": teacher.id, "name": teacher.name},
            "answered_at": answer.answered_at,
        },
    }


# ── 修改可见性 ────────────────────────────────────────────────

def update_visibility(course_id: str, question_id: str, user_id: str,
                      role: str, visibility: str, db: Session) -> dict:
    if role == "teacher":
        _require_teacher_course(course_id, user_id, db)
    else:
        _require_enrollment(course_id, user_id, db)
    q = _require_question(question_id, course_id, db)
    # 学生只能改为 private
    if role == "student":
        if q.asked_by != user_id:
            raise HTTPException(status_code=403, detail="无权修改他人问题")
        if visibility == "public":
            raise HTTPException(status_code=403, detail="学生只能将问题改为私密")
    q.visibility = visibility
    db.commit()
    return {"id": q.id, "visibility": q.visibility}


# ── 删除问题 ──────────────────────────────────────────────────

def delete_question(course_id: str, question_id: str, user_id: str,
                    role: str, db: Session) -> None:
    if role == "teacher":
        _require_teacher_course(course_id, user_id, db)
    else:
        _require_enrollment(course_id, user_id, db)
    q = _require_question(question_id, course_id, db)
    if role == "student":
        if q.asked_by != user_id:
            raise HTTPException(status_code=403, detail="无权删除他人问题")
        if q.status == "answered":
            raise HTTPException(status_code=400, detail="已回答的问题不能删除")
    answer = db.query(QuestionAnswer).filter(QuestionAnswer.question_id == question_id).first()
    if answer:
        db.delete(answer)
    db.delete(q)
    db.commit()
