import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _uuid() -> str:
    return str(uuid.uuid4())


class Submission(Base):
    __tablename__ = "submissions"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    assignment_id: Mapped[str] = mapped_column(String, nullable=False)
    student_id: Mapped[str] = mapped_column(String, nullable=False)
    # text | file
    submit_type: Mapped[str] = mapped_column(String, nullable=False)
    content: Mapped[str | None] = mapped_column(Text, nullable=True)
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    # submitted
    status: Mapped[str] = mapped_column(String, default="submitted")


class SubmissionFile(Base):
    """提交 ↔ 文件 关联表（多对多）"""
    __tablename__ = "submission_files"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    submission_id: Mapped[str] = mapped_column(String, ForeignKey("submissions.id"), nullable=False, index=True)
    file_id: Mapped[str] = mapped_column(String, ForeignKey("files.id"), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
