"""学习计划进度跟踪、效果反馈与多轮调整服务 —— 业务编排层"""
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.db.repositories.course import require_enrollment as _require_enrollment
from app.db.repositories.learning_plan import (
    get_plan as get_plan_repo,
    archive_plan,
    create_new_version_plan,
)
from app.db.repositories.plan_progress import (
    mark_task as _repo_mark_task,
    get_progress_map,
    list_progress_records,
)


def mark_task(course_id: str, plan_id: str, student_id: str,
              day: int, completed: bool, feedback: str | None, db: Session) -> dict:
    """标记某天任务完成情况，先验证 day 在计划范围内。"""
    plan = get_plan_repo(course_id, plan_id, student_id, db)
    valid_days = {item.get("day") for item in plan.plan}
    return _repo_mark_task(course_id, plan_id, student_id, day, completed, feedback, db, valid_days)


def get_progress(course_id: str, plan_id: str, student_id: str, db: Session) -> dict:
    """获取计划的完整进度情况。"""
    _require_enrollment(course_id, student_id, db)
    plan = get_plan_repo(course_id, plan_id, student_id, db)
    progress_records = get_progress_map(plan_id, student_id, db)
    total = len(plan.plan)
    completed_count = sum(1 for r in progress_records.values() if r.completed)
    tasks = []
    for item in sorted(plan.plan, key=lambda x: x.get("day", 0)):
        day = item.get("day")
        record = progress_records.get(day)
        tasks.append({
            "day": day,
            "task": item.get("task"),
            "duration_minutes": item.get("duration_minutes"),
            "section_id": item.get("section_id"),
            "section_title": item.get("section_title"),
            "completed": record.completed if record else False,
            "feedback": record.feedback if record else None,
            "completed_at": record.completed_at if record else None,
        })
    return {
        "plan_id": plan_id, "version": plan.version,
        "total_days": total, "completed_days": completed_count,
        "completion_rate": round(completed_count / total, 2) if total else 0.0,
        "tasks": tasks,
    }


def get_plan_effect(course_id: str, plan_id: str, student_id: str, db: Session) -> dict:
    """计算计划实施前后的成绩变化。"""
    _require_enrollment(course_id, student_id, db)
    plan = get_plan_repo(course_id, plan_id, student_id, db)
    from app.models.assignment import Assignment
    from app.models.grade import AIGradingResult
    from app.models.submission import Submission
    assignments = db.query(Assignment).filter(Assignment.course_id == course_id).all()
    before, after = [], []
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
        if not grade or grade.final_score is None:
            continue
        rate = grade.final_score / a.full_score if a.full_score else 0
        record = {"title": a.title, "score": grade.final_score, "full_score": a.full_score, "rate": round(rate, 2)}
        if sub.submitted_at < plan.created_at:
            before.append(record)
        else:
            after.append(record)
    avg_before = round(sum(r["rate"] for r in before) / len(before), 2) if before else None
    avg_after = round(sum(r["rate"] for r in after) / len(after), 2) if after else None
    return {
        "plan_id": plan_id, "plan_created_at": plan.created_at,
        "assignment_effect": {
            "before": {"count": len(before), "avg_rate": avg_before, "records": before},
            "after": {"count": len(after), "avg_rate": avg_after, "records": after},
            "improvement": round(avg_after - avg_before, 2)
            if (avg_before is not None and avg_after is not None) else None,
        },
        "note": "improvement > 0 表示计划实施后成绩有所提升",
    }


def adjust_plan(course_id: str, plan_id: str, student_id: str,
                feedback: str, available_time_per_day: int | None,
                db: Session) -> dict:
    """基于学生反馈，生成调整后的新版本计划。"""
    _require_enrollment(course_id, student_id, db)
    plan = get_plan_repo(course_id, plan_id, student_id, db)
    if plan.status != "active":
        raise HTTPException(status_code=400, detail="只有进行中的计划才能调整")

    progress_records = list_progress_records(plan_id, student_id, db)
    progress = [
        {"day": r.day, "completed": r.completed, "feedback": r.feedback or ""}
        for r in sorted(progress_records, key=lambda x: x.day)
    ]
    minutes = available_time_per_day or plan.basis.get("available_time_per_day", 60)

    from app.models.course import Course
    from app.models.user import User
    course = db.get(Course, course_id)
    student = db.get(User, student_id)
    career_direction = (student.extra or {}).get("career_direction") if student else None

    from app.services.minimax_client import adjust_learning_plan
    result = adjust_learning_plan(
        course.name if course else "", plan.plan, progress, feedback, minutes,
    )

    archive_plan(course_id, plan_id, student_id, db)
    new_plan = create_new_version_plan(
        course_id, student_id, course.name if course else "",
        plan.id, plan.version, plan.data_sources,
        {**plan.basis, "available_time_per_day": minutes, "adjustment_feedback": feedback},
        result.get("plan", plan.plan), result.get("analysis", {}), db,
    )
    return {
        "id": new_plan.id, "course_id": course_id,
        "course_name": course.name if course else "",
        "career_direction": career_direction,
        "version": new_plan.version,
        "parent_plan_id": new_plan.parent_plan_id,
        "data_sources": new_plan.data_sources,
        "analysis": new_plan.analysis,
        "plan": new_plan.plan,
        "created_at": new_plan.created_at,
    }
