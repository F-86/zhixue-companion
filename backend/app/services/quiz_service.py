"""测试服务"""
import json
from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.quiz import Quiz, QuizAnswer, QuizAttempt, QuizQuestion
from app.services.course_service import _require_enrollment, _require_teacher_course


# ── 内部工具 ──────────────────────────────────────────────────

def _require_quiz(quiz_id: str, course_id: str, db: Session) -> Quiz:
    q = db.get(Quiz, quiz_id)
    if not q or q.course_id != course_id:
        raise HTTPException(status_code=404, detail="测试不存在")
    return q


def _require_attempt(attempt_id: str, student_id: str, db: Session) -> QuizAttempt:
    a = db.get(QuizAttempt, attempt_id)
    if not a or a.student_id != student_id:
        raise HTTPException(status_code=404, detail="作答记录不存在")
    return a


def _is_correct(question: QuizQuestion, student_answer: str) -> bool:
    """判断客观题答案是否正确（不区分大小写）。"""
    if not question.correct_answer:
        return False
    if question.question_type == "multi_choice":
        # 多选题：把答案拆成集合比较
        try:
            correct = set(json.loads(question.correct_answer))
            student = set(json.loads(student_answer))
        except Exception:
            correct = set(question.correct_answer.upper().split(","))
            student = set(student_answer.upper().split(","))
        return correct == student
    return question.correct_answer.strip().lower() == student_answer.strip().lower()


def _serialize_question(q: QuizQuestion, include_answer: bool = False) -> dict:
    d = {
        "id": q.id, "question_type": q.question_type,
        "content": q.content, "options": q.options,
        "score": q.score, "order": q.order,
    }
    if include_answer:
        d["correct_answer"] = q.correct_answer
        d["explanation"] = q.explanation
    return d


# ── 教师端 ────────────────────────────────────────────────────

def create_quiz(course_id: str, teacher_id: str, title: str,
                description: str | None, section_id: str | None,
                time_limit_minutes: int | None,
                questions: list[dict], db: Session) -> dict:
    _require_teacher_course(course_id, teacher_id, db)
    quiz = Quiz(
        course_id=course_id, section_id=section_id, teacher_id=teacher_id,
        title=title, description=description, time_limit_minutes=time_limit_minutes,
    )
    db.add(quiz)
    db.flush()  # 获取 quiz.id
    for i, q in enumerate(questions):
        db.add(QuizQuestion(
            quiz_id=quiz.id,
            question_type=q["question_type"],
            content=q["content"],
            options=q.get("options", []),
            correct_answer=q.get("correct_answer"),
            explanation=q.get("explanation"),
            score=q.get("score", 10.0),
            order=q.get("order", i),
        ))
    db.commit()
    db.refresh(quiz)
    return _get_quiz_detail(quiz, db, include_answer=True)


def list_teacher_quizzes(course_id: str, teacher_id: str,
                          section_id: str | None, status: str | None, db: Session) -> dict:
    _require_teacher_course(course_id, teacher_id, db)
    q = db.query(Quiz).filter(Quiz.course_id == course_id, Quiz.teacher_id == teacher_id)
    if section_id:
        q = q.filter(Quiz.section_id == section_id)
    if status:
        q = q.filter(Quiz.status == status)
    quizzes = q.order_by(Quiz.created_at.desc()).all()
    items = []
    for quiz in quizzes:
        q_count = db.query(QuizQuestion).filter(QuizQuestion.quiz_id == quiz.id).count()
        attempt_count = db.query(QuizAttempt).filter(
            QuizAttempt.quiz_id == quiz.id, QuizAttempt.status == "submitted"
        ).count()
        items.append({
            "id": quiz.id, "title": quiz.title, "section_id": quiz.section_id,
            "status": quiz.status, "question_count": q_count,
            "time_limit_minutes": quiz.time_limit_minutes,
            "attempt_count": attempt_count, "created_at": quiz.created_at,
        })
    return {"course_id": course_id, "items": items, "total": len(items)}


def update_quiz_status(course_id: str, teacher_id: str, quiz_id: str,
                        status: str, db: Session) -> dict:
    _require_teacher_course(course_id, teacher_id, db)
    quiz = _require_quiz(quiz_id, course_id, db)
    if quiz.teacher_id != teacher_id:
        raise HTTPException(status_code=403, detail="无权操作")
    quiz.status = status
    db.commit()
    return {"id": quiz.id, "status": quiz.status}


