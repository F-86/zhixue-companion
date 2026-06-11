"""数据库操作层 —— 讨论查询"""
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.discussion import Discussion, DiscussionReply
from app.models.user import User
from app.db.repositories.course import require_enrollment, require_teacher_course


def require_discussion(discussion_id: str, course_id: str, db: Session) -> Discussion:
    d = db.get(Discussion, discussion_id)
    if not d or d.course_id != course_id:
        raise HTTPException(status_code=404, detail="讨论不存在")
    return d


def section_title(section_id: str | None, db: Session) -> str | None:
    if not section_id:
        return None
    from app.models.section import Section
    s = db.get(Section, section_id)
    return s.title if s else None


def user_info(user: User) -> dict:
    return {"id": user.id, "name": user.name, "role": user.role}


# ── 教师创建讨论 ──────────────────────────────────────────────

def create_discussion(course_id: str, teacher_id: str, title: str,
                       content: str, section_id: str | None, db: Session) -> dict:
    require_teacher_course(course_id, teacher_id, db)
    d = Discussion(
        course_id=course_id, section_id=section_id,
        title=title, content=content, created_by=teacher_id,
    )
    db.add(d)
    db.commit()
    db.refresh(d)
    teacher = db.get(User, teacher_id)
    return {
        "id": d.id, "course_id": course_id,
        "section_id": section_id, "section_title": section_title(section_id, db),
        "title": d.title, "content": d.content, "status": d.status,
        "reply_count": 0, "created_by": user_info(teacher), "created_at": d.created_at,
    }


# ── 获取讨论列表 ──────────────────────────────────────────────

def list_discussions(course_id: str, user_id: str, role: str,
                     section_id: str | None, status: str | None, db: Session) -> dict:
    if role == "teacher":
        require_teacher_course(course_id, user_id, db)
    else:
        require_enrollment(course_id, user_id, db)
    q = db.query(Discussion).filter(Discussion.course_id == course_id)
    if section_id:
        q = q.filter(Discussion.section_id == section_id)
    if status:
        q = q.filter(Discussion.status == status)
    discussions = q.order_by(Discussion.created_at.desc()).all()
    items = []
    for d in discussions:
        creator = db.get(User, d.created_by)
        reply_count = db.query(DiscussionReply).filter(DiscussionReply.discussion_id == d.id).count()
        last_reply = (
            db.query(DiscussionReply)
            .filter(DiscussionReply.discussion_id == d.id)
            .order_by(DiscussionReply.created_at.desc()).first()
        )
        items.append({
            "id": d.id, "section_id": d.section_id,
            "section_title": section_title(d.section_id, db),
            "title": d.title, "status": d.status, "reply_count": reply_count,
            "created_by": user_info(creator) if creator else {},
            "last_reply_at": last_reply.created_at if last_reply else None,
            "created_at": d.created_at,
        })
    return {"course_id": course_id, "items": items, "total": len(items)}


# ── 获取讨论详情 ──────────────────────────────────────────────

def get_discussion(course_id: str, discussion_id: str, user_id: str,
                   role: str, page: int, page_size: int, db: Session) -> dict:
    if role == "teacher":
        require_teacher_course(course_id, user_id, db)
    else:
        require_enrollment(course_id, user_id, db)
    d = require_discussion(discussion_id, course_id, db)
    creator = db.get(User, d.created_by)
    reply_total = db.query(DiscussionReply).filter(DiscussionReply.discussion_id == discussion_id).count()
    replies_raw = (
        db.query(DiscussionReply)
        .filter(DiscussionReply.discussion_id == discussion_id)
        .order_by(DiscussionReply.created_at)
        .offset((page - 1) * page_size).limit(page_size).all()
    )
    replies = []
    for r in replies_raw:
        author = db.get(User, r.author_id)
        replies.append({
            "id": r.id, "content": r.content,
            "author": user_info(author) if author else {},
            "is_teacher": (author.role == "teacher") if author else False,
            "created_at": r.created_at,
        })
    return {
        "id": d.id, "course_id": course_id,
        "section_id": d.section_id, "section_title": section_title(d.section_id, db),
        "title": d.title, "content": d.content, "status": d.status,
        "reply_count": reply_total,
        "created_by": user_info(creator) if creator else {},
        "created_at": d.created_at,
        "replies": {
            "items": replies, "total": reply_total,
            "page": page, "page_size": page_size,
        },
    }


# ── 发表回复 ──────────────────────────────────────────────────

def add_reply(course_id: str, discussion_id: str, user_id: str,
              role: str, content: str, db: Session) -> dict:
    if role == "teacher":
        require_teacher_course(course_id, user_id, db)
    else:
        require_enrollment(course_id, user_id, db)
    d = require_discussion(discussion_id, course_id, db)
    if d.status == "closed":
        raise HTTPException(status_code=400, detail="讨论已关闭，不能回复")
    r = DiscussionReply(discussion_id=discussion_id, author_id=user_id, content=content)
    db.add(r)
    db.commit()
    db.refresh(r)
    author = db.get(User, user_id)
    return {
        "id": r.id, "discussion_id": discussion_id, "content": r.content,
        "author": user_info(author) if author else {},
        "is_teacher": role == "teacher",
        "created_at": r.created_at,
    }


# ── 删除回复 ──────────────────────────────────────────────────

def delete_reply(course_id: str, discussion_id: str, reply_id: str,
                 user_id: str, role: str, db: Session) -> None:
    require_discussion(discussion_id, course_id, db)
    r = db.get(DiscussionReply, reply_id)
    if not r or r.discussion_id != discussion_id:
        raise HTTPException(status_code=404, detail="回复不存在")
    if role != "teacher" and r.author_id != user_id:
        raise HTTPException(status_code=403, detail="无权删除他人回复")
    db.delete(r)
    db.commit()


# ── 更新讨论状态（教师关闭/重开） ────────────────────────────

def update_discussion_status(course_id: str, teacher_id: str,
                              discussion_id: str, status: str, db: Session) -> dict:
    require_teacher_course(course_id, teacher_id, db)
    d = require_discussion(discussion_id, course_id, db)
    d.status = status
    db.commit()
    db.refresh(d)
    return {"id": d.id, "status": d.status}


# ── 删除讨论（教师） ─────────────────────────────────────────

def delete_discussion(course_id: str, teacher_id: str, discussion_id: str, db: Session) -> None:
    require_teacher_course(course_id, teacher_id, db)
    d = require_discussion(discussion_id, course_id, db)
    db.query(DiscussionReply).filter(DiscussionReply.discussion_id == discussion_id).delete()
    db.delete(d)
    db.commit()
