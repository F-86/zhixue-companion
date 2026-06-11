from fastapi import APIRouter, Depends, Form
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.services import student_assignment_service as svc
from app.services.auth_service import require_student

router = APIRouter(tags=["学生端作业"])


def _ok(data, message="ok"):
    return {"success": True, "data": data, "message": message}


@router.get("/student/courses/{course_id}/assignments")
def list_assignments(
    course_id: str,
    course: str | None = None,
    status: str | None = None,
    current_user=Depends(require_student),
    db: Session = Depends(get_db),
):
    result = svc.list_assignments(course_id, current_user.id, course, status, db)
    return _ok(result)


@router.get("/student/courses/{course_id}/assignments/{assignment_id}")
def get_assignment(
    course_id: str,
    assignment_id: str,
    current_user=Depends(require_student),
    db: Session = Depends(get_db),
):
    result = svc.get_assignment_detail(assignment_id, current_user.id, db)
    return _ok(result)


@router.post("/student/courses/{course_id}/assignments/{assignment_id}/submit", status_code=201)
async def submit_assignment(
    course_id: str,
    assignment_id: str,
    submit_type: str = Form(...),
    content: str | None = Form(None),
    file_ids: str | None = Form(None),
    current_user=Depends(require_student),
    db: Session = Depends(get_db),
):
    """
    提交作业。文本提交时传 content；文件提交时传 file_ids（多个 ID 以逗号分隔）。
    可同时传 content 和 file_ids，两者都会被记录。
    file_ids 中的每个 ID 应来自 /api/upload 接口返回的 file_id。
    """
    has_content = bool(content)
    has_files = bool(file_ids)

    if not has_content and not has_files:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail="content 和 file_ids 至少提供一个")

    if has_files:
        ids = [fid.strip() for fid in file_ids.split(",") if fid.strip()]
        if not ids:
            from fastapi import HTTPException
            raise HTTPException(status_code=400, detail="file_ids 格式不合法")
        sub = svc.submit_file(assignment_id, current_user.id, ids, db, content)
    else:
        sub = svc.submit_text(assignment_id, current_user.id, content, db)

    return _ok({
        "id": sub.id,
        "assignment_id": sub.assignment_id,
        "student_id": sub.student_id,
        "submit_type": sub.submit_type,
        "submitted_at": sub.submitted_at,
        "status": sub.status,
    }, "submitted")


@router.get("/student/courses/{course_id}/assignments/{assignment_id}/my-submission")
def my_submission(
    course_id: str,
    assignment_id: str,
    current_user=Depends(require_student),
    db: Session = Depends(get_db),
):
    return _ok(svc.get_my_submission(assignment_id, current_user.id, db))
