"""讨论路由"""
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.services import discussion_service as svc
from app.services.auth_service import get_current_user, require_teacher

router = APIRouter(tags=["讨论"])


def _ok(data, message="ok"):
    return {"success": True, "data": data, "message": message}


class DiscussionCreateRequest(BaseModel):
    title: str
    content: str
    section_id: str | None = None


class DiscussionStatusRequest(BaseModel):
    status: str  # open | closed


class ReplyCreateRequest(BaseModel):
    content: str


# ── 教师创建讨论 ──────────────────────────────────────────────

@router.post("/courses/{course_id}/discussions", status_code=201)
def create_discussion(course_id: str, req: DiscussionCreateRequest,
                       current_user=Depends(require_teacher), db: Session = Depends(get_db)):
    return _ok(svc.create_discussion(course_id, current_user.id, req.title, req.content, req.section_id, db), "created")


# ── 通用：列表/详情 ───────────────────────────────────────────

@router.get("/courses/{course_id}/discussions")
def list_discussions(course_id: str, section_id: str | None = None, status: str | None = None,
                      current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    return _ok(svc.list_discussions(course_id, current_user.id, current_user.role, section_id, status, db))


@router.get("/courses/{course_id}/discussions/{discussion_id}")
def get_discussion(course_id: str, discussion_id: str, page: int = 1, page_size: int = 20,
                    current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    return _ok(svc.get_discussion(course_id, discussion_id, current_user.id, current_user.role, page, page_size, db))


# ── 回复 ──────────────────────────────────────────────────────

@router.post("/courses/{course_id}/discussions/{discussion_id}/replies", status_code=201)
def add_reply(course_id: str, discussion_id: str, req: ReplyCreateRequest,
               current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    return _ok(svc.add_reply(course_id, discussion_id, current_user.id, current_user.role, req.content, db), "replied")


@router.delete("/courses/{course_id}/discussions/{discussion_id}/replies/{reply_id}")
def delete_reply(course_id: str, discussion_id: str, reply_id: str,
                  current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    svc.delete_reply(course_id, discussion_id, reply_id, current_user.id, current_user.role, db)
    return _ok({"id": reply_id}, "deleted")


# ── 教师管理 ──────────────────────────────────────────────────

@router.patch("/courses/{course_id}/discussions/{discussion_id}")
def update_discussion(course_id: str, discussion_id: str, req: DiscussionStatusRequest,
                       current_user=Depends(require_teacher), db: Session = Depends(get_db)):
    return _ok(svc.update_discussion_status(course_id, current_user.id, discussion_id, req.status, db), "updated")


@router.delete("/courses/{course_id}/discussions/{discussion_id}")
def delete_discussion(course_id: str, discussion_id: str,
                       current_user=Depends(require_teacher), db: Session = Depends(get_db)):
    svc.delete_discussion(course_id, current_user.id, discussion_id, db)
    return _ok({"id": discussion_id}, "deleted")
