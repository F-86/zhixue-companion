"""智能问答服务（课程路径版，支持 RAG）—— 业务编排层"""
import json
import logging
import uuid

from sqlalchemy.orm import Session

from app.db.repositories.course import require_enrollment as _require_enrollment, get_course_name
from app.db.repositories.chat import (
    get_history,
    save_messages,
    get_session_messages,
    list_sessions,
)

logger = logging.getLogger(__name__)


def _rag_retrieve(course_id: str, section_id: str | None, question: str, db: Session) -> list[dict]:
    """向量检索：将问题向量化后，在向量库中找最相关的课程材料片段。"""
    try:
        from app.services.minimax_client import embed_query
        from app.db.vector_store import query_chunks
        query_embedding = embed_query(question)
        results = query_chunks(query_embedding, course_id, top_k=3)
        if section_id:
            results = [r for r in results if r["section_id"] == section_id]
        return results
    except Exception:
        logger.warning("RAG 检索失败，降级为无上下文回答", exc_info=True)
        return []


def stream_message(course_id: str, student_id: str, question: str,
                   session_id: str | None, section_id: str | None, db: Session):
    """流式问答主流程，yield SSE 格式字符串。"""
    _require_enrollment(course_id, student_id, db)
    session_id = session_id or str(uuid.uuid4())

    history = get_history(session_id, course_id, db)
    history_data = [{"role": m.role, "content": m.content} for m in history]

    refs = _rag_retrieve(course_id, section_id, question, db)
    rag_used = len(refs) > 0
    course_name = get_course_name(course_id, db)
    context = ""
    if refs:
        context = "\n\n".join(
            f"[课程材料参考] {r['section_title']}：{r['excerpt']}" for r in refs
        )

    yield f"data: {json.dumps({'type': 'meta', 'session_id': session_id, 'rag_used': rag_used, 'references': refs}, ensure_ascii=False)}\n\n"

    full_answer_parts: list[str] = []
    try:
        from app.services.minimax_client import answer_question_stream
        for chunk in answer_question_stream(question, course_name, history_data, context):
            full_answer_parts.append(chunk)
            yield f"data: {json.dumps({'type': 'delta', 'content': chunk}, ensure_ascii=False)}\n\n"
    except Exception:
        logger.exception("流式问答 MiniMax 调用失败，session_id=%s", session_id)
        yield f"data: {json.dumps({'type': 'error', 'message': '大模型服务暂时不可用，请稍后重试'}, ensure_ascii=False)}\n\n"

    yield 'data: {"type":"done"}\n\n'

    full_answer = "".join(full_answer_parts)
    if full_answer:
        save_messages(session_id, {
            "student_id": student_id, "course_id": course_id,
            "section_id": section_id, "question": question,
            "answer": full_answer,
        })


def send_message(course_id: str, student_id: str, question: str,
                 session_id: str | None, section_id: str | None, db: Session) -> dict:
    """非流式问答主流程。"""
    _require_enrollment(course_id, student_id, db)
    session_id = session_id or str(uuid.uuid4())

    history = get_history(session_id, course_id, db)
    history_data = [{"role": m.role, "content": m.content} for m in history]

    refs = _rag_retrieve(course_id, section_id, question, db)
    rag_used = len(refs) > 0
    course_name = get_course_name(course_id, db)
    context = ""
    if refs:
        context = "\n\n".join(
            f"[课程材料参考] {r['section_title']}：{r['excerpt']}" for r in refs
        )
    from app.services.minimax_client import answer_question
    result = answer_question(question, course_name, history_data, context)
    return {
        "session_id": session_id,
        "answer": result.get("answer", ""),
        "rag_used": rag_used,
        "references": refs,
        "suggestions": result.get("suggestions", []),
        "_save_ctx": {
            "student_id": student_id, "course_id": course_id,
            "section_id": section_id, "question": question,
            "answer": result.get("answer", ""),
        },
    }
