"""数据库操作层 —— 聊天消息查询"""
import logging

from sqlalchemy.orm import Session

from app.models.chat import ChatMessage

logger = logging.getLogger(__name__)


def get_history(session_id: str, course_id: str, db: Session, limit: int = 10) -> list[ChatMessage]:
    return (
        db.query(ChatMessage)
        .filter(ChatMessage.session_id == session_id, ChatMessage.course_id == course_id)
        .order_by(ChatMessage.created_at)
        .limit(limit).all()
    )


def save_messages(session_id: str, ctx: dict) -> None:
    """后台任务：将用户问题和 AI 回答持久化到数据库。"""
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
