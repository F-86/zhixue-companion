"""知识点总结服务（课程路径版，支持 RAG）"""
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.summary import Summary
from app.services.course_service import _require_enrollment


def create_summary(course_id: str, student_id: str, title: str,
                   section_id: str | None, source_text: str | None,
                   summary_type: str, db: Session) -> dict:
    _require_enrollment(course_id, student_id, db)
    rag_used = False
    refs = []
    # 确定总结原文
    if source_text:
        text_to_summarize = source_text
    elif section_id:
        from app.models.section import Section
        sec = db.get(Section, section_id)
        if not sec or not sec.material_text:
            raise HTTPException(status_code=400, detail="该小节暂无可用课程材料，请手动输入内容")
        text_to_summarize = sec.material_text[:3000]
        refs = [{"file_name": sec.material_path.split("/")[-1] if sec.material_path else "", "excerpt": text_to_summarize[:200]}]
        rag_used = True
    else:
        raise HTTPException(status_code=400, detail="请提供 source_text 或 section_id")
    from app.models.course import Course
    course = db.get(Course, course_id)
    course_name = course.name if course else ""
    from app.services import minimax_client
    result = minimax_client.generate_summary(title, text_to_summarize, summary_type, course_name)
    section_title = None
    if section_id:
        from app.models.section import Section
        sec = db.get(Section, section_id)
        section_title = sec.title if sec else None
    s_obj = Summary(
        user_id=student_id, course_id=course_id, section_id=section_id,
        title=title, source_text=source_text, summary_type=summary_type,
        rag_used=rag_used, result=result,
    )
    db.add(s_obj)
    db.commit()
    db.refresh(s_obj)
    return {
        "id": s_obj.id, "course_id": course_id, "section_id": section_id,
        "section_title": section_title, "title": title,
        "rag_used": rag_used, "references": refs,
        "summary": result, "created_at": s_obj.created_at,
    }


def list_summaries(course_id: str, student_id: str,
                   section_id: str | None, keyword: str | None, db: Session) -> dict:
    _require_enrollment(course_id, student_id, db)
    q = db.query(Summary).filter(Summary.user_id == student_id, Summary.course_id == course_id)
    if section_id:
        q = q.filter(Summary.section_id == section_id)
    if keyword:
        q = q.filter(Summary.title.contains(keyword))
    items_raw = q.order_by(Summary.created_at.desc()).all()
    items = []
    for s in items_raw:
        section_title = None
        if s.section_id:
            from app.models.section import Section
            sec = db.get(Section, s.section_id)
            section_title = sec.title if sec else None
        items.append({
            "id": s.id, "section_id": s.section_id, "section_title": section_title,
            "title": s.title, "rag_used": s.rag_used, "created_at": s.created_at,
        })
    return {"course_id": course_id, "items": items, "total": len(items)}


def get_summary(course_id: str, summary_id: str, student_id: str, db: Session) -> dict:
    _require_enrollment(course_id, student_id, db)
    s = db.get(Summary, summary_id)
    if not s or s.user_id != student_id or s.course_id != course_id:
        raise HTTPException(status_code=404, detail="总结不存在")
    section_title = None
    refs = []
    if s.section_id:
        from app.models.section import Section
        sec = db.get(Section, s.section_id)
        section_title = sec.title if sec else None
        if s.rag_used and sec and sec.material_path:
            refs = [{"file_name": sec.material_path.split("/")[-1], "excerpt": ""}]
    return {
        "id": s.id, "course_id": course_id, "section_id": s.section_id,
        "section_title": section_title, "title": s.title,
        "rag_used": s.rag_used, "references": refs,
        "summary": s.result, "created_at": s.created_at,
    }


def delete_summary(course_id: str, summary_id: str, student_id: str, db: Session) -> None:
    _require_enrollment(course_id, student_id, db)
    s = db.get(Summary, summary_id)
    if not s or s.user_id != student_id or s.course_id != course_id:
        raise HTTPException(status_code=404, detail="总结不存在")
    db.delete(s)
    db.commit()
