import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, Integer, JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _uuid() -> str:
    return str(uuid.uuid4())


class LearningPlan(Base):
    __tablename__ = "learning_plans"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    student_id: Mapped[str] = mapped_column(String, nullable=False)
    course_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    course: Mapped[str] = mapped_column(String, nullable=False)
    # 版本号，初始为 1，每次调整 +1
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    # 指向被调整的上一版计划，首次生成时为 None
    parent_plan_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    # 生成时使用的数据来源标签
    data_sources: Mapped[list] = mapped_column(JSON, default=list)
    basis: Mapped[dict] = mapped_column(JSON, default=dict)
    plan: Mapped[list] = mapped_column(JSON, default=list)
    analysis: Mapped[dict] = mapped_column(JSON, default=dict)
    # active | completed | archived（被新版本替代后自动 archived）
    status: Mapped[str] = mapped_column(String, default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)
