"""学习计划进度跟踪、效果反馈与多轮调整服务"""
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.learning_plan import LearningPlan
from app.models.plan_progress import PlanTaskProgress
from app.services.course_service import _require_enrollment


def _require_plan(plan_id: str, student_id: str, course_id: str, db: Session) -> LearningPlan:
    p = db.get(LearningPlan, plan_id)
    if not p or p.student_id != student_id or p.course_id != course_id:
        raise HTTPException(status_code=404, detail="学习计划不存在")
    return p


# ── 进度打卡 ──────────────────────────────────────────────────

def mark_task(course_id: str, plan_id: str, student_id: str,
              day: int, completed: bool, feedback: str | None, db: Session) -> dict:
    """
    标记某天任务完成情况。重复调用时更新已有记录。
    """
    _require_enrollment(course_id, student_id, db)
    plan = _require_plan(plan_id, student_id, course_id, db)
    # 验证 day 在计划范围内
    valid_days = {item.get("day") for item in plan.plan}
    if day not in valid_days:
        raise HTTPException(status_code=400, detail=f"计划中不存在第 {day} 天的任务")
    existing = db.query(PlanTaskProgress).filter(
        PlanTaskProgress.plan_id == plan_id,
        PlanTaskProgress.student_id == student_id,
        PlanTaskProgress.day == day,
    ).first()
    if existing:
        existing.completed = completed
        existing.feedback = feedback
        existing.completed_at = datetime.now(timezone.utc) if completed else None
        db.commit()
        db.refresh(existing)
        record = existing
    else:
        record = PlanTaskProgress(
            plan_id=plan_id, student_id=student_id, day=day,
            completed=completed, feedback=feedback,
            completed_at=datetime.now(timezone.utc) if completed else None,
        )
        db.add(record)
        db.commit()
        db.refresh(record)
    return {
        "plan_id": plan_id, "day": day,
        "completed": record.completed, "feedback": record.feedback,
        "completed_at": record.completed_at,
    }


def get_progress(course_id: str, plan_id: str, student_id: str, db: Session) -> dict:
    """获取计划的完整进度情况，包含每天任务的完成状态。"""
    _require_enrollment(course_id, student_id, db)
    plan = _require_plan(plan_id, student_id, course_id, db)
    progress_records = {
        r.day: r for r in db.query(PlanTaskProgress).filter(
            PlanTaskProgress.plan_id == plan_id,
            PlanTaskProgress.student_id == student_id,
        ).all()
    }
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
        "plan_id": plan_id,
        "version": plan.version,
        "total_days": total,
        "completed_days": completed_count,
        "completion_rate": round(completed_count / total, 2) if total else 0.0,
        "tasks": tasks,
    }


# ── 效果反馈 ──────────────────────────────────────────────────

def get_plan_effect(course_id: str, plan_id: str, student_id: str, db: Session) -> dict:
    """
    计算计划实施前后的成绩变化，作为效果反馈。
    比较计划创建时间前后各作业的得分趋势。
    """
    _require_enrollment(course_id, student_id, db)
    plan = _require_plan(plan_id, student_id, course_id, db)
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
        record = {
            "title": a.title,
            "score": grade.final_score,
            "full_score": a.full_score,
            "rate": round(rate, 2),
        }
        if sub.submitted_at < plan.created_at:
            before.append(record)
        else:
            after.append(record)
    avg_before = round(sum(r["rate"] for r in before) / len(before), 2) if before else None
    avg_after = round(sum(r["rate"] for r in after) / len(after), 2) if after else None
    # 测试成绩变化
    from app.services.quiz_service import get_quiz_scores_for_signals
    quiz_records = get_quiz_scores_for_signals(course_id, student_id, db)
    quiz_before = [r for r in quiz_records if r.get("submitted_at", plan.created_at) < plan.created_at]
    quiz_after = [r for r in quiz_records if r.get("submitted_at", plan.created_at) >= plan.created_at]
    return {
        "plan_id": plan_id,
        "plan_created_at": plan.created_at,
        "assignment_effect": {
            "before": {"count": len(before), "avg_rate": avg_before, "records": before},
            "after": {"count": len(after), "avg_rate": avg_after, "records": after},
            "improvement": round(avg_after - avg_before, 2)
            if (avg_before is not None and avg_after is not None) else None,
        },
        "note": "improvement > 0 表示计划实施后成绩有所提升",
    }


# ── 多轮调整 ──────────────────────────────────────────────────

def adjust_plan(course_id: str, plan_id: str, student_id: str,
                feedback: str, available_time_per_day: int | None,
                db: Session) -> dict:
    """
    基于学生的完成进度和主动反馈，生成调整后的新版本计划。
    旧计划状态改为 archived，新计划 version +1，parent_plan_id 指向旧计划。
    """
    _require_enrollment(course_id, student_id, db)
    plan = _require_plan(plan_id, student_id, course_id, db)
    if plan.status != "active":
        raise HTTPException(status_code=400, detail="只有进行中的计划才能调整")
    # 获取当前进度
    progress_records = db.query(PlanTaskProgress).filter(
        PlanTaskProgress.plan_id == plan_id,
        PlanTaskProgress.student_id == student_id,
    ).all()
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
    from app.services import minimax_client
    result = minimax_client.adjust_learning_plan(
        course.name if course else "",
        plan.plan, progress, feedback, minutes,
    )
    # 旧计划归档
    plan.status = "archived"
    db.commit()
    # 创建新版本计划，继承 data_sources 和 basis，plan/analysis 替换为调整后的结果
    new_plan = LearningPlan(
        student_id=student_id, course_id=course_id,
        course=course.name if course else "",
        version=plan.version + 1,
        parent_plan_id=plan.id,
        data_sources=plan.data_sources,
        basis={**plan.basis, "available_time_per_day": minutes, "adjustment_feedback": feedback},
        plan=result.get("plan", plan.plan),
        analysis=result.get("analysis", {}),
    )
    db.add(new_plan)
    db.commit()
    db.refresh(new_plan)
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
