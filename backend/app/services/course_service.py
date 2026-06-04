"""课程管理服务"""
import random
import string

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.course import Course, CourseEnrollment
from app.models.user import User


def _gen_unique_code(db: Session) -> str:
    """生成不重复的 6 位课程码"""
    for _ in range(10):
        code = "".join(random.choices(string.ascii_uppercase + string.digits, k=6))
        if not db.query(Course).filter(Course.code == code).first():
            return code
    raise RuntimeError("无法生成唯一课程码，请重试")


# ── 教师端 ────────────────────────────────────────────────────

def create_course(teacher_id: str, name: str, description: str | None,
                  semester: str | None, cover_image_url: str | None, db: Session) -> Course:
    course = Course(
        teacher_id=teacher_id,
        name=name,
        description=description,
        semester=semester,
        cover_image_url=cover_image_url,
        code=_gen_unique_code(db),
    )
    db.add(course)
    db.commit()
    db.refresh(course)
    return course


def list_teacher_courses(teacher_id: str, status: str | None, keyword: str | None, db: Session) -> dict:
    from app.models.section import Section
    q = db.query(Course).filter(Course.teacher_id == teacher_id)
    if status:
        q = q.filter(Course.status == status)
    if keyword:
        q = q.filter(Course.name.contains(keyword))
    courses = q.order_by(Course.created_at.desc()).all()
    items = []
    for c in courses:
        student_count = db.query(CourseEnrollment).filter(CourseEnrollment.course_id == c.id).count()
        section_count = db.query(Section).filter(Section.course_id == c.id).count()
        items.append({
            "id": c.id, "name": c.name, "code": c.code, "semester": c.semester,
            "status": c.status, "student_count": student_count,
            "section_count": section_count, "created_at": c.created_at,
        })
    return {"items": items, "total": len(items)}


def get_teacher_course(course_id: str, teacher_id: str, db: Session) -> dict:
    c = _require_teacher_course(course_id, teacher_id, db)
    from app.models.section import Section
    student_count = db.query(CourseEnrollment).filter(CourseEnrollment.course_id == c.id).count()
    section_count = db.query(Section).filter(Section.course_id == c.id).count()
    return {
        "id": c.id, "name": c.name, "description": c.description,
        "code": c.code, "semester": c.semester, "status": c.status,
        "teacher_id": c.teacher_id, "student_count": student_count,
        "section_count": section_count, "created_at": c.created_at, "updated_at": c.updated_at,
    }


def update_course(course_id: str, teacher_id: str, name: str | None,
                  description: str | None, semester: str | None, db: Session) -> Course:
    c = _require_teacher_course(course_id, teacher_id, db)
    if name is not None:
        c.name = name
    if description is not None:
        c.description = description
    if semester is not None:
        c.semester = semester
    db.commit()
    db.refresh(c)
    return c


def archive_course(course_id: str, teacher_id: str, db: Session) -> Course:
    c = _require_teacher_course(course_id, teacher_id, db)
    c.status = "archived"
    db.commit()
    db.refresh(c)
    return c


def regenerate_code(course_id: str, teacher_id: str, db: Session) -> Course:
    c = _require_teacher_course(course_id, teacher_id, db)
    c.code = _gen_unique_code(db)
    db.commit()
    db.refresh(c)
    return c


def list_course_students(course_id: str, teacher_id: str, db: Session) -> dict:
    _require_teacher_course(course_id, teacher_id, db)
    from app.models.grade import AIGradingResult
    from app.models.submission import Submission
    from app.models.assignment import Assignment
    enrollments = db.query(CourseEnrollment).filter(CourseEnrollment.course_id == course_id).all()
    items = []
    for e in enrollments:
        student = db.get(User, e.student_id)
        if not student:
            continue
        # 计算课程总分
        total_score = _calc_total_score(course_id, e.student_id, db)
        items.append({
            "id": student.id, "username": student.username, "name": student.name,
            "class_name": (student.extra or {}).get("class_name", ""),
            "joined_at": e.joined_at, "total_score": total_score,
        })
    return {"course_id": course_id, "items": items, "total": len(items)}


def add_students_by_username(course_id: str, teacher_id: str,
                              usernames: list[str], db: Session) -> dict:
    _require_teacher_course(course_id, teacher_id, db)
    added, failed = [], []
    for username in usernames:
        student = db.query(User).filter(User.username == username, User.role == "student").first()
        if not student:
            failed.append({"username": username, "reason": "用户不存在"})
            continue
        already = db.query(CourseEnrollment).filter(
            CourseEnrollment.course_id == course_id,
            CourseEnrollment.student_id == student.id,
        ).first()
        if already:
            failed.append({"username": username, "reason": "已在课程中"})
            continue
        db.add(CourseEnrollment(course_id=course_id, student_id=student.id))
        added.append({"username": username, "name": student.name, "student_id": student.id})
    db.commit()
    return {"course_id": course_id, "added": added, "failed": failed}


