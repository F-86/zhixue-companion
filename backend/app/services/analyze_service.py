"""查重与作业比对合并服务（AI + C++ 指纹预处理）—— 业务编排层"""
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.assignment import Assignment
from app.models.file import File as FileModel
from app.models.submission import Submission, SubmissionFile
from app.models.user import User
from app.db.repositories.analysis_report import get_report_by_assignment, upsert_report
from app.file_processing import get_fingerprint, batch_compare
from app.services.minimax_client import analyze_submissions as ai_analyze


def analyze(
    assignment_id: str,
    submission_ids: list[str],
    teacher_id: str,
    similarity_threshold: float,
    compare_dimensions: list[str],
    db: Session,
):
    a = db.get(Assignment, assignment_id)
    if not a or a.teacher_id != teacher_id:
        raise HTTPException(status_code=404, detail="作业不存在")

    # 收集各提交文本
    submissions_data = []
    for sub_id in submission_ids:
        sub = db.get(Submission, sub_id)
        if not sub or sub.assignment_id != assignment_id:
            continue
        text = sub.content or ""
        if not text:
            sf_records = db.query(SubmissionFile).filter(
                SubmissionFile.submission_id == sub_id,
            ).all()
            file_ids = [sf.file_id for sf in sf_records]
            file_records = db.query(FileModel).filter(FileModel.id.in_(file_ids)).all() if file_ids else []
            extracted_parts = [f.extracted_text or "" for f in file_records if f.extracted_text]
            text = "\n\n".join(extracted_parts)
        student = db.get(User, sub.student_id)
        submissions_data.append({
            "id": sub_id,
            "student_name": student.name if student else "未知",
            "student_id": sub.student_id,
            "text": text,
        })

    if len(submissions_data) < 2:
        raise HTTPException(status_code=400, detail="至少需要 2 份提交才能进行分析")

    texts = [s["text"] for s in submissions_data]

    # C++ pybind11：文本预处理 + 指纹粗筛
    fingerprint_data = {}
    for i, s in enumerate(submissions_data):
        fp = get_fingerprint(s["text"])
        fingerprint_data[s["id"]] = fp

    suspect_pairs = batch_compare(texts, threshold=similarity_threshold)

    # MiniMax：语义分析 + 比对
    ai_result = ai_analyze(submissions_data, suspect_pairs, compare_dimensions)

    # 补充提交 ID 到 suspicious_pairs
    name_to_sub = {s["student_name"]: s["id"] for s in submissions_data}
    for pair in ai_result.get("suspicious_pairs", []):
        if "submission_a" not in pair:
            pair["submission_a"] = name_to_sub.get(pair.get("student_a", ""), "")
        if "submission_b" not in pair:
            pair["submission_b"] = name_to_sub.get(pair.get("student_b", ""), "")

    for detail in ai_result.get("comparison_details", []):
        if "submission_id" not in detail:
            detail["submission_id"] = name_to_sub.get(detail.get("student_name", ""), "")

    return upsert_report(assignment_id, ai_result, fingerprint_data, db)


def get_report(assignment_id: str, teacher_id: str, db: Session):
    a = db.get(Assignment, assignment_id)
    if not a or a.teacher_id != teacher_id:
        raise HTTPException(status_code=404, detail="作业不存在")
    report = get_report_by_assignment(assignment_id, db)
    if not report:
        raise HTTPException(status_code=404, detail="尚未执行分析，请先触发查重与比对")
    return report