def get_quiz_attempts_summary(course_id: str, teacher_id: str, quiz_id: str, db: Session) -> dict:
    """教师查看所有学生的作答结果汇总。"""
    _require_teacher_course(course_id, teacher_id, db)
    _require_quiz(quiz_id, course_id, db)
    attempts = db.query(QuizAttempt).filter(
        QuizAttempt.quiz_id == quiz_id, QuizAttempt.status == "submitted"
    ).all()
    items = []
    for a in attempts:
        from app.models.user import User
        student = db.get(User, a.student_id)
        items.append({
            "attempt_id": a.id, "student_id": a.student_id,
            "student_name": student.name if student else "",
            "total_score": a.total_score, "full_score": a.full_score,
            "submitted_at": a.submitted_at,
        })
    scores = [i["total_score"] for i in items if i["total_score"] is not None]
    return {
        "quiz_id": quiz_id,
        "attempt_count": len(items),
        "average_score": round(sum(scores) / len(scores), 1) if scores else None,
        "items": items,
    }


# ── 学生端 ────────────────────────────────────────────────────

def list_student_quizzes(course_id: str, student_id: str,
                          section_id: str | None, db: Session) -> dict:
    _require_enrollment(course_id, student_id, db)
    q = db.query(Quiz).filter(Quiz.course_id == course_id, Quiz.status == "open")
    if section_id:
        q = q.filter(Quiz.section_id == section_id)
    quizzes = q.order_by(Quiz.created_at.desc()).all()
    items = []
    for quiz in quizzes:
        q_count = db.query(QuizQuestion).filter(QuizQuestion.quiz_id == quiz.id).count()
        attempt = db.query(QuizAttempt).filter(
            QuizAttempt.quiz_id == quiz.id, QuizAttempt.student_id == student_id,
        ).first()
        items.append({
            "id": quiz.id, "title": quiz.title, "section_id": quiz.section_id,
            "question_count": q_count, "time_limit_minutes": quiz.time_limit_minutes,
            "attempt_status": attempt.status if attempt else None,
            "score": attempt.total_score if attempt else None,
        })
    return {"course_id": course_id, "items": items, "total": len(items)}


def get_quiz_for_student(course_id: str, quiz_id: str, student_id: str, db: Session) -> dict:
    """学生获取测试详情，不包含正确答案。"""
    _require_enrollment(course_id, student_id, db)
    quiz = _require_quiz(quiz_id, course_id, db)
    questions = (
        db.query(QuizQuestion)
        .filter(QuizQuestion.quiz_id == quiz_id)
        .order_by(QuizQuestion.order).all()
    )
    attempt = db.query(QuizAttempt).filter(
        QuizAttempt.quiz_id == quiz_id, QuizAttempt.student_id == student_id,
    ).first()
    return {
        "id": quiz.id, "title": quiz.title, "description": quiz.description,
        "section_id": quiz.section_id, "time_limit_minutes": quiz.time_limit_minutes,
        "questions": [_serialize_question(q, include_answer=False) for q in questions],
        "attempt": {
            "id": attempt.id, "status": attempt.status,
            "total_score": attempt.total_score, "started_at": attempt.started_at,
        } if attempt else None,
    }


def start_attempt(course_id: str, quiz_id: str, student_id: str, db: Session) -> dict:
    """学生开始作答，创建 QuizAttempt 记录。"""
    _require_enrollment(course_id, student_id, db)
    quiz = _require_quiz(quiz_id, course_id, db)
    if quiz.status != "open":
        raise HTTPException(status_code=400, detail="测试已关闭")
    existing = db.query(QuizAttempt).filter(
        QuizAttempt.quiz_id == quiz_id, QuizAttempt.student_id == student_id,
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="已开始过该测试，请直接提交")
    attempt = QuizAttempt(quiz_id=quiz_id, student_id=student_id)
    db.add(attempt)
    db.commit()
    db.refresh(attempt)
    return {"attempt_id": attempt.id, "started_at": attempt.started_at}


