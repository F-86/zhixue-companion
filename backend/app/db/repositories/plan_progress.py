"""数据库操作层 —— 学习计划进度查询"""
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.plan_progress import PlanTaskProgress


def mark_task(course_id: str, plan_id: str, student_id: str,
              day: int, completed: bool, feedback: str | None, db: Session,
              valid_days: set) -> dict:
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


def get_progress_map(plan_id: str, student_id: str, db: Session) -> dict:
    """返回 {day: PlanTaskProgress} 字典。"""
    return {
        r.day: r for r in db.query(PlanTaskProgress).filter(
            PlanTaskProgress.plan_id == plan_id,
            PlanTaskProgress.student_id == student_id,
        ).all()
    }


def list_progress_records(plan_id: str, student_id: str, db: Session) -> list[PlanTaskProgress]:
    return db.query(PlanTaskProgress).filter(
        PlanTaskProgress.plan_id == plan_id,
        PlanTaskProgress.student_id == student_id,
    ).order_by(PlanTaskProgress.day).all()
