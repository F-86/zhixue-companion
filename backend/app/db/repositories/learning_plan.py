"""数据库操作层 —— 学习计划查询"""
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.learning_plan import LearningPlan
from app.db.repositories.course import require_enrollment


def require_plan(plan_id: str, student_id: str, course_id: str, db: Session) -> LearningPlan:
    p = db.get(LearningPlan, plan_id)
    if not p or p.student_id != student_id or p.course_id != course_id:
        raise HTTPException(status_code=404, detail="学习计划不存在")
    return p


def create_plan_obj(course_id: str, student_id: str, course_name: str,
                     data_sources: list, basis: dict, plan_data: list,
                     analysis: dict, db: Session) -> LearningPlan:
    plan_obj = LearningPlan(
        student_id=student_id, course_id=course_id, course=course_name,
        data_sources=data_sources, basis=basis,
        plan=plan_data, analysis=analysis,
    )
    db.add(plan_obj)
    db.commit()
    db.refresh(plan_obj)
    return plan_obj


def list_plans(course_id: str, student_id: str, status: str | None, db: Session) -> list[LearningPlan]:
    q = db.query(LearningPlan).filter(
        LearningPlan.student_id == student_id, LearningPlan.course_id == course_id,
    )
    if status:
        q = q.filter(LearningPlan.status == status)
    return q.order_by(LearningPlan.created_at.desc()).all()


def get_plan(course_id: str, plan_id: str, student_id: str, db: Session) -> LearningPlan:
    return require_plan(plan_id, student_id, course_id, db)


def update_plan_status(course_id: str, plan_id: str, student_id: str,
                        status: str, db: Session) -> LearningPlan:
    p = require_plan(plan_id, student_id, course_id, db)
    p.status = status
    db.commit()
    db.refresh(p)
    return p


def archive_plan(course_id: str, plan_id: str, student_id: str, db: Session) -> LearningPlan:
    return update_plan_status(course_id, plan_id, student_id, "archived", db)


def create_new_version_plan(
    course_id: str, student_id: str, course_name: str,
    parent_plan_id: str, version: int,
    data_sources: list, basis: dict, plan_data: list,
    analysis: dict, db: Session,
) -> LearningPlan:
    new_plan = LearningPlan(
        student_id=student_id, course_id=course_id,
        course=course_name,
        version=version + 1,
        parent_plan_id=parent_plan_id,
        data_sources=data_sources,
        basis=basis,
        plan=plan_data,
        analysis=analysis,
    )
    db.add(new_plan)
    db.commit()
    db.refresh(new_plan)
    return new_plan
