"""数据库操作层 —— 公告查询"""
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.announcement import Announcement, AnnouncementRead
from app.models.course import CourseEnrollment
from app.db.repositories.course import require_enrollment, require_teacher_course


def require_announcement(notice_id: str, course_id: str, db: Session) -> Announcement:
    a = db.get(Announcement, notice_id)
    if not a or a.course_id != course_id:
        raise HTTPException(status_code=404, detail="公告不存在")
    return a


# ── 教师端 ────────────────────────────────────────────────────

def create_announcement(course_id: str, teacher_id: str, title: str,
                         content: str, is_pinned: bool, db: Session) -> Announcement:
    require_teacher_course(course_id, teacher_id, db)
    a = Announcement(course_id=course_id, title=title, content=content, is_pinned=is_pinned)
    db.add(a)
    db.commit()
    db.refresh(a)
    return a


def list_teacher_announcements(course_id: str, teacher_id: str,
                                page: int, page_size: int, db: Session) -> dict:
    require_teacher_course(course_id, teacher_id, db)
    total_students = db.query(CourseEnrollment).filter(CourseEnrollment.course_id == course_id).count()
    q = db.query(Announcement).filter(Announcement.course_id == course_id)
    total = q.count()
    items_raw = (
        q.order_by(Announcement.is_pinned.desc(), Announcement.created_at.desc())
        .offset((page - 1) * page_size).limit(page_size).all()
    )
    items = []
    for a in items_raw:
        read_count = db.query(AnnouncementRead).filter(AnnouncementRead.announcement_id == a.id).count()
        items.append({
            "id": a.id, "title": a.title, "is_pinned": a.is_pinned,
            "read_count": read_count, "total_students": total_students,
            "created_at": a.created_at,
        })
    return {"course_id": course_id, "items": items, "total": total}


def update_announcement(course_id: str, teacher_id: str, notice_id: str,
                         title: str | None, content: str | None,
                         is_pinned: bool | None, db: Session) -> Announcement:
    require_teacher_course(course_id, teacher_id, db)
    a = require_announcement(notice_id, course_id, db)
    if title is not None:
        a.title = title
    if content is not None:
        a.content = content
    if is_pinned is not None:
        a.is_pinned = is_pinned
    db.commit()
    db.refresh(a)
    return a


def get_teacher_announcement(course_id: str, teacher_id: str, notice_id: str, db: Session) -> dict:
    """教师查看单条公告（含已读统计）"""
    require_teacher_course(course_id, teacher_id, db)
    a = require_announcement(notice_id, course_id, db)
    total_students = db.query(CourseEnrollment).filter(CourseEnrollment.course_id == course_id).count()
    read_count = db.query(AnnouncementRead).filter(AnnouncementRead.announcement_id == notice_id).count()
    return {
        "id": a.id, "course_id": course_id, "title": a.title, "content": a.content,
        "is_pinned": a.is_pinned, "read_count": read_count, "total_students": total_students,
        "created_at": a.created_at, "updated_at": a.updated_at,
    }


def delete_announcement(course_id: str, teacher_id: str, notice_id: str, db: Session) -> None:
    require_teacher_course(course_id, teacher_id, db)
    a = require_announcement(notice_id, course_id, db)
    db.query(AnnouncementRead).filter(AnnouncementRead.announcement_id == notice_id).delete()
    db.delete(a)
    db.commit()


# ── 学生端 ────────────────────────────────────────────────────

def list_student_announcements(course_id: str, student_id: str,
                                page: int, page_size: int, db: Session) -> dict:
    require_enrollment(course_id, student_id, db)
    q = db.query(Announcement).filter(Announcement.course_id == course_id)
    total = q.count()
    items_raw = (
        q.order_by(Announcement.is_pinned.desc(), Announcement.created_at.desc())
        .offset((page - 1) * page_size).limit(page_size).all()
    )
    existing_reads = {
        r.announcement_id
        for r in db.query(AnnouncementRead).filter(
            AnnouncementRead.student_id == student_id
        ).all()
    }
    unread_count = 0
    items = []
    for a in items_raw:
        is_read = a.id in existing_reads
        if not is_read:
            unread_count += 1
            db.add(AnnouncementRead(announcement_id=a.id, student_id=student_id))
        items.append({
            "id": a.id, "title": a.title, "content": a.content,
            "is_pinned": a.is_pinned, "is_read": is_read, "created_at": a.created_at,
        })
    db.commit()
    return {"course_id": course_id, "unread_count": unread_count, "items": items, "total": total}


def get_student_announcement(course_id: str, student_id: str, notice_id: str, db: Session) -> dict:
    require_enrollment(course_id, student_id, db)
    a = require_announcement(notice_id, course_id, db)
    exists = db.query(AnnouncementRead).filter(
        AnnouncementRead.announcement_id == notice_id,
        AnnouncementRead.student_id == student_id,
    ).first()
    if not exists:
        db.add(AnnouncementRead(announcement_id=notice_id, student_id=student_id))
        db.commit()
    return {
        "id": a.id, "course_id": course_id, "title": a.title, "content": a.content,
        "is_pinned": a.is_pinned, "is_read": True, "created_at": a.created_at,
    }
