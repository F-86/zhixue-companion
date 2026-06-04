"""智能问答服务（课程路径版，支持 RAG）"""
import logging
import uuid

from sqlalchemy.orm import Session

from app.models.chat import ChatMessage
from app.services.course_service import _require_enrollment

logger = logging.getLogger(__name__)


def _get_course_name(course_id: str, db: Session) -> str:
    from app.models.course import Course
    c = db.get(Course, course_id)
    return c.name if c else ""


def _rag_retrieve(course_id: str, section_id: str | None, question: str, db: Session) -> list[dict]:
    """
    向量检索：将问题向量化后，在向量库中找最相关的课程材料片段。
    section_id 不为空时限定在指定小节内检索（通过 Chroma where 过滤）。
    若向量库不可用（如未配置 API Key），静默返回空列表。
    """
    try:
        from app.services import minimax_client
        from app.db.vector_store import query_chunks
        query_embedding = minimax_client.embed_query(question)
        results = query_chunks(query_embedding, course_id, top_k=3)
        # 若指定了 section_id，只保留该小节的结果
        if section_id:
            results = [r for r in results if r["section_id"] == section_id]
        return results
    except Exception:
        logger.warning("RAG 检索失败，降级为无上下文回答", exc_info=True)
        return []


def send_message(course_id: str, student_id: str, question: str,
                 session_id: str | None, section_id: str | None, db: Session) -> dict:
    """
    主流程：验证权限 → 读历史 → RAG 检索 → 调用 MiniMax。
    不在此处写入数据库，由调用方通过 BackgroundTasks 异步写入，降低响应延迟。
    """
    _require_enrollment(course_id, student_id, db)
    session_id = session_id or str(uuid.uuid4())
    # 读取历史
    history = (
        db.query(ChatMessage)
        .filter(ChatMessage.session_id == session_id, ChatMessage.course_id == course_id)
        .order_by(ChatMessage.created_at)
        .limit(10).all()
    )
    history_data = [{"role": m.role, "content": m.content} for m in history]
    # RAG 检索
    refs = _rag_retrieve(course_id, section_id, question, db)
    rag_used = len(refs) > 0
    course_name = _get_course_name(course_id, db)
    context = ""
    if refs:
        context = "\n\n".join(
            f"[课程材料参考] {r['section_title']}：{r['excerpt']}" for r in refs
        )
    from app.services import minimax_client
    result = minimax_client.answer_question(question, course_name, history_data, context)
    return {
        "session_id": session_id,
        "answer": result.get("answer", ""),
        "rag_used": rag_used,
        "references": refs,
        "suggestions": result.get("suggestions", []),
        # 私有字段，供后台任务写入使用，不会出现在最终 JSON 响应里
        "_save_ctx": {
            "student_id": student_id,
            "course_id": course_id,
            "section_id": section_id,
            "question": question,
            "answer": result.get("answer", ""),
        },
    }


def save_messages(session_id: str, ctx: dict) -> None:
    """
    后台任务：将用户问题和 AI 回答持久化到数据库。
    使用独立的 DB session，不依赖请求生命周期内的 session。
    """
    from app.db.session import SessionLocal
    db = SessionLocal()
    try:
        db.add(ChatMessage(
            user_id=ctx["student_id"], session_id=session_id,
            course_id=ctx["course_id"], section_id=ctx["section_id"],
            role="user", content=ctx["question"],
        ))
        db.add(ChatMessage(
            user_id=ctx["student_id"], session_id=session_id,
            course_id=ctx["course_id"], section_id=ctx["section_id"],
            role="assistant", content=ctx["answer"],
        ))
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("后台保存消息失败，session_id=%s", session_id)
    finally:
        db.close()


def get_session_messages(course_id: str, session_id: str, student_id: str, db: Session) -> dict:
    _require_enrollment(course_id, student_id, db)
    messages = (
        db.query(ChatMessage)
        .filter(
            ChatMessage.session_id == session_id,
            ChatMessage.user_id == student_id,
            ChatMessage.course_id == course_id,
        )
        .order_by(ChatMessage.created_at).all()
    )
    items = [
        {"id": m.id, "role": m.role, "content": m.content, "created_at": m.created_at}
        for m in messages
    ]
    return {"session_id": session_id, "course_id": course_id, "messages": items}


def list_sessions(course_id: str, student_id: str, section_id: str | None, db: Session) -> dict:
    _require_enrollment(course_id, student_id, db)
    session_ids_rows = (
        db.query(ChatMessage.session_id)
        .filter(ChatMessage.user_id == student_id, ChatMessage.course_id == course_id)
        .distinct().all()
    )
    items = []
    for (sid,) in session_ids_rows:
        msgs = (
            db.query(ChatMessage)
            .filter(ChatMessage.session_id == sid)
            .order_by(ChatMessage.created_at).all()
        )
        if not msgs:
            continue
        if section_id and msgs[0].section_id != section_id:
            continue
        user_msgs = [m for m in msgs if m.role == "user"]
        last_question = user_msgs[-1].content if user_msgs else ""
        sec_title = None
        if msgs[0].section_id:
            from app.models.section import Section
            s = db.get(Section, msgs[0].section_id)
            sec_title = s.title if s else None
        items.append({
            "id": sid, "section_id": msgs[0].section_id, "section_title": sec_title,
            "last_question": last_question, "message_count": len(msgs),
            "created_at": msgs[0].created_at, "updated_at": msgs[-1].created_at,
        })
    return {"course_id": course_id, "items": items, "total": len(items)}
