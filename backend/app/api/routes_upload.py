"""独立文件上传接口 —— 每文件一次 upload，写入 files 表并返回 file_id + 可访问 URL"""
import os
import uuid

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_db
from app.models.file import File as FileModel
from app.file_processing import extract_text
from app.services.auth_service import get_current_user

router = APIRouter(tags=["文件上传"])


def _ok(data, message="ok"):
    return {"success": True, "data": data, "message": message}


@router.post("/upload", status_code=201)
async def upload_file(
    file: UploadFile = File(...),
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """上传单个文件到文件服务器，写入 files 表，返回 file_id + file_url"""
    if not file.filename:
        raise HTTPException(status_code=400, detail="文件名不能为空")

    # 校验扩展名
    ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
    if ext not in settings.allowed_extensions:
        raise HTTPException(status_code=400, detail=f"不支持的文件格式：{ext}，支持：{', '.join(settings.allowed_extensions)}")

    # 读取内容
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="文件内容为空")
    if len(content) > settings.max_upload_bytes:
        raise HTTPException(status_code=400, detail=f"文件超过 {settings.max_upload_bytes // 1024 // 1024} MB 限制")

    # 用 UUID 生成唯一存储名
    unique_name = f"{uuid.uuid4().hex}_{file.filename}"
    save_path = os.path.join(settings.upload_dir, unique_name)

    with open(save_path, "wb") as f:
        f.write(content)

    # 提取文本
    extracted_text = extract_text(save_path)

    # 写入 files 表
    record = FileModel(
        filename=file.filename,
        file_path=save_path,
        file_size=len(content),
        extracted_text=extracted_text,
        uploaded_by=current_user.id,
    )
    db.add(record)
    db.commit()
    db.refresh(record)

    file_url = f"/files/{unique_name}"
    return _ok({
        "file_id": record.id,
        "file_url": file_url,
        "file_name": file.filename,
        "file_size": len(content),
        "extracted_text": extracted_text,
    }, "uploaded")
