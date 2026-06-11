"""认证服务 —— 从 db.repositories.user 重导出"""
from app.db.repositories.user import (
    register_student,
    register_teacher,
    login,
    get_current_user,
    require_student,
    require_teacher,
)
