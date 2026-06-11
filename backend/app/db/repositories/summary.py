"""数据库操作层 —— 知识点总结查询"""
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.summary import Summary


def require_summary(summary_id: str, student_id: str, course_id: str, db: Session) -> Summary:
    s = db.get(Summary, summary_id)
    if not s or s.user_id != student_id or s.course_id != course_id:
        raise HTTPException(status_code=404, detail="总结不存在")
    return s


def create_summary_obj(user_id: str, course_id: str, section_id: str | None,
                        title: str, source_text: str | None, summary_type: str,
                        rag_used: bool, result: dict, db: Session) -> Summary:
    s_obj = Summary(
        user_id=user_id, course_id=course_id, section_id=section_id,
        title=title, source_text=source_text, summary_type=summary_type,
        rag_used=rag_used, result=result,
    )
    db.add(s_obj)
    db.commit()
    db.refresh(s_obj)
    return s_obj


def list_summaries(course_id: str, student_id: str,
                   section_id: str | None, keyword: str | None, db: Session) -> list[Summary]:
    q = db.query(Summary).filter(Summary.user_id == student_id, Summary.course_id == course_id)
    if section_id:
        q = q.filter(Summary.section_id == section_id)
    if keyword:
        q = q.filter(Summary.title.contains(keyword))
    return q.order_by(Summary.created_at.desc()).all()


def get_summary_obj(course_id: str, summary_id: str, student_id: str, db: Session) -> Summary:
    return require_summary(summary_id, student_id, course_id, db)


def delete_summary(course_id: str, summary_id: str, student_id: str, db: Session) -> None:
    s = require_summary(summary_id, student_id, course_id, db)
    db.delete(s)
    db.commit()
