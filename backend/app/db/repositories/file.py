"""数据库操作层 —— 文件查询"""
from sqlalchemy.orm import Session

from app.models.file import File as FileModel


def get_file(file_id: str, db: Session) -> FileModel | None:
    return db.get(FileModel, file_id)


def create_file_record(filename: str, file_path: str, file_size: int,
                        extracted_text: str | None, uploaded_by: str, db: Session) -> FileModel:
    record = FileModel(
        filename=filename,
        file_path=file_path,
        file_size=file_size,
        extracted_text=extracted_text,
        uploaded_by=uploaded_by,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record
