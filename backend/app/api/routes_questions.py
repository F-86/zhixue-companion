"""提问路由"""
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.services import question_service as svc
from app.services.auth_service import get_current_user, require_student, require_teacher

router = APIRouter(tags=["提问"])


def _ok(data, message="ok"):
    return {"success": True, "data": data, "message": message}


class QuestionCreateRequest(BaseModel):
    title: str
    content: str | None = None
    visibility: str = "public"  # public | private
    section_id: str | None = None


class VisibilityUpdateRequest(BaseModel):
    visibility: str


class AnswerRequest(BaseModel):
    content: str


# ── 学生提问 ──────────────────────────────────────────────────

@router.post("/courses/{course_id}/questions", status_code=201)
def create_question(course_id: str, req: QuestionCreateRequest,
                     current_user=Depends(require_student), db: Session = Depends(get_db)):
    return _ok(svc.create_question(
        course_id, current_user.id, req.title, req.content,
        req.visibility, req.section_id, db,
    ), "created")


# ── 列表/详情（师生通用） ──────────────────────────────────────

@router.get("/courses/{course_id}/questions")
def list_questions(course_id: str, section_id: str | None = None,
                    status: str | None = None, visibility: str | None = None,
                    current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    return _ok(svc.list_questions(
        course_id, current_user.id, current_user.role,
        section_id, status, visibility, db,
    ))


@router.get("/courses/{course_id}/questions/{question_id}")
def get_question(course_id: str, question_id: str,
                  current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    return _ok(svc.get_question(course_id, question_id, current_user.id, current_user.role, db))


# ── 教师回答 ──────────────────────────────────────────────────

@router.post("/courses/{course_id}/questions/{question_id}/answer")
def answer_question(course_id: str, question_id: str, req: AnswerRequest,
                     current_user=Depends(require_teacher), db: Session = Depends(get_db)):
    return _ok(svc.answer_question(course_id, current_user.id, question_id, req.content, db), "answered")


# ── 修改可见性 ────────────────────────────────────────────────

@router.patch("/courses/{course_id}/questions/{question_id}")
def update_visibility(course_id: str, question_id: str, req: VisibilityUpdateRequest,
                       current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    return _ok(svc.update_visibility(
        course_id, question_id, current_user.id, current_user.role, req.visibility, db,
    ), "updated")


# ── 删除问题 ──────────────────────────────────────────────────

@router.delete("/courses/{course_id}/questions/{question_id}")
def delete_question(course_id: str, question_id: str,
                     current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    svc.delete_question(course_id, question_id, current_user.id, current_user.role, db)
    return _ok({"id": question_id}, "deleted")
