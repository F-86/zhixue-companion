from fastapi import APIRouter, Depends, Form
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.services import student_assignment_service as svc
from app.services.auth_service import require_student

router = APIRouter(tags=["学生端作业"])


def _ok(data, message="ok"):
    return {"success": True, "data": data, "message": message}


@router.get("/student/assignments")
def list_assignments(
    course: str | None = None,
    status: str | None = None,
    current_user=Depends(require_student),
    db: Session = Depends(get_db),
):
    result = svc.list_assignments(current_user.id, course, status, db)
    return _ok(result)


@router.get("/student/assignments/{assignment_id}")
def get_assignment(assignment_id: str, current_user=Depends(require_student), db: Session = Depends(get_db)):
    result = svc.get_assignment_detail(assignment_id, current_user.id, db)
    return _ok(result)


@router.post("/student/assignments/{assignment_id}/submit", status_code=201)
async def submit_assignment(
    assignment_id: str,
    submit_type: str = Form(...),
    content: str | None = Form(None),
    file_ids: str | None = Form(None),
    current_user=Depends(require_student),
    db: Session = Depends(get_db),
):
    """
    提交作业。文本提交时传 content；文件提交时传 file_ids（多个 ID 以逗号分隔）。
    file_ids 中的每个 ID 应来自 /api/upload 接口返回的 file_id。
    """
    if submit_type == "text":
        if not content:
            from fastapi import HTTPException
            raise HTTPException(status_code=400, detail="文本提交时 content 不能为空")
        sub = svc.submit_text(assignment_id, current_user.id, content, db)
    else:
        if not file_ids:
            from fastapi import HTTPException
            raise HTTPException(status_code=400, detail="文件提交时 file_ids 不能为空")
        ids = [fid.strip() for fid in file_ids.split(",") if fid.strip()]
        if not ids:
            from fastapi import HTTPException
            raise HTTPException(status_code=400, detail="file_ids 格式不合法")
        sub = svc.submit_file(assignment_id, current_user.id, ids, db)

    return _ok({
        "id": sub.id,
        "assignment_id": sub.assignment_id,
        "student_id": sub.student_id,
        "submit_type": sub.submit_type,
        "submitted_at": sub.submitted_at,
        "status": sub.status,
    }, "submitted")


@router.get("/student/assignments/{assignment_id}/my-submission")
def my_submission(assignment_id: str, current_user=Depends(require_student), db: Session = Depends(get_db)):
    return _ok(svc.get_my_submission(assignment_id, current_user.id, db))