def submit_attempt(course_id: str, quiz_id: str, attempt_id: str,
                   student_id: str, answers: list[dict], db: Session) -> dict:
    """
    学生提交答案。
    客观题（单选、多选、判断）自动批改；简答题调用 MiniMax 批改。
    answers: [{"question_id": str, "answer": str}, ...]
    """
    _require_enrollment(course_id, student_id, db)
    _require_quiz(quiz_id, course_id, db)
    attempt = _require_attempt(attempt_id, student_id, db)
    if attempt.status == "submitted":
        raise HTTPException(status_code=400, detail="已提交，不能重复提交")
    questions = {
        q.id: q for q in db.query(QuizQuestion).filter(QuizQuestion.quiz_id == quiz_id).all()
    }
    total_score = 0.0
    full_score = sum(q.score for q in questions.values())
    results = []
    for ans in answers:
        qid = ans.get("question_id")
        student_answer = ans.get("answer", "")
        question = questions.get(qid)
        if not question:
            continue
        # 避免重复答题
        existing_ans = db.query(QuizAnswer).filter(
            QuizAnswer.attempt_id == attempt_id,
            QuizAnswer.question_id == qid,
        ).first()
        if existing_ans:
            continue
        is_correct = None
        score = 0.0
        ai_feedback = None
        if question.question_type == "short_answer":
            # 简答题：调用 MiniMax 批改
            try:
                from app.services import minimax_client
                result = minimax_client.grade_quiz_answer(
                    question.content,
                    question.correct_answer or "",
                    student_answer,
                    question.score,
                )
                score = result.get("score", 0.0)
                ai_feedback = result.get("feedback", "")
                is_correct = score >= question.score * 0.6  # 60% 以上视为基本正确
            except Exception:
                score = 0.0
                ai_feedback = "自动批改暂时不可用"
        else:
            # 客观题：直接判断
            is_correct = _is_correct(question, student_answer)
            score = question.score if is_correct else 0.0
        total_score += score
        db.add(QuizAnswer(
            attempt_id=attempt_id, question_id=qid,
            answer=student_answer, is_correct=is_correct,
            score=score, ai_feedback=ai_feedback,
        ))
        results.append({
            "question_id": qid, "is_correct": is_correct,
            "score": score, "ai_feedback": ai_feedback,
            "correct_answer": question.correct_answer,
            "explanation": question.explanation,
        })
    attempt.status = "submitted"
    attempt.total_score = round(total_score, 1)
    attempt.full_score = full_score
    attempt.submitted_at = datetime.now(timezone.utc)
    db.commit()
    return {
        "attempt_id": attempt_id, "total_score": attempt.total_score,
        "full_score": full_score, "results": results,
    }


def get_attempt_result(course_id: str, quiz_id: str, attempt_id: str,
                        student_id: str, db: Session) -> dict:
    """学生查看已提交的测试结果（含正确答案和解析）。"""
    _require_enrollment(course_id, student_id, db)
    attempt = _require_attempt(attempt_id, student_id, db)
    if attempt.status != "submitted":
        raise HTTPException(status_code=400, detail="测试尚未提交")
    questions = (
        db.query(QuizQuestion)
        .filter(QuizQuestion.quiz_id == quiz_id)
        .order_by(QuizQuestion.order).all()
    )
    answers_map = {
        a.question_id: a
        for a in db.query(QuizAnswer).filter(QuizAnswer.attempt_id == attempt_id).all()
    }
    items = []
    for q in questions:
        a = answers_map.get(q.id)
        items.append({
            **_serialize_question(q, include_answer=True),
            "student_answer": a.answer if a else None,
            "is_correct": a.is_correct if a else None,
            "score": a.score if a else 0.0,
            "ai_feedback": a.ai_feedback if a else None,
        })
    return {
        "attempt_id": attempt_id, "quiz_id": quiz_id,
        "total_score": attempt.total_score, "full_score": attempt.full_score,
        "submitted_at": attempt.submitted_at, "questions": items,
    }


# ── 内部：供 _collect_signals 调用 ───────────────────────────

def get_quiz_scores_for_signals(course_id: str, student_id: str, db: Session) -> list[dict]:
    """返回学生在该课程所有测试中的得分记录，供学习计划生成使用。"""
    quizzes = db.query(Quiz).filter(Quiz.course_id == course_id).all()
    records = []
    for quiz in quizzes:
        attempt = db.query(QuizAttempt).filter(
            QuizAttempt.quiz_id == quiz.id,
            QuizAttempt.student_id == student_id,
            QuizAttempt.status == "submitted",
        ).first()
        if not attempt:
            continue
        # 找出错题对应的知识点（题目内容作为薄弱点描述）
        wrong_answers = db.query(QuizAnswer).filter(
            QuizAnswer.attempt_id == attempt.id,
            QuizAnswer.is_correct == False,
        ).all()
        wrong_questions = []
        for wa in wrong_answers:
            q = db.get(QuizQuestion, wa.question_id)
            if q:
                wrong_questions.append(q.content[:50])
        records.append({
            "quiz_title": quiz.title,
            "score": attempt.total_score,
            "full_score": attempt.full_score,
            "wrong_questions": wrong_questions,
        })
    return records


# ── 内部工具 ──────────────────────────────────────────────────

def _get_quiz_detail(quiz: Quiz, db: Session, include_answer: bool = False) -> dict:
    from app.models.section import Section
    questions = (
        db.query(QuizQuestion)
        .filter(QuizQuestion.quiz_id == quiz.id)
        .order_by(QuizQuestion.order).all()
    )
    sec = db.get(Section, quiz.section_id) if quiz.section_id else None
    return {
        "id": quiz.id, "course_id": quiz.course_id,
        "section_id": quiz.section_id,
        "section_title": sec.title if sec else None,
        "title": quiz.title, "description": quiz.description,
        "time_limit_minutes": quiz.time_limit_minutes,
        "status": quiz.status, "created_at": quiz.created_at,
        "questions": [_serialize_question(q, include_answer=include_answer) for q in questions],
    }
