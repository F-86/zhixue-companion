"""数据库操作层 —— 成绩查询"""
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.assignment import Assignment
from app.models.course import Course, CourseEnrollment
from app.models.grade import AIGradingResult
from app.models.section import Section
from app.models.submission import Submission
from app.models.user import User
from app.db.repositories.course import require_enrollment, require_teacher_course, calc_total_score


# ── 学生端 ────────────────────────────────────────────────────

def get_student_course_scores(course_id: str, student_id: str, db: Session) -> dict:
    require_enrollment(course_id, student_id, db)
    course = db.get(Course, course_id)
    assignments = db.query(Assignment).filter(Assignment.course_id == course_id).all()
    records = []
    scores = []
    for a in assignments:
        sub = db.query(Submission).filter(
            Submission.assignment_id == a.id,
            Submission.student_id == student_id,
        ).first()
        if not sub:
            continue
        grade = db.query(AIGradingResult).filter(
            AIGradingResult.submission_id == sub.id,
            AIGradingResult.confirmed == True,
        ).first()
        if not grade:
            continue
        section = db.get(Section, a.section_id) if a.section_id else None
        records.append({
            "assignment_id": a.id, "assignment_title": a.title,
            "section_title": section.title if section else None,
            "full_score": a.full_score,
            "score": grade.final_score, "ai_score": grade.ai_score,
            "teacher_comment": grade.teacher_comment, "graded_at": grade.created_at,
        })
        if grade.final_score is not None:
            scores.append(grade.final_score)
    total_score = round(sum(scores) / len(scores), 1) if scores else None
    rank = calc_rank(course_id, student_id, total_score, db)
    total_students = db.query(CourseEnrollment).filter(CourseEnrollment.course_id == course_id).count()
    return {
        "course_id": course_id, "course_name": course.name if course else "",
        "total_score": total_score, "rank": rank, "total_students": total_students,
        "records": records,
    }


def get_all_course_scores(student_id: str, db: Session) -> dict:
    enrollments = db.query(CourseEnrollment).filter(
        CourseEnrollment.student_id == student_id
    ).all()
    items = []
    for e in enrollments:
        course = db.get(Course, e.course_id)
        if not course:
            continue
        assignments = db.query(Assignment).filter(Assignment.course_id == e.course_id).all()
        total_assignments = len(assignments)
        graded, scores = 0, []
        for a in assignments:
            sub = db.query(Submission).filter(
                Submission.assignment_id == a.id,
                Submission.student_id == student_id,
            ).first()
            if not sub:
                continue
            grade = db.query(AIGradingResult).filter(
                AIGradingResult.submission_id == sub.id,
                AIGradingResult.confirmed == True,
            ).first()
            if grade and grade.final_score is not None:
                graded += 1
                scores.append(grade.final_score)
        total_score = round(sum(scores) / len(scores), 1) if scores else None
        rank = calc_rank(e.course_id, student_id, total_score, db)
        total_students = db.query(CourseEnrollment).filter(CourseEnrollment.course_id == e.course_id).count()
        items.append({
            "course_id": e.course_id, "course_name": course.name,
            "total_score": total_score, "rank": rank, "total_students": total_students,
            "graded_assignments": graded, "total_assignments": total_assignments,
        })
    return {"items": items}


# ── 教师端 ────────────────────────────────────────────────────

