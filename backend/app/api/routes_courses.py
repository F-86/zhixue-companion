"""课程管理路由"""
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.services import course_service as svc
from app.services.auth_service import get_current_user, require_student, require_teacher

router = APIRouter(tags=["课程管理"])


def _ok(data, message="ok", status_code=200):
    return {"success": True, "data": data, "message": message}


# ── 请求体 ────────────────────────────────────────────────────

class CourseCreateRequest(BaseModel):
    name: str
    description: str | None = None
    semester: str | None = None
    cover_image_url: str | None = None


class CourseUpdateRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    semester: str | None = None


class AddStudentsRequest(BaseModel):
    usernames: list[str]


class JoinCourseRequest(BaseModel):
    code: str


# ── 教师端 ────────────────────────────────────────────────────

@router.post("/teacher/courses", status_code=201)
def create_course(req: CourseCreateRequest, current_user=Depends(require_teacher), db: Session = Depends(get_db)):
    c = svc.create_course(current_user.id, req.name, req.description, req.semester, req.cover_image_url, db)
    return _ok({
        "id": c.id, "name": c.name, "description": c.description, "code": c.code,
        "semester": c.semester, "status": c.status, "teacher_id": c.teacher_id,
        "student_count": 0, "created_at": c.created_at,
    }, "created")


@router.get("/teacher/courses")
def list_teacher_courses(status: str | None = None, keyword: str | None = None,
                          current_user=Depends(require_teacher), db: Session = Depends(get_db)):
    return _ok(svc.list_teacher_courses(current_user.id, status, keyword, db))


@router.get("/teacher/courses/{course_id}")
def get_teacher_course(course_id: str, current_user=Depends(require_teacher), db: Session = Depends(get_db)):
    return _ok(svc.get_teacher_course(course_id, current_user.id, db))


@router.patch("/teacher/courses/{course_id}")
def update_course(course_id: str, req: CourseUpdateRequest,
                   current_user=Depends(require_teacher), db: Session = Depends(get_db)):
    c = svc.update_course(course_id, current_user.id, req.name, req.description, req.semester, db)
    return _ok({"id": c.id, "name": c.name, "updated_at": c.updated_at}, "updated")


@router.post("/teacher/courses/{course_id}/archive")
def archive_course(course_id: str, current_user=Depends(require_teacher), db: Session = Depends(get_db)):
    c = svc.archive_course(course_id, current_user.id, db)
    return _ok({"id": c.id, "status": c.status}, "archived")


@router.post("/teacher/courses/{course_id}/regenerate-code")
def regenerate_code(course_id: str, current_user=Depends(require_teacher), db: Session = Depends(get_db)):
    c = svc.regenerate_code(course_id, current_user.id, db)
    return _ok({"id": c.id, "code": c.code}, "code regenerated")


@router.get("/teacher/courses/{course_id}/students")
def list_course_students(course_id: str, current_user=Depends(require_teacher), db: Session = Depends(get_db)):
    return _ok(svc.list_course_students(course_id, current_user.id, db))


@router.post("/teacher/courses/{course_id}/students", status_code=201)
def add_students(course_id: str, req: AddStudentsRequest,
                  current_user=Depends(require_teacher), db: Session = Depends(get_db)):
    return _ok(svc.add_students_by_username(course_id, current_user.id, req.usernames, db))


@router.delete("/teacher/courses/{course_id}/students/{student_id}")
def remove_student(course_id: str, student_id: str,
                    current_user=Depends(require_teacher), db: Session = Depends(get_db)):
    svc.remove_student(course_id, current_user.id, student_id, db)
    return _ok({"course_id": course_id, "student_id": student_id}, "removed")


# ── 学生端 ────────────────────────────────────────────────────

@router.post("/student/courses/join", status_code=201)
def join_course(req: JoinCourseRequest, current_user=Depends(require_student), db: Session = Depends(get_db)):
    return _ok(svc.join_course(current_user.id, req.code, db), "joined")


@router.get("/student/courses")
def list_student_courses(status: str | None = None,
                          current_user=Depends(require_student), db: Session = Depends(get_db)):
    return _ok(svc.list_student_courses(current_user.id, status, db))


@router.get("/student/courses/{course_id}")
def get_student_course(course_id: str, current_user=Depends(require_student), db: Session = Depends(get_db)):
    return _ok(svc.get_student_course(course_id, current_user.id, db))


@router.post("/student/courses/{course_id}/quit")
def quit_course(course_id: str, current_user=Depends(require_student), db: Session = Depends(get_db)):
    svc.quit_course(course_id, current_user.id, db)
    return _ok({"course_id": course_id}, "quit")
