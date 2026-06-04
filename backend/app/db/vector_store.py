"""
向量数据库封装层。

对外只暴露以下函数：
  - upsert_chunks(chunks)              写入/更新向量
  - query_chunks(query_vec, course_id, top_k)   两阶段 Rerank 检索
  - delete_chunks_by_section(section_id)        按小节删除所有块

后端根据配置自动选择实现：
  - vector_db_url 为空 → ChromaDB（嵌入式，本地持久化）
  - vector_db_url 填写 PostgreSQL 连接串 → pgvector（同 PG 实例）

切换数据库只需改配置，调用方代码无需修改。

Chunk 数据结构：
  {
    "id":          str,   # 唯一标识，建议格式 "{section_id}#{chunk_index}"
    "section_id":  str,
    "section_title": str,
    "course_id":   str,
    "file_name":   str,
    "text":        str,   # 原始文本片段
    "embedding":   list[float],  # 向量，由调用方传入
  }

检索策略（两阶段 Rerank）：
  1. 初召回：向量库召回 max(top_k * 4, 10) 个候选块（粗筛）
  2. 精排：在 Python 侧用余弦相似度对候选块重新打分，取最高 top_k 个
  这样可以过滤向量库近似索引引入的误差，提升最终送给 LLM 的片段质量。
"""
import logging
import math
import os
from typing import Any

from app.core.config import settings

logger = logging.getLogger(__name__)

# ── ChromaDB 实现 ──────────────────────────────────────────────

_chroma_client: Any = None
_chroma_collection: Any = None


def _get_chroma_collection():
    global _chroma_client, _chroma_collection
    if _chroma_collection is not None:
        return _chroma_collection
    import chromadb
    os.makedirs(settings.chroma_dir, exist_ok=True)
    _chroma_client = chromadb.PersistentClient(path=settings.chroma_dir)
    # 使用预计算向量，指定 embedding_function=None
    _chroma_collection = _chroma_client.get_or_create_collection(
        name="course_materials",
        metadata={"hnsw:space": "cosine"},
    )
    logger.info("ChromaDB 已初始化，持久化目录: %s", settings.chroma_dir)
    return _chroma_collection


def _chroma_upsert(chunks: list[dict]) -> None:
    col = _get_chroma_collection()
    col.upsert(
        ids=[c["id"] for c in chunks],
        embeddings=[c["embedding"] for c in chunks],
        metadatas=[{
            "section_id":    c["section_id"],
            "section_title": c["section_title"],
            "course_id":     c["course_id"],
            "file_name":     c["file_name"],
            "text":          c["text"][:500],  # Chroma metadata 限 500 字
        } for c in chunks],
    )


def _chroma_query(query_embedding: list[float], course_id: str, top_k: int) -> list[dict]:
    col = _get_chroma_collection()
    results = col.query(
        query_embeddings=[query_embedding],
        n_results=top_k,
        where={"course_id": course_id},
        include=["metadatas", "distances", "embeddings"],
    )
    refs = []
    metadatas = results["metadatas"][0]
    distances = results["distances"][0]
    embeddings = results.get("embeddings") or [[None] * top_k]
    embeddings = embeddings[0] if embeddings else [None] * len(metadatas)
    for meta, distance, emb in zip(metadatas, distances, embeddings):
        item = {
            "section_id":    meta["section_id"],
            "section_title": meta["section_title"],
            "file_name":     meta["file_name"],
            "excerpt":       meta["text"],
            "score":         round(1 - distance, 4),  # 余弦距离转相似度
        }
        if emb is not None:
            item["_embedding"] = emb  # 供精排使用，最终会被移除
        refs.append(item)
    return refs


def _chroma_delete_by_section(section_id: str) -> None:
    col = _get_chroma_collection()
    col.delete(where={"section_id": section_id})


# ── pgvector 实现 ──────────────────────────────────────────────

def _pg_upsert(chunks: list[dict]) -> None:
    """将 chunks 写入 pgvector 表 course_material_chunks。"""
    from sqlalchemy import text
    from app.db.session import engine
    with engine.connect() as conn:
        for c in chunks:
            conn.execute(text("""
                INSERT INTO course_material_chunks
                    (id, section_id, section_title, course_id, file_name, text, embedding)
                VALUES
                    (:id, :section_id, :section_title, :course_id, :file_name, :text, :embedding)
                ON CONFLICT (id) DO UPDATE SET
                    section_id    = EXCLUDED.section_id,
                    section_title = EXCLUDED.section_title,
                    course_id     = EXCLUDED.course_id,
                    file_name     = EXCLUDED.file_name,
                    text          = EXCLUDED.text,
                    embedding     = EXCLUDED.embedding
            """), {
                "id":            c["id"],
                "section_id":    c["section_id"],
                "section_title": c["section_title"],
                "course_id":     c["course_id"],
                "file_name":     c["file_name"],
                "text":          c["text"],
                "embedding":     str(c["embedding"]),  # pgvector 接受字符串格式
            })
        conn.commit()


