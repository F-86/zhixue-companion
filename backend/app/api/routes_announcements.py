"""公告路由"""
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.services import announcement_service as svc
from app.services.auth_service import get_current_user, require_teacher

router = APIRouter(tags=["课程公告"])


def _ok(data, message="ok"):
    return {"success": True, "data": data, "message": message}


class AnnouncementCreateRequest(BaseModel):
    title: str
    content: str
    is_pinned: bool = False


class AnnouncementUpdateRequest(BaseModel):
    title: str | None = None
    content: str | None = None
    is_pinned: bool | None = None


# ── 教师端 ────────────────────────────────────────────────────

@router.post("/courses/{course_id}/announcements", status_code=201)
def create_announcement(course_id: str, req: AnnouncementCreateRequest,
                         current_user=Depends(require_teacher), db: Session = Depends(get_db)):
    a = svc.create_announcement(course_id, current_user.id, req.title, req.content, req.is_pinned, db)
    return _ok({
        "id": a.id, "course_id": course_id, "title": a.title,
        "content": a.content, "is_pinned": a.is_pinned, "created_at": a.created_at,
    }, "published")


@router.patch("/courses/{course_id}/announcements/{notice_id}")
def update_announcement(course_id: str, notice_id: str, req: AnnouncementUpdateRequest,
                         current_user=Depends(require_teacher), db: Session = Depends(get_db)):
    a = svc.update_announcement(course_id, current_user.id, notice_id,
                                 req.title, req.content, req.is_pinned, db)
    return _ok({"id": a.id, "title": a.title, "is_pinned": a.is_pinned, "updated_at": a.updated_at}, "updated")


@router.delete("/courses/{course_id}/announcements/{notice_id}")
def delete_announcement(course_id: str, notice_id: str,
                         current_user=Depends(require_teacher), db: Session = Depends(get_db)):
    svc.delete_announcement(course_id, current_user.id, notice_id, db)
    return _ok({"id": notice_id}, "deleted")


# ── 学生端 ────────────────────────────────────────────────────

@router.get("/courses/{course_id}/announcements")
def list_announcements(course_id: str, page: int = 1, page_size: int = 20,
                        current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    """教师调用时返回阅读统计，学生调用时自动标已读"""
    if current_user.role == "teacher":
        return _ok(svc.list_teacher_announcements(course_id, current_user.id, page, page_size, db))
    return _ok(svc.list_student_announcements(course_id, current_user.id, page, page_size, db))


@router.get("/courses/{course_id}/announcements/{notice_id}")
def get_announcement(course_id: str, notice_id: str,
                      current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    """教师和学生均可查看公告详情"""
    if current_user.role == "teacher":
        return _ok(svc.get_teacher_announcement(course_id, current_user.id, notice_id, db))
    return _ok(svc.get_student_announcement(course_id, current_user.id, notice_id, db))