def get_course_score_distribution(course_id: str, teacher_id: str,
                                   sort_by: str, order: str, db: Session) -> dict:
    require_teacher_course(course_id, teacher_id, db)
    course = db.get(Course, course_id)
    enrollments = db.query(CourseEnrollment).filter(CourseEnrollment.course_id == course_id).all()
    student_scores = []
    for e in enrollments:
        student = db.get(User, e.student_id)
        if not student:
            continue
        total = calc_total_score(course_id, e.student_id, db)
        student_scores.append((student, total))
    reverse = (order == "desc")
    if sort_by == "name":
        student_scores.sort(key=lambda x: x[0].name, reverse=reverse)
    else:
        student_scores.sort(key=lambda x: (x[1] is None, -(x[1] or 0)), reverse=not reverse)
    valid_scores = [s for _, s in student_scores if s is not None]
    dist = {"90_100": 0, "80_89": 0, "70_79": 0, "60_69": 0, "below_60": 0}
    for s in valid_scores:
        if s >= 90:
            dist["90_100"] += 1
        elif s >= 80:
            dist["80_89"] += 1
        elif s >= 70:
            dist["70_79"] += 1
        elif s >= 60:
            dist["60_69"] += 1
        else:
            dist["below_60"] += 1
    avg = round(sum(valid_scores) / len(valid_scores), 1) if valid_scores else None
    pass_count = sum(1 for s in valid_scores if s >= 60)
    exc_count = sum(1 for s in valid_scores if s >= 90)
    items = []
    for rank_idx, (student, total) in enumerate(student_scores, start=1):
        items.append({
            "student_id": student.id, "student_name": student.name,
            "class_name": (student.extra or {}).get("class_name", ""),
            "total_score": total,
            "graded_assignments": count_graded(course_id, student.id, db),
            "rank": rank_idx,
        })
    return {
        "course_id": course_id, "course_name": course.name if course else "",
        "statistics": {
            "average_score": avg,
            "max_score": max(valid_scores) if valid_scores else None,
            "min_score": min(valid_scores) if valid_scores else None,
            "pass_rate": round(pass_count / len(valid_scores), 2) if valid_scores else None,
            "excellent_rate": round(exc_count / len(valid_scores), 2) if valid_scores else None,
        },
        "score_distribution": dist,
        "items": items, "total": len(items),
    }


def get_student_detail_score(course_id: str, teacher_id: str,
                              student_id: str, db: Session) -> dict:
    require_teacher_course(course_id, teacher_id, db)
    student = db.get(User, student_id)
    if not student:
        raise HTTPException(status_code=404, detail="学生不存在")
    assignments = db.query(Assignment).filter(Assignment.course_id == course_id).all()
    records = []
    scores = []
    for a in assignments:
        sub = db.query(Submission).filter(
            Submission.assignment_id == a.id,
            Submission.student_id == student_id,
        ).first()
        if not sub:
            continue
        grade = db.query(AIGradingResult).filter(
            AIGradingResult.submission_id == sub.id,
            AIGradingResult.confirmed == True,
        ).first()
        if not grade:
            continue
        section = db.get(Section, a.section_id) if a.section_id else None
        records.append({
            "assignment_id": a.id, "assignment_title": a.title,
            "section_title": section.title if section else None,
            "full_score": a.full_score,
            "score": grade.final_score, "ai_score": grade.ai_score,
            "deductions": grade.deductions, "suggestions": grade.suggestions,
            "teacher_comment": grade.teacher_comment, "graded_at": grade.created_at,
        })
        if grade.final_score is not None:
            scores.append(grade.final_score)
    total_score = round(sum(scores) / len(scores), 1) if scores else None
    rank = calc_rank(course_id, student_id, total_score, db)
    return {
        "student_id": student_id, "student_name": student.name,
        "course_id": course_id, "total_score": total_score, "rank": rank,
        "records": records,
    }


# ── 内部工具 ──────────────────────────────────────────────────

def calc_rank(course_id: str, student_id: str, my_score: float | None, db: Session) -> int | None:
    if my_score is None:
        return None
    enrollments = db.query(CourseEnrollment).filter(CourseEnrollment.course_id == course_id).all()
    rank = 1
    for e in enrollments:
        if e.student_id == student_id:
            continue
        s = calc_total_score(course_id, e.student_id, db)
        if s is not None and s > my_score:
            rank += 1
    return rank


def count_graded(course_id: str, student_id: str, db: Session) -> int:
    assignments = db.query(Assignment).filter(Assignment.course_id == course_id).all()
    count = 0
    for a in assignments:
        sub = db.query(Submission).filter(
            Submission.assignment_id == a.id,
            Submission.student_id == student_id,
        ).first()
        if sub:
            grade = db.query(AIGradingResult).filter(
                AIGradingResult.submission_id == sub.id,
                AIGradingResult.confirmed == True,
            ).first()
            if grade:
                count += 1
    return count