def _pg_query(query_embedding: list[float], course_id: str, top_k: int) -> list[dict]:
    """使用 pgvector 余弦相似度检索，同时返回向量供精排。"""
    from sqlalchemy import text
    from app.db.session import engine
    vec_str = str(query_embedding)
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT section_id, section_title, file_name, text, embedding::text,
                   1 - (embedding <=> :vec) AS score
            FROM course_material_chunks
            WHERE course_id = :course_id
            ORDER BY embedding <=> :vec
            LIMIT :top_k
        """), {"vec": vec_str, "course_id": course_id, "top_k": top_k}).fetchall()
    result = []
    for row in rows:
        item = {
            "section_id":    row.section_id,
            "section_title": row.section_title,
            "file_name":     row.file_name,
            "excerpt":       row.text,
            "score":         round(row.score, 4),
        }
        # 将 pgvector 文本格式的向量解析回列表，供精排使用
        try:
            emb_str = row.embedding.strip("[]")
            item["_embedding"] = [float(x) for x in emb_str.split(",")]
        except Exception:
            pass
        result.append(item)
    return result


def _pg_delete_by_section(section_id: str) -> None:
    from sqlalchemy import text
    from app.db.session import engine
    with engine.connect() as conn:
        conn.execute(text("DELETE FROM course_material_chunks WHERE section_id = :sid"),
                     {"sid": section_id})
        conn.commit()


def _pg_init_table() -> None:
    """建表（pgvector 维度固定为 1536，与 MiniMax embo-01 对齐）。"""
    from sqlalchemy import text
    from app.db.session import engine
    with engine.connect() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS course_material_chunks (
                id            TEXT PRIMARY KEY,
                section_id    TEXT NOT NULL,
                section_title TEXT NOT NULL,
                course_id     TEXT NOT NULL,
                file_name     TEXT NOT NULL,
                text          TEXT NOT NULL,
                embedding     vector(1536) NOT NULL
            )
        """))
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_chunks_course_id
            ON course_material_chunks (course_id)
        """))
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_chunks_embedding
            ON course_material_chunks
            USING ivfflat (embedding vector_cosine_ops)
        """))
        conn.commit()
    logger.info("pgvector 表 course_material_chunks 已就绪")


# ── Rerank 工具 ────────────────────────────────────────────────

def _cosine_similarity(a: list[float], b: list[float]) -> float:
    """计算两个向量的余弦相似度。"""
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def _rerank(
    candidates: list[dict],
    query_embedding: list[float],
    top_k: int,
) -> list[dict]:
    """
    两阶段 Rerank 精排：
    对候选块重新计算与查询向量的精确余弦相似度，
    按相似度降序排列，取前 top_k 个返回。
    候选块需包含 "_embedding" 字段（原始向量），精排后该字段会被移除。
    """
    for c in candidates:
        emb = c.get("_embedding")
        if emb:
            c["score"] = round(_cosine_similarity(query_embedding, emb), 4)
    candidates.sort(key=lambda x: x.get("score", 0), reverse=True)
    result = candidates[:top_k]
    # 移除内部用的向量字段，不暴露给上层
    for c in result:
        c.pop("_embedding", None)
    return result


# ── 路由：根据配置选择后端 ────────────────────────────────────

def _use_pg() -> bool:
    """判断是否使用 pgvector（vector_db_url 填写了 PG 连接串）。"""
    url = settings.vector_db_url.strip()
    return bool(url) and url.startswith("postgresql")


def init_vector_store() -> None:
    """应用启动时调用，初始化向量数据库。"""
    if _use_pg():
        _pg_init_table()
    else:
        _get_chroma_collection()  # 触发 ChromaDB 初始化


def upsert_chunks(chunks: list[dict]) -> None:
    """
    写入/更新向量片段。chunks 中每项必须包含 embedding 字段。
    已存在相同 id 的记录会被覆盖。
    """
    if not chunks:
        return
    if _use_pg():
        _pg_upsert(chunks)
    else:
        _chroma_upsert(chunks)


def query_chunks(query_embedding: list[float], course_id: str, top_k: int = 3) -> list[dict]:
    """
    两阶段检索：
    1. 初召回：向量库召回 recall_k 个候选（recall_k = max(top_k * 4, 10)）
    2. 精排（Rerank）：在 Python 侧重新计算精确余弦相似度，取 top_k 个
    返回列表，每项包含：section_id, section_title, file_name, excerpt, score。
    score 为余弦相似度，值域 [0, 1]，越大越相关。
    """
    recall_k = max(top_k * 4, 10)
    if _use_pg():
        candidates = _pg_query(query_embedding, course_id, recall_k)
    else:
        candidates = _chroma_query(query_embedding, course_id, recall_k)
    # 精排：重新排序取最优 top_k
    return _rerank(candidates, query_embedding, top_k)


def delete_chunks_by_section(section_id: str) -> None:
    """删除某个小节的所有向量片段，在小节被删除时调用。"""
    if _use_pg():
        _pg_delete_by_section(section_id)
    else:
        _chroma_delete_by_section(section_id)
