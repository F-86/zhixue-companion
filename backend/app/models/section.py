import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _uuid() -> str:
    return str(uuid.uuid4())


class Section(Base):
    __tablename__ = "sections"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    course_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    title: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 排序序号，越小越靠前
    order: Mapped[int] = mapped_column(Integer, default=0)
    # 教师上传的课件/资料文件路径
    material_path: Mapped[str | None] = mapped_column(String, nullable=True)
    # C++ 服务提取的课件文本，用于 RAG 检索
    material_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 课件文本的 SHA-256 摘要，用于增量更新索引时比对内容是否变化
    material_hash: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)
