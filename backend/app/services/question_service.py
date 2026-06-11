"""提问服务 —— 从 db.repositories.question 重导出"""
from app.db.repositories.question import (
    create_question,
    list_questions,
    get_question,
    answer_question,
    update_visibility,
    delete_question,
)
