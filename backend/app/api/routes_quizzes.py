"""测试路由"""
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.services import quiz_service as svc
from app.services.auth_service import get_current_user, require_student, require_teacher

router = APIRouter(tags=["测试"])


def _ok(data, message="ok"):
    return {"success": True, "data": data, "message": message}


# ── 请求体 ────────────────────────────────────────────────────

class QuizQuestionIn(BaseModel):
    question_type: str  # single_choice | multi_choice | true_false | short_answer
    content: str
    options: list[dict] = []   # [{"key": "A", "text": "..."}]
    correct_answer: str | None = None
    explanation: str | None = None
    score: float = 10.0
    order: int = 0


class QuizCreateRequest(BaseModel):
    title: str
    description: str | None = None
    section_id: str | None = None
    time_limit_minutes: int | None = None
    questions: list[QuizQuestionIn]


class QuizStatusRequest(BaseModel):
    status: str  # open | closed


class AnswerIn(BaseModel):
    question_id: str
    answer: str


class SubmitRequest(BaseModel):
    answers: list[AnswerIn]


class SaveAnswerRequest(BaseModel):
    question_id: str
    answer: str


# ── 教师端 ────────────────────────────────────────────────────

@router.post("/teacher/courses/{course_id}/quizzes", status_code=201)
def create_quiz(course_id: str, req: QuizCreateRequest,
                 current_user=Depends(require_teacher), db: Session = Depends(get_db)):
    return _ok(svc.create_quiz(
        course_id, current_user.id, req.title, req.description,
        req.section_id, req.time_limit_minutes,
        [q.model_dump() for q in req.questions], db,
    ), "created")


@router.get("/teacher/courses/{course_id}/quizzes")
def list_teacher_quizzes(course_id: str, section_id: str | None = None, status: str | None = None,
                          current_user=Depends(require_teacher), db: Session = Depends(get_db)):
    return _ok(svc.list_teacher_quizzes(course_id, current_user.id, section_id, status, db))


@router.patch("/teacher/courses/{course_id}/quizzes/{quiz_id}")
def update_quiz_status(course_id: str, quiz_id: str, req: QuizStatusRequest,
                        current_user=Depends(require_teacher), db: Session = Depends(get_db)):
    return _ok(svc.update_quiz_status(course_id, current_user.id, quiz_id, req.status, db), "updated")


@router.get("/teacher/courses/{course_id}/quizzes/{quiz_id}/attempts")
def get_attempts_summary(course_id: str, quiz_id: str,
                          current_user=Depends(require_teacher), db: Session = Depends(get_db)):
    return _ok(svc.get_quiz_attempts_summary(course_id, current_user.id, quiz_id, db))


# ── 学生端 ────────────────────────────────────────────────────

@router.get("/student/courses/{course_id}/quizzes")
def list_student_quizzes(course_id: str, section_id: str | None = None,
                          current_user=Depends(require_student), db: Session = Depends(get_db)):
    return _ok(svc.list_student_quizzes(course_id, current_user.id, section_id, db))


@router.get("/student/courses/{course_id}/quizzes/{quiz_id}")
def get_quiz(course_id: str, quiz_id: str,
              current_user=Depends(require_student), db: Session = Depends(get_db)):
    return _ok(svc.get_quiz_for_student(course_id, quiz_id, current_user.id, db))


@router.post("/student/courses/{course_id}/quizzes/{quiz_id}/start", status_code=201)
def start_attempt(course_id: str, quiz_id: str,
                   current_user=Depends(require_student), db: Session = Depends(get_db)):
    return _ok(svc.start_attempt(course_id, quiz_id, current_user.id, db), "started")


@router.get("/student/courses/{course_id}/quizzes/{quiz_id}/attempts/{attempt_id}")
def get_attempt(course_id: str, quiz_id: str, attempt_id: str,
                current_user=Depends(require_student), db: Session = Depends(get_db)):
    """获取当前作答进度，用于继续作答。"""
    return _ok(svc.get_attempt_for_resume(course_id, quiz_id, attempt_id, current_user.id, db))


@router.put("/student/courses/{course_id}/quizzes/{quiz_id}/attempts/{attempt_id}/answers")
def save_answer(course_id: str, quiz_id: str, attempt_id: str,
                req: SaveAnswerRequest,
                current_user=Depends(require_student), db: Session = Depends(get_db)):
    """逐题保存答案，用于继续作答。"""
    return _ok(svc.save_answer(course_id, quiz_id, attempt_id, current_user.id,
                                req.question_id, req.answer, db), "saved")


@router.post("/student/courses/{course_id}/quizzes/{quiz_id}/attempts/{attempt_id}/submit")
def submit_attempt(course_id: str, quiz_id: str, attempt_id: str,
                    req: SubmitRequest,
                    current_user=Depends(require_student), db: Session = Depends(get_db)):
    return _ok(svc.submit_attempt(
        course_id, quiz_id, attempt_id, current_user.id,
        [a.model_dump() for a in req.answers], db,
    ), "submitted")


@router.get("/student/courses/{course_id}/quizzes/{quiz_id}/attempts/{attempt_id}/result")
def get_attempt_result(course_id: str, quiz_id: str, attempt_id: str,
                        current_user=Depends(require_student), db: Session = Depends(get_db)):
    return _ok(svc.get_attempt_result(course_id, quiz_id, attempt_id, current_user.id, db))
