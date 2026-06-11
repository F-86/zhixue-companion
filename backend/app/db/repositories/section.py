"""数据库操作层 —— 小节查询"""
import hashlib
import logging
import os
import re

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.section import Section
from app.db.repositories.course import require_enrollment, require_teacher_course

logger = logging.getLogger(__name__)

# 超长段落降级为字符分块时的大小和重叠
_CHUNK_SIZE = 500
_CHUNK_OVERLAP = 50


def require_section(section_id: str, course_id: str, db: Session) -> Section:
    s = db.get(Section, section_id)
    if not s or s.course_id != course_id:
        raise HTTPException(status_code=404, detail="小节不存在")
    return s


def section_title(section_id: str | None, db: Session) -> str | None:
    if not section_id:
        return None
    s = db.get(Section, section_id)
    return s.title if s else None


def _char_split(text: str) -> list[str]:
    """超长段落的字符级降级分块，保留 _CHUNK_OVERLAP 字符重叠。"""
    chunks = []
    start = 0
    while start < len(text):
        end = start + _CHUNK_SIZE
        chunk = text[start:end]
        if end < len(text):
            for sep in ("。", "\n", ".", "，"):
                pos = chunk.rfind(sep)
                if pos > _CHUNK_SIZE // 2:
                    chunk = chunk[: pos + 1]
                    end = start + pos + 1
                    break
        chunks.append(chunk.strip())
        start = end - _CHUNK_OVERLAP
    return [c for c in chunks if c]


def split_text(text: str) -> list[str]:
    """段落/标题感知分块策略。"""
    raw_segments = re.split(r"(?=\n#{1,6}\s)|\n{2,}", text)
    chunks: list[str] = []
    for seg in raw_segments:
        seg = seg.strip()
        if not seg:
            continue
        if len(seg) <= _CHUNK_SIZE:
            chunks.append(seg)
        else:
            chunks.extend(_char_split(seg))
    return [c for c in chunks if c]


def text_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def index_material(section: Section, db: Session | None = None) -> None:
    """对小节课件文本分块、向量化，写入向量库。"""
    if not section.material_text:
        return
    new_hash = text_hash(section.material_text)
    if section.material_hash and section.material_hash == new_hash:
        logger.info("小节 %s 内容未变（hash 一致），跳过重新索引", section.id)
        return
    try:
        from app.services import minimax_client
        from app.db.vector_store import delete_chunks_by_section, upsert_chunks
        delete_chunks_by_section(section.id)
        chunks_text = split_text(section.material_text)
        if not chunks_text:
            return
        embeddings = minimax_client.embed_texts(chunks_text)
        file_name = os.path.basename(section.material_path) if section.material_path else ""
        chunks = [
            {
                "id": f"{section.id}#{i}",
                "section_id": section.id,
                "section_title": section.title,
                "course_id": section.course_id,
                "file_name": file_name,
                "text": text,
                "embedding": emb,
            }
            for i, (text, emb) in enumerate(zip(chunks_text, embeddings))
        ]
        upsert_chunks(chunks)
        section.material_hash = new_hash
        if db is not None:
            db.commit()
        logger.info("小节 %s 向量化完成，共 %d 块", section.id, len(chunks))
    except Exception:
        logger.exception("小节 %s 向量化失败，跳过", section.id)


# ── 教师端 ────────────────────────────────────────────────────

def create_section(course_id: str, teacher_id: str, title: str,
                   description: str | None, order: int | None,
                   material_file_id: str | None, db: Session) -> Section:
    require_teacher_course(course_id, teacher_id, db)
    if order is None:
        max_order = db.query(Section).filter(Section.course_id == course_id).count()
        order = max_order + 1
    material_path = None
    material_text = None
    if material_file_id:
        from app.models.file import File as FileModel
        file_record = db.get(FileModel, material_file_id)
        if not file_record:
            raise HTTPException(status_code=400, detail="课件文件不存在，请先通过 /api/upload 上传")
        material_path = file_record.file_path
        material_text = file_record.extracted_text
    s = Section(
        course_id=course_id, title=title, description=description,
        order=order, material_path=material_path, material_text=material_text,
    )
    db.add(s)
    db.commit()
    db.refresh(s)
    index_material(s, db)
    return s


