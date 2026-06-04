"""智能问答路由（课程路径版）"""
from fastapi import APIRouter, BackgroundTasks, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.services import chat_service as svc
from app.services.auth_service import require_student

router = APIRouter(tags=["智能问答"])


def _ok(data, message="ok"):
    return {"success": True, "data": data, "message": message}


class ChatRequest(BaseModel):
    question: str
    session_id: str | None = None
    section_id: str | None = None


@router.post("/student/courses/{course_id}/chat")
def send_message(
    course_id: str,
    req: ChatRequest,
    background_tasks: BackgroundTasks,
    current_user=Depends(require_student),
    db: Session = Depends(get_db),
):
    result = svc.send_message(
        course_id, current_user.id, req.question, req.session_id, req.section_id, db
    )
    # 取出写入上下文，调度后台任务，不阻塞响应
    save_ctx = result.pop("_save_ctx")
    background_tasks.add_task(svc.save_messages, result["session_id"], save_ctx)
    return _ok(result)


@router.get("/student/courses/{course_id}/chat/sessions")
def list_sessions(course_id: str, section_id: str | None = None,
                   current_user=Depends(require_student), db: Session = Depends(get_db)):
    return _ok(svc.list_sessions(course_id, current_user.id, section_id, db))


@router.get("/student/courses/{course_id}/chat/sessions/{session_id}/messages")
def get_session_messages(course_id: str, session_id: str,
                          current_user=Depends(require_student), db: Session = Depends(get_db)):
    return _ok(svc.get_session_messages(course_id, session_id, current_user.id, db))