def remove_student(course_id: str, teacher_id: str, student_id: str, db: Session) -> None:
    _require_teacher_course(course_id, teacher_id, db)
    e = db.query(CourseEnrollment).filter(
        CourseEnrollment.course_id == course_id,
        CourseEnrollment.student_id == student_id,
    ).first()
    if not e:
        raise HTTPException(status_code=404, detail="该学生不在课程中")
    db.delete(e)
    db.commit()


# ── 学生端 ────────────────────────────────────────────────────

def join_course(student_id: str, code: str, db: Session) -> dict:
    course = db.query(Course).filter(Course.code == code).first()
    if not course:
        raise HTTPException(status_code=404, detail="课程码无效或课程不存在")
    if course.status == "archived":
        raise HTTPException(status_code=400, detail="该课程已归档，无法加入")
    already = db.query(CourseEnrollment).filter(
        CourseEnrollment.course_id == course.id,
        CourseEnrollment.student_id == student_id,
    ).first()
    if already:
        raise HTTPException(status_code=400, detail="你已加入该课程")
    enrollment = CourseEnrollment(course_id=course.id, student_id=student_id)
    db.add(enrollment)
    db.commit()
    db.refresh(enrollment)
    teacher = db.get(User, course.teacher_id)
    return {
        "course_id": course.id, "course_name": course.name,
        "teacher_name": teacher.name if teacher else "",
        "semester": course.semester, "joined_at": enrollment.joined_at,
    }


def list_student_courses(student_id: str, status: str | None, db: Session) -> dict:
    from app.models.section import Section
    q = db.query(CourseEnrollment, Course).join(
        Course, CourseEnrollment.course_id == Course.id
    ).filter(CourseEnrollment.student_id == student_id)
    if status:
        q = q.filter(Course.status == status)
    rows = q.order_by(CourseEnrollment.joined_at.desc()).all()
    items = []
    for enrollment, course in rows:
        teacher = db.get(User, course.teacher_id)
        section_count = db.query(Section).filter(Section.course_id == course.id).count()
        total_score = _calc_total_score(course.id, student_id, db)
        items.append({
            "id": course.id, "name": course.name,
            "teacher_name": teacher.name if teacher else "",
            "semester": course.semester, "status": course.status,
            "section_count": section_count, "total_score": total_score,
            "joined_at": enrollment.joined_at,
        })
    return {"items": items, "total": len(items)}


def get_student_course(course_id: str, student_id: str, db: Session) -> dict:
    _require_enrollment(course_id, student_id, db)
    course = db.get(Course, course_id)
    from app.models.section import Section
    teacher = db.get(User, course.teacher_id)
    section_count = db.query(Section).filter(Section.course_id == course_id).count()
    total_score = _calc_total_score(course_id, student_id, db)
    enrollment = db.query(CourseEnrollment).filter(
        CourseEnrollment.course_id == course_id,
        CourseEnrollment.student_id == student_id,
    ).first()
    return {
        "id": course.id, "name": course.name, "description": course.description,
        "teacher_name": teacher.name if teacher else "",
        "semester": course.semester, "status": course.status,
        "section_count": section_count, "total_score": total_score,
        "joined_at": enrollment.joined_at,
    }


def quit_course(course_id: str, student_id: str, db: Session) -> None:
    e = db.query(CourseEnrollment).filter(
        CourseEnrollment.course_id == course_id,
        CourseEnrollment.student_id == student_id,
    ).first()
    if not e:
        raise HTTPException(status_code=404, detail="你未加入该课程")
    db.delete(e)
    db.commit()


# ── 内部工具函数 ──────────────────────────────────────────────

def _require_teacher_course(course_id: str, teacher_id: str, db: Session) -> Course:
    c = db.get(Course, course_id)
    if not c or c.teacher_id != teacher_id:
        raise HTTPException(status_code=404, detail="课程不存在")
    return c


def _require_enrollment(course_id: str, student_id: str, db: Session) -> CourseEnrollment:
    e = db.query(CourseEnrollment).filter(
        CourseEnrollment.course_id == course_id,
        CourseEnrollment.student_id == student_id,
    ).first()
    if not e:
        raise HTTPException(status_code=403, detail="你未加入该课程")
    return e


def _calc_total_score(course_id: str, student_id: str, db: Session) -> float | None:
    """计算学生在某课程内所有已确认批改结果的平均分"""
    from app.models.assignment import Assignment
    from app.models.grade import AIGradingResult
    from app.models.submission import Submission
    assignment_ids = [
        a.id for a in db.query(Assignment).filter(Assignment.course_id == course_id).all()
    ]
    if not assignment_ids:
        return None
    scores = []
    for aid in assignment_ids:
        sub = db.query(Submission).filter(
            Submission.assignment_id == aid,
            Submission.student_id == student_id,
        ).first()
        if not sub:
            continue
        grade = db.query(AIGradingResult).filter(
            AIGradingResult.submission_id == sub.id,
            AIGradingResult.confirmed == True,
        ).first()
        if grade and grade.final_score is not None:
            scores.append(grade.final_score)
    return round(sum(scores) / len(scores), 1) if scores else None
