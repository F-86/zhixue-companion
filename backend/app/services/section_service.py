"""课程小节服务 —— 从 db.repositories.section 重导出"""
from app.db.repositories.section import (
    create_section,
    list_teacher_sections,
    update_section,
    delete_section,
    list_student_sections,
    get_student_section,
    # 内部工具函数（测试依赖）
    _CHUNK_SIZE,
    _char_split,
    split_text as _split_text,
    text_hash as _text_hash,
)
