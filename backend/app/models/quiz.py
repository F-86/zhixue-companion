import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Float, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _uuid() -> str:
    return str(uuid.uuid4())


class Quiz(Base):
    """教师发布的测试，包含多道题目。"""
    __tablename__ = "quizzes"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    course_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    section_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    teacher_id: Mapped[str] = mapped_column(String, nullable=False)
    title: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 时间限制（分钟），None 表示不限时
    time_limit_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # open | closed
    status: Mapped[str] = mapped_column(String, default="open")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)


class QuizQuestion(Base):
    """测试题目。支持单选、多选、判断、简答四种类型。"""
    __tablename__ = "quiz_questions"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    quiz_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    # single_choice | multi_choice | true_false | short_answer
    question_type: Mapped[str] = mapped_column(String, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    # 选择题选项列表，格式：[{"key": "A", "text": "..."}]
    options: Mapped[list] = mapped_column(JSON, default=list)
    # 正确答案：选择题为选项 key（多选用列表），判断题为 "true"/"false"，简答题为参考答案文本
    correct_answer: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 解析说明
    explanation: Mapped[str | None] = mapped_column(Text, nullable=True)
    score: Mapped[float] = mapped_column(Float, nullable=False, default=10.0)
    order: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class QuizAttempt(Base):
    """学生的一次测试作答记录（整体）。"""
    __tablename__ = "quiz_attempts"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    quiz_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    student_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    # in_progress | submitted
    status: Mapped[str] = mapped_column(String, default="in_progress")
    # 客观题自动得分，简答题 AI 批改后累计
    total_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    full_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class QuizAnswer(Base):
    """学生对单道题目的作答。"""
    __tablename__ = "quiz_answers"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    attempt_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    question_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    # 学生提交的答案（选择题为选项 key，简答题为文本）
    answer: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 客观题：直接判断是否正确；简答题：AI 批改后填入
    is_correct: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    score: Mapped[float | None] = mapped_column(Float, nullable=True)
    # 简答题 AI 批改评语
    ai_feedback: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
