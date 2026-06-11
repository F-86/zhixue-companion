"""
文件处理客户端 —— 已迁移至 app.file_processing，此处保留向后兼容重导出。
"""
from app.file_processing import (
    extract_text,
    preprocess,
    get_fingerprint,
    batch_compare,
)
