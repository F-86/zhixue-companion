"""课程小节服务"""
import hashlib
import logging
import os
import re
import uuid

from fastapi import HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.section import Section
from app.services.course_service import _require_enrollment, _require_teacher_course

logger = logging.getLogger(__name__)

# 超长段落降级为字符分块时的大小和重叠
_CHUNK_SIZE = 500
_CHUNK_OVERLAP = 50


def _require_section(section_id: str, course_id: str, db: Session) -> Section:
    s = db.get(Section, section_id)
    if not s or s.course_id != course_id:
        raise HTTPException(status_code=404, detail="小节不存在")
    return s


def _char_split(text: str) -> list[str]:
    """超长段落的字符级降级分块，保留 _CHUNK_OVERLAP 字符重叠。"""
    chunks = []
    start = 0
    while start < len(text):
        end = start + _CHUNK_SIZE
        chunk = text[start:end]
        # 尽量在句号/换行处断开
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


def _split_text(text: str) -> list[str]:
    """
    段落/标题感知分块策略：
    1. 先按 Markdown 标题行（# 开头）或连续空行（\\n\\n）切分为自然段落
    2. 段落本身不超过 _CHUNK_SIZE 字符的直接保留
    3. 超长段落再调用 _char_split 降级切分
    这样切出来的块尽量保持完整的语义单元（一个小节/一个段落），
    避免语义在固定位置被硬截断。
    """
    # 按 Markdown 标题或连续空行切分
    raw_segments = re.split(r"(?=\n#{1,6}\s)|\n{2,}", text)
    chunks: list[str] = []
    for seg in raw_segments:
        seg = seg.strip()
        if not seg:
            continue
        if len(seg) <= _CHUNK_SIZE:
            chunks.append(seg)
        else:
            # 段落太长，降级为字符分块
            chunks.extend(_char_split(seg))
    return [c for c in chunks if c]


def _text_hash(text: str) -> str:
    """计算文本的 SHA-256 摘要，用于增量更新索引的比对。"""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _index_material(section: Section, db: Session | None = None) -> None:
    """
    对小节课件文本分块、向量化，写入向量库。
    在 create_section / update_section 提取到新 material_text 后调用。

    增量更新：先计算文本的 SHA-256 hash，与数据库中已存储的 material_hash 比对：
    - 内容未变（hash 相同）→ 直接跳过，节省 Embedding API 调用和向量库写入
    - 内容变化或首次建索引 → 删除旧块，重新向量化写入

    失败时只记日志，不影响主流程。
    """
    if not section.material_text:
        return
    new_hash = _text_hash(section.material_text)
    # hash 未变，跳过重建
    if section.material_hash and section.material_hash == new_hash:
        logger.info("小节 %s 内容未变（hash 一致），跳过重新索引", section.id)
        return
    try:
        from app.services import minimax_client
        from app.db.vector_store import delete_chunks_by_section, upsert_chunks
        # 先删除该小节旧块，避免残留过时向量
        delete_chunks_by_section(section.id)
        chunks_text = _split_text(section.material_text)
        if not chunks_text:
            return
        embeddings = minimax_client.embed_texts(chunks_text)
        file_name = os.path.basename(section.material_path) if section.material_path else ""
        chunks = [
            {
                "id":            f"{section.id}#{i}",
                "section_id":    section.id,
                "section_title": section.title,
                "course_id":     section.course_id,
                "file_name":     file_name,
                "text":          text,
                "embedding":     emb,
            }
            for i, (text, emb) in enumerate(zip(chunks_text, embeddings))
        ]
        upsert_chunks(chunks)
        # 更新 hash，避免下次重复建索引
        section.material_hash = new_hash
        if db is not None:
            db.commit()
        logger.info("小节 %s 向量化完成，共 %d 块（分块策略：段落/标题感知）", section.id, len(chunks))
    except Exception:
        logger.exception("小节 %s 向量化失败，跳过", section.id)


# ── 教师端 ────────────────────────────────────────────────────

def create_section(course_id: str, teacher_id: str, title: str,
                   description: str | None, order: int | None,
                   material: UploadFile | None, db: Session) -> Section:
    _require_teacher_course(course_id, teacher_id, db)
    if order is None:
        max_order = db.query(Section).filter(Section.course_id == course_id).count()
        order = max_order + 1
    material_path = None
    material_text = None
    if material:
        ext = material.filename.rsplit(".", 1)[-1].lower() if "." in material.filename else "bin"
        fname = f"section_material_{uuid.uuid4()}.{ext}"
        fpath = os.path.join(settings.upload_dir, fname)
        content = material.file.read()
        with open(fpath, "wb") as f:
            f.write(content)
        material_path = fpath
        # C++ 文件处理提取文本（降级时跳过）
        try:
            from app.services.file_processor_client import extract_text
            material_text = extract_text(fpath)
        except Exception:
            pass
    s = Section(
        course_id=course_id, title=title, description=description,
        order=order, material_path=material_path, material_text=material_text,
    )
    db.add(s)
    db.commit()
    db.refresh(s)
    # 材料提取后立即向量化写入向量库（传入 db 以持久化 hash）
    _index_material(s, db)
    return s


def list_teacher_sections(course_id: str, teacher_id: str, db: Session) -> dict:
    _require_teacher_course(course_id, teacher_id, db)
    from app.models.assignment import Assignment
    sections = db.query(Section).filter(Section.course_id == course_id).order_by(Section.order).all()
    items = []
    for s in sections:
        assignment_count = db.query(Assignment).filter(Assignment.section_id == s.id).count()
        items.append({
            "id": s.id, "title": s.title, "order": s.order,
            "assignment_count": assignment_count, "created_at": s.created_at,
        })
    return {"course_id": course_id, "items": items, "total": len(items)}


def update_section(course_id: str, teacher_id: str, section_id: str,
                   title: str | None, description: str | None, order: int | None,
                   db: Session) -> Section:
    _require_teacher_course(course_id, teacher_id, db)
    s = _require_section(section_id, course_id, db)
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
    _require_teacher_course(course_id, teacher_id, db)
    s = _require_section(section_id, course_id, db)
    # 级联删除该节下的作业
    from app.models.assignment import Assignment
    db.query(Assignment).filter(Assignment.section_id == section_id).delete()
    db.delete(s)
    db.commit()
    # 清理向量库中该小节的所有向量
    try:
        from app.db.vector_store import delete_chunks_by_section
        delete_chunks_by_section(section_id)
    except Exception:
        logger.exception("清理小节 %s 向量失败，跳过", section_id)


# ── 学生端 ────────────────────────────────────────────────────

def list_student_sections(course_id: str, student_id: str, db: Session) -> dict:
    _require_enrollment(course_id, student_id, db)
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
    _require_enrollment(course_id, student_id, db)
    s = _require_section(section_id, course_id, db)
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
