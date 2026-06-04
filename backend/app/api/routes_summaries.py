"""知识点总结路由（课程路径版）"""
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.services import summary_service as svc
from app.services.auth_service import require_student

router = APIRouter(tags=["知识点总结"])


def _ok(data, message="ok"):
    return {"success": True, "data": data, "message": message}


class SummaryCreateRequest(BaseModel):
    title: str
    section_id: str | None = None
    source_text: str | None = None
    summary_type: str = "structured"


@router.post("/student/courses/{course_id}/summaries", status_code=201)
def create_summary(course_id: str, req: SummaryCreateRequest,
                    current_user=Depends(require_student), db: Session = Depends(get_db)):
    return _ok(svc.create_summary(
        course_id, current_user.id, req.title,
        req.section_id, req.source_text, req.summary_type, db,
    ), "created")


@router.get("/student/courses/{course_id}/summaries")
def list_summaries(course_id: str, section_id: str | None = None, keyword: str | None = None,
                    current_user=Depends(require_student), db: Session = Depends(get_db)):
    return _ok(svc.list_summaries(course_id, current_user.id, section_id, keyword, db))


@router.get("/student/courses/{course_id}/summaries/{summary_id}")
def get_summary(course_id: str, summary_id: str,
                 current_user=Depends(require_student), db: Session = Depends(get_db)):
    return _ok(svc.get_summary(course_id, summary_id, current_user.id, db))


@router.delete("/student/courses/{course_id}/summaries/{summary_id}")
def delete_summary(course_id: str, summary_id: str,
                    current_user=Depends(require_student), db: Session = Depends(get_db)):
    svc.delete_summary(course_id, summary_id, current_user.id, db)
    return _ok({"id": summary_id}, "deleted")
