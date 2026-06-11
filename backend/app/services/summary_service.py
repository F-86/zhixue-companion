"""知识点总结服务（课程路径版，支持 RAG）—— 业务编排层"""
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.db.repositories.course import require_enrollment as _require_enrollment, get_course_name
from app.db.repositories.summary import (
    create_summary_obj,
    list_summaries as list_summaries_repo,
    get_summary_obj,
    delete_summary,
)


def create_summary(course_id: str, student_id: str, title: str,
                   section_id: str | None, source_text: str | None,
                   summary_type: str, db: Session) -> dict:
    _require_enrollment(course_id, student_id, db)
    rag_used = False
    refs = []
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

    course_name = get_course_name(course_id, db)
    from app.services.minimax_client import generate_summary
    result = generate_summary(title, text_to_summarize, summary_type, course_name)

    section_title = None
    if section_id:
        from app.models.section import Section
        sec = db.get(Section, section_id)
        section_title = sec.title if sec else None

    s_obj = create_summary_obj(student_id, course_id, section_id, title, source_text,
                                summary_type, rag_used, result, db)
    return {
        "id": s_obj.id, "course_id": course_id, "section_id": section_id,
        "section_title": section_title, "title": title,
        "rag_used": rag_used, "references": refs,
        "summary": result, "created_at": s_obj.created_at,
    }


def list_summaries(course_id: str, student_id: str,
                   section_id: str | None, keyword: str | None, db: Session) -> dict:
    _require_enrollment(course_id, student_id, db)
    items_raw = list_summaries_repo(course_id, student_id, section_id, keyword, db)
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
    s = get_summary_obj(course_id, summary_id, student_id, db)
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
