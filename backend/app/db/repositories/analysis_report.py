"""数据库操作层 —— 分析报告查询"""
from sqlalchemy.orm import Session

from app.models.analysis_report import AnalysisReport


def get_report_by_assignment(assignment_id: str, db: Session) -> AnalysisReport | None:
    return (
        db.query(AnalysisReport)
        .filter(AnalysisReport.assignment_id == assignment_id)
        .first()
    )


def upsert_report(assignment_id: str, ai_result: dict, fingerprint_data: dict, db: Session) -> AnalysisReport:
    existing = db.query(AnalysisReport).filter(AnalysisReport.assignment_id == assignment_id).first()
    if existing:
        existing.suspicious_pairs = ai_result.get("suspicious_pairs", [])
        existing.comparison_details = ai_result.get("comparison_details", [])
        existing.common_issues = ai_result.get("common_issues", [])
        existing.teaching_suggestions = ai_result.get("teaching_suggestions", [])
        existing.fingerprint_data = fingerprint_data
        db.commit()
        db.refresh(existing)
        return existing
    report = AnalysisReport(
        assignment_id=assignment_id,
        suspicious_pairs=ai_result.get("suspicious_pairs", []),
        comparison_details=ai_result.get("comparison_details", []),
        common_issues=ai_result.get("common_issues", []),
        teaching_suggestions=ai_result.get("teaching_suggestions", []),
        fingerprint_data=fingerprint_data,
    )
    db.add(report)
    db.commit()
    db.refresh(report)
    return report
