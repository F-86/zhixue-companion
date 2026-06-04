import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _uuid() -> str:
    return str(uuid.uuid4())


class Question(Base):
    __tablename__ = "questions"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    course_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    section_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    asked_by: Mapped[str] = mapped_column(String, nullable=False)  # student user_id
    title: Mapped[str] = mapped_column(String, nullable=False)
    content: Mapped[str | None] = mapped_column(Text, nullable=True)
    # public | private
    visibility: Mapped[str] = mapped_column(String, default="public")
    # unanswered | answered
    status: Mapped[str] = mapped_column(String, default="unanswered")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class QuestionAnswer(Base):
    __tablename__ = "question_answers"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    question_id: Mapped[str] = mapped_column(String, nullable=False, unique=True, index=True)
    answered_by: Mapped[str] = mapped_column(String, nullable=False)  # teacher user_id
    content: Mapped[str] = mapped_column(Text, nullable=False)
    answered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
