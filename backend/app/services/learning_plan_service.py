"""个性化学习计划服务（综合所有数据信号 + RAG）—— 业务编排层"""
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.db.repositories.course import require_enrollment as _require_enrollment, get_course_name
from app.db.repositories.learning_plan import (
    create_plan_obj,
    list_plans as list_plans_repo,
    get_plan as get_plan_repo,
    update_plan_status,
)


def _collect_signals(course_id: str, student_id: str, db: Session) -> tuple[dict, list[str]]:
    """采集所有数据信号，返回 (basis_dict, data_sources_list)"""
    from app.models.assignment import Assignment
    from app.models.chat import ChatMessage
    from app.models.course import Course
    from app.models.discussion import Discussion, DiscussionReply
    from app.models.grade import AIGradingResult
    from app.models.question import Question
    from app.models.submission import Submission
    from app.models.summary import Summary
    from app.models.user import User

    basis: dict = {}
    data_sources: list[str] = []
    student = db.get(User, student_id)

    if student and student.extra:
        profile = {k: v for k, v in student.extra.items() if k in ("interests", "career_direction")}
        if profile:
            basis["profile"] = profile
            data_sources.append("profile")

    assignments = db.query(Assignment).filter(Assignment.course_id == course_id).all()
    grade_records = []
    for a in assignments:
        sub = db.query(Submission).filter(
            Submission.assignment_id == a.id,
            Submission.student_id == student_id,
        ).first()
        if not sub:
            continue
        grade = db.query(AIGradingResult).filter(
            AIGradingResult.submission_id == sub.id,
            AIGradingResult.confirmed == True,
        ).first()
        if grade:
            grade_records.append({
                "title": a.title, "score": grade.final_score, "full_score": a.full_score,
                "weak_points": [d.get("point", "") if isinstance(d, dict) else d
                                for d in (grade.deductions or [])],
            })
    if grade_records:
        basis["grade_records"] = grade_records
        data_sources.append("scores")

    chat_msgs = (
        db.query(ChatMessage)
        .filter(ChatMessage.user_id == student_id, ChatMessage.course_id == course_id, ChatMessage.role == "user")
        .order_by(ChatMessage.created_at.desc()).limit(20).all()
    )
    if chat_msgs:
        basis["recent_questions"] = [m.content for m in chat_msgs[:10]]
        data_sources.append("chat_sessions")

    summaries = (
        db.query(Summary)
        .filter(Summary.user_id == student_id, Summary.course_id == course_id)
        .order_by(Summary.created_at.desc()).limit(10).all()
    )
    if summaries:
        basis["summaries"] = [s.title for s in summaries]
        data_sources.append("summaries")

    questions = (
        db.query(Question)
        .filter(Question.course_id == course_id, Question.asked_by == student_id)
        .order_by(Question.created_at.desc()).limit(10).all()
    )
    if questions:
        basis["questions_asked"] = [q.title for q in questions]
        data_sources.append("questions")

    replied = db.query(DiscussionReply).filter(DiscussionReply.author_id == student_id).all()
    if replied:
        disc_ids = {r.discussion_id for r in replied}
        titles = []
        for did in list(disc_ids)[:5]:
            d = db.get(Discussion, did)
            if d and d.course_id == course_id:
                titles.append(d.title)
        if titles:
            basis["discussions_participated"] = titles
            data_sources.append("discussions")

    from app.db.repositories.quiz import get_quiz_scores_for_signals
    quiz_records = get_quiz_scores_for_signals(course_id, student_id, db)
    if quiz_records:
        basis["quiz_records"] = quiz_records
        data_sources.append("quizzes")

    return basis, data_sources


def _rag_retrieve_for_plan(course_id: str, weak_points: list[str], db: Session) -> list[dict]:
    if not weak_points:
        return []
    query = " ".join(wp for wp in weak_points if wp)
    try:
        import logging
        from app.services.minimax_client import embed_query
        from app.db.vector_store import query_chunks
        query_embedding = embed_query(query)
        return query_chunks(query_embedding, course_id, top_k=3)
    except Exception:
        logging.getLogger(__name__).warning("学习计划 RAG 检索失败，跳过", exc_info=True)
        return []


def create_plan(course_id: str, student_id: str, goal: str | None,
                available_time_per_day: int, plan_days: int, db: Session) -> dict:
    _require_enrollment(course_id, student_id, db)
    from app.models.course import Course
    from app.models.user import User
    course = db.get(Course, course_id)
    if not course:
        raise HTTPException(status_code=404, detail="课程不存在")
    basis, data_sources = _collect_signals(course_id, student_id, db)
    basis["available_time_per_day"] = available_time_per_day
    if goal:
        basis["goal"] = goal

    weak_points = []
    for rec in basis.get("grade_records", []):
        weak_points.extend(rec.get("weak_points", []))
    for rec in basis.get("quiz_records", []):
        weak_points.extend(rec.get("wrong_questions", []))
    rag_refs = _rag_retrieve_for_plan(course_id, weak_points, db)
    if rag_refs:
        basis["course_material_excerpts"] = [r["excerpt"] for r in rag_refs]
        data_sources.append("course_materials")

    from app.services.minimax_client import generate_learning_plan
    effective_goal = goal or "根据学情数据制定合适的学习计划"
    result = generate_learning_plan(course.name, effective_goal, basis, available_time_per_day, plan_days)

    student = db.get(User, student_id)
    career_direction = (student.extra or {}).get("career_direction") if student else None
    plan_obj = create_plan_obj(course_id, student_id, course.name, data_sources, basis,
                                result.get("plan", []), result.get("analysis", {}), db)
    return {
        "id": plan_obj.id, "course_id": course_id, "course_name": course.name,
        "career_direction": career_direction, "data_sources": data_sources,
        "analysis": plan_obj.analysis, "rag_references": rag_refs,
        "plan": plan_obj.plan, "created_at": plan_obj.created_at.isoformat(),
    }


def list_plans(course_id: str, student_id: str, status: str | None, db: Session) -> dict:
    _require_enrollment(course_id, student_id, db)
    from app.models.course import Course
    from app.models.user import User
    plans = list_plans_repo(course_id, student_id, status, db)
    course = db.get(Course, course_id)
    student = db.get(User, student_id)
    career_direction = (student.extra or {}).get("career_direction") if student else None
    items = [{
        "id": p.id, "course_id": course_id, "course_name": course.name if course else "",
        "status": p.status, "career_direction": career_direction,
        "data_sources": p.data_sources, "created_at": p.created_at.isoformat(),
    } for p in plans]
    return {"course_id": course_id, "items": items, "total": len(items)}


def get_plan(course_id: str, plan_id: str, student_id: str, db: Session) -> dict:
    _require_enrollment(course_id, student_id, db)
    p = get_plan_repo(course_id, plan_id, student_id, db)
    from app.models.course import Course
    from app.models.user import User
    course = db.get(Course, course_id)
    student = db.get(User, student_id)
    career_direction = (student.extra or {}).get("career_direction") if student else None
    return {
        "id": p.id, "course_id": course_id, "course_name": course.name if course else "",
        "career_direction": career_direction, "status": p.status,
        "data_sources": p.data_sources, "analysis": p.analysis,
        "rag_references": [], "plan": p.plan, "created_at": p.created_at.isoformat(),
    }
