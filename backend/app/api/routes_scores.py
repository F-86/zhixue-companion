"""成绩路由"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.services import score_service as svc
from app.services.auth_service import require_student, require_teacher

router = APIRouter(tags=["成绩"])


def _ok(data, message="ok"):
    return {"success": True, "data": data, "message": message}


# ── 学生端 ────────────────────────────────────────────────────

@router.get("/student/courses/{course_id}/scores")
def get_course_scores(course_id: str, current_user=Depends(require_student), db: Session = Depends(get_db)):
    return _ok(svc.get_student_course_scores(course_id, current_user.id, db))


@router.get("/student/scores")
def get_all_scores(current_user=Depends(require_student), db: Session = Depends(get_db)):
    return _ok(svc.get_all_course_scores(current_user.id, db))


# ── 教师端 ────────────────────────────────────────────────────

@router.get("/teacher/courses/{course_id}/scores")
def get_course_distribution(course_id: str, sort_by: str = "total_score", order: str = "desc",
                              current_user=Depends(require_teacher), db: Session = Depends(get_db)):
    return _ok(svc.get_course_score_distribution(course_id, current_user.id, sort_by, order, db))


@router.get("/teacher/courses/{course_id}/scores/{student_id}")
def get_student_detail(course_id: str, student_id: str,
                        current_user=Depends(require_teacher), db: Session = Depends(get_db)):
    return _ok(svc.get_student_detail_score(course_id, current_user.id, student_id, db))
