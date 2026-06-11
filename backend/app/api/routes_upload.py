"""独立文件上传接口 —— 每文件一次 upload，返回可访问路径"""
import os
import uuid

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from app.core.config import settings
from app.services import file_processor_client
from app.services.auth_service import get_current_user

router = APIRouter(tags=["文件上传"])


def _ok(data, message="ok"):
    return {"success": True, "data": data, "message": message}


@router.post("/upload", status_code=201)
async def upload_file(
    file: UploadFile = File(...),
    current_user=Depends(get_current_user),
):
    """上传单个文件到文件服务器，返回后续可访问的 file_url"""
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

    # 用 UUID 生成唯一存储名，保留原始扩展名
    unique_name = f"{uuid.uuid4().hex}_{file.filename}"
    save_path = os.path.join(settings.upload_dir, unique_name)

    with open(save_path, "wb") as f:
        f.write(content)

    # 提取文本
    extracted_text = file_processor_client.extract_text(save_path)

    file_url = f"/files/{unique_name}"
    return _ok({
        "file_url": file_url,
        "file_name": file.filename,
        "file_size": len(content),
        "extracted_text": extracted_text,
    }, "uploaded")
