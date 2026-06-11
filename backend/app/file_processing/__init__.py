"""
文件处理模块。
封装 C++ pybind11 扩展，提供文本提取、指纹计算、批量比对等功能。
"""
from app.file_processing.processor import (
    extract_text,
    preprocess,
    get_fingerprint,
    batch_compare,
)

__all__ = [
    "extract_text",
    "preprocess",
    "get_fingerprint",
    "batch_compare",
]