def list_teacher_sections(course_id: str, teacher_id: str, db: Session) -> dict:
    require_teacher_course(course_id, teacher_id, db)
    from app.models.assignment import Assignment
    sections = db.query(Section).filter(Section.course_id == course_id).order_by(Section.order).all()
    items = []
    for s in sections:
        assignment_count = db.query(Assignment).filter(Assignment.section_id == s.id).count()
        material_url = f"/files/{os.path.basename(s.material_path)}" if s.material_path else None
        items.append({
            "id": s.id, "title": s.title, "order": s.order,
            "material_url": material_url,
            "assignment_count": assignment_count, "created_at": s.created_at,
        })
    return {"course_id": course_id, "items": items, "total": len(items)}


def update_section(course_id: str, teacher_id: str, section_id: str,
                   title: str | None, description: str | None, order: int | None,
                   db: Session) -> Section:
    require_teacher_course(course_id, teacher_id, db)
    s = require_section(section_id, course_id, db)
    if title is not None:
        s.title = title
    if description is not None:
        s.description = description
    if order is not None:
        s.order = order
    db.commit()
    db.refresh(s)
    return s


def delete_section(course_id: str, teacher_id: str, section_id: str, db: Session) -> None:
    require_teacher_course(course_id, teacher_id, db)
    s = require_section(section_id, course_id, db)
    from app.models.assignment import Assignment
    db.query(Assignment).filter(Assignment.section_id == section_id).delete()
    db.delete(s)
    db.commit()
    try:
        from app.db.vector_store import delete_chunks_by_section
        delete_chunks_by_section(section_id)
    except Exception:
        logger.exception("清理小节 %s 向量失败，跳过", section_id)


# ── 学生端 ────────────────────────────────────────────────────

def list_student_sections(course_id: str, student_id: str, db: Session) -> dict:
    require_enrollment(course_id, student_id, db)
    from app.models.assignment import Assignment
    from app.models.grade import AIGradingResult
    from app.models.submission import Submission
    sections = db.query(Section).filter(Section.course_id == course_id).order_by(Section.order).all()
    items = []
    for s in sections:
        assignments = db.query(Assignment).filter(Assignment.section_id == s.id).all()
        assignment_count = len(assignments)
        submitted_count = 0
        scores = []
        for a in assignments:
            sub = db.query(Submission).filter(
                Submission.assignment_id == a.id,
                Submission.student_id == student_id,
            ).first()
            if sub:
                submitted_count += 1
                grade = db.query(AIGradingResult).filter(
                    AIGradingResult.submission_id == sub.id,
                    AIGradingResult.confirmed == True,
                ).first()
                if grade and grade.final_score is not None:
                    scores.append(grade.final_score)
        material_url = f"/files/{os.path.basename(s.material_path)}" if s.material_path else None
        items.append({
            "id": s.id, "title": s.title, "description": s.description,
            "order": s.order, "material_url": material_url,
            "assignment_count": assignment_count, "submitted_count": submitted_count,
            "section_score": round(sum(scores) / len(scores), 1) if scores else None,
        })
    return {"course_id": course_id, "items": items, "total": len(items)}


def get_student_section(course_id: str, student_id: str, section_id: str, db: Session) -> dict:
    require_enrollment(course_id, student_id, db)
    s = require_section(section_id, course_id, db)
    from app.models.assignment import Assignment
    from app.models.grade import AIGradingResult
    from app.models.submission import Submission
    assignments = db.query(Assignment).filter(Assignment.section_id == section_id).all()
    assignment_items = []
    for a in assignments:
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
        assignment_items.append({
            "id": a.id, "title": a.title, "due_at": a.due_at,
            "status": a.status, "submitted": sub is not None, "score": score,
        })
    material_url = f"/files/{os.path.basename(s.material_path)}" if s.material_path else None
    return {
        "id": s.id, "course_id": course_id, "title": s.title,
        "description": s.description, "order": s.order,
        "material_url": material_url, "assignments": assignment_items,
    }
