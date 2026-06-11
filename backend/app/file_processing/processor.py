"""
C++ pybind11 扩展封装层。
业务代码通过本模块调用 file_processor，不直接 import file_processor。
若 C++ 扩展尚未编译，所有函数返回安全的降级结果，不阻断主流程。
"""
import logging

from app.core.config import settings

logger = logging.getLogger(__name__)

# 尝试导入编译好的 pybind11 扩展
try:
    import file_processor as _fp
    _AVAILABLE = True
    logger.info("file_processor 扩展加载成功")
except ImportError:
    _AVAILABLE = False
    logger.warning("file_processor 扩展未找到，文件处理功能将降级（仅支持文本提交）")


def extract_text(file_path: str) -> str | None:
    """
    从上传文件中提取纯文本。
    支持 .txt / .pdf；失败时返回 None 并写入日志。
    """
    if not _AVAILABLE:
        logger.warning("extract_text: 扩展不可用，跳过文件提取")
        return None
    try:
        return _fp.extract_text(file_path)
    except (ValueError, RuntimeError) as e:
        logger.error("extract_text 失败 [%s]: %s", file_path, e)
        _write_log("ERROR", f"extract_text: {e}")
        return None


def preprocess(text: str) -> list[str]:
    """对文本进行去噪和分段，返回段落列表。失败时返回空列表。"""
    if not _AVAILABLE or not text:
        return []
    try:
        return _fp.preprocess_segments(text)
    except ValueError as e:
        logger.warning("preprocess_segments 失败: %s", e)
        return []


def get_fingerprint(text: str, window_size: int = 5) -> list[int]:
    """计算文本指纹（滑动窗口哈希）。失败时返回空列表。"""
    if not _AVAILABLE or not text:
        return []
    try:
        return _fp.compute_fingerprint(text, window_size=window_size)
    except ValueError as e:
        logger.warning("compute_fingerprint 失败: %s", e)
        return []


def batch_compare(texts: list[str], threshold: float = 0.8) -> list[tuple[int, int, float]]:
    """
    对多份文本进行指纹相似度粗筛。
    返回相似度超过 threshold 的 (i, j, similarity) 三元组列表。
    扩展不可用时返回全量两两组合（让 MiniMax 全量分析），失败时返回空列表。
    """
    if not _AVAILABLE:
        # 降级：返回所有两两组合，由 MiniMax 全量判断
        result = []
        for i in range(len(texts)):
            for j in range(i + 1, len(texts)):
                result.append((i, j, 1.0))
        return result
    try:
        return _fp.batch_compare(texts, threshold=threshold)
    except (ValueError, RuntimeError) as e:
        logger.error("batch_compare 失败: %s", e)
        return []


def _write_log(level: str, message: str) -> None:
    """向 C++ 日志文件写入一条记录"""
    if not _AVAILABLE:
        return
    import os
    log_path = os.path.join(settings.log_dir, "file_processor.log")
    try:
        _fp.write_log(log_path, level, message)
    except Exception as e:
        logger.error("write_log 失败: %s", e)
