"""个性化学习计划路由（含进度跟踪、效果反馈、多轮调整）"""
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.services import learning_plan_service as svc
from app.services import plan_progress_service as progress_svc
from app.services.auth_service import require_student

router = APIRouter(tags=["学习计划"])


def _ok(data, message="ok"):
    return {"success": True, "data": data, "message": message}


# ── 请求体 ────────────────────────────────────────────────────

class PlanCreateRequest(BaseModel):
    goal: str | None = None
    available_time_per_day: int = 60


class PlanStatusRequest(BaseModel):
    status: str


class TaskProgressRequest(BaseModel):
    day: int
    completed: bool
    feedback: str | None = None


class PlanAdjustRequest(BaseModel):
    feedback: str
    available_time_per_day: int | None = None


# ── 计划 CRUD ─────────────────────────────────────────────────

@router.post("/student/courses/{course_id}/learning-plans", status_code=201)
def create_plan(course_id: str, req: PlanCreateRequest,
                 current_user=Depends(require_student), db: Session = Depends(get_db)):
    return _ok(svc.create_plan(course_id, current_user.id, req.goal, req.available_time_per_day, db), "created")


@router.get("/student/courses/{course_id}/learning-plans")
def list_plans(course_id: str, status: str | None = None,
                current_user=Depends(require_student), db: Session = Depends(get_db)):
    return _ok(svc.list_plans(course_id, current_user.id, status, db))


@router.get("/student/courses/{course_id}/learning-plans/{plan_id}")
def get_plan(course_id: str, plan_id: str,
              current_user=Depends(require_student), db: Session = Depends(get_db)):
    return _ok(svc.get_plan(course_id, plan_id, current_user.id, db))


@router.patch("/student/courses/{course_id}/learning-plans/{plan_id}/status")
def update_plan_status(course_id: str, plan_id: str, req: PlanStatusRequest,
                        current_user=Depends(require_student), db: Session = Depends(get_db)):
    p = svc.update_plan_status(course_id, plan_id, current_user.id, req.status, db)
    return _ok({"id": p.id, "status": p.status, "updated_at": p.updated_at.isoformat()}, "updated")


# ── 进度跟踪 ──────────────────────────────────────────────────

@router.post("/student/courses/{course_id}/learning-plans/{plan_id}/progress")
def mark_task_progress(course_id: str, plan_id: str, req: TaskProgressRequest,
                        current_user=Depends(require_student), db: Session = Depends(get_db)):
    """标记某天任务完成情况，可携带文字反馈（如"太难了"、"已掌握"）。"""
    return _ok(progress_svc.mark_task(
        course_id, plan_id, current_user.id, req.day, req.completed, req.feedback, db,
    ), "updated")


@router.get("/student/courses/{course_id}/learning-plans/{plan_id}/progress")
def get_progress(course_id: str, plan_id: str,
                  current_user=Depends(require_student), db: Session = Depends(get_db)):
    """获取计划的整体进度，包含每天任务的完成状态。"""
    return _ok(progress_svc.get_progress(course_id, plan_id, current_user.id, db))


# ── 效果反馈 ──────────────────────────────────────────────────

@router.get("/student/courses/{course_id}/learning-plans/{plan_id}/effect")
def get_plan_effect(course_id: str, plan_id: str,
                     current_user=Depends(require_student), db: Session = Depends(get_db)):
    """对比计划实施前后的成绩变化，量化学习计划的效果。"""
    return _ok(progress_svc.get_plan_effect(course_id, plan_id, current_user.id, db))


# ── 多轮调整 ──────────────────────────────────────────────────

@router.post("/student/courses/{course_id}/learning-plans/{plan_id}/adjust", status_code=201)
def adjust_plan(course_id: str, plan_id: str, req: PlanAdjustRequest,
                 current_user=Depends(require_student), db: Session = Depends(get_db)):
    """
    基于当前完成进度和反馈，生成调整后的新版本计划。
    旧计划自动归档，返回新计划。
    """
    return _ok(progress_svc.adjust_plan(
        course_id, plan_id, current_user.id,
        req.feedback, req.available_time_per_day, db,
    ), "adjusted")
