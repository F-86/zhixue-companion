import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, Float, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _uuid() -> str:
    return str(uuid.uuid4())


class Assignment(Base):
    __tablename__ = "assignments"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    teacher_id: Mapped[str] = mapped_column(String, nullable=False)
    course_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    section_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    title: Mapped[str] = mapped_column(String, nullable=False)
    # 冗余保留课程名，方便显示
    course: Mapped[str] = mapped_column(String, nullable=False)
    full_score: Mapped[float] = mapped_column(Float, nullable=False, default=100.0)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    reference_answer: Mapped[str | None] = mapped_column(Text, nullable=True)
    rubric: Mapped[str | None] = mapped_column(Text, nullable=True)
    attachment_file_id: Mapped[str | None] = mapped_column(String, ForeignKey("files.id"), nullable=True)
    # 以下两个字段仅作缓存/降级，通过 attachment_file_id 从 files 表可还原
    attachment_path: Mapped[str | None] = mapped_column(String, nullable=True)
    attachment_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # open | closed
    status: Mapped[str] = mapped_column(String, default="open")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)
