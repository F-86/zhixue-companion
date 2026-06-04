from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/ 目录的绝对路径，作为所有相对路径的锚点
# 无论从哪个工作目录启动服务，数据库和文件路径始终落在 backend/ 下
_BACKEND_DIR = Path(__file__).resolve().parent.parent.parent


class Settings(BaseSettings):
    # MiniMax 大模型
    minimax_api_key: str = ""
    minimax_group_id: str = ""
    minimax_model: str = "abab6.5s-chat"
    # MiniMax Embedding 模型，用于向量检索
    minimax_embedding_model: str = "embo-01"

    # JWT 鉴权
    secret_key: str = "change_this_to_a_long_random_string"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 1440  # 24 小时

    # 关系数据库
    # 默认使用 SQLite（嵌入式）；填写 PostgreSQL 连接串后自动切换，例如：
    #   postgresql+psycopg2://user:password@host:5432/dbname
    database_url: str = f"sqlite:///{_BACKEND_DIR / 'zhixue.db'}"

    # 向量数据库
    # 默认使用 ChromaDB（嵌入式，持久化到本地目录）；
    # 填写 PostgreSQL 连接串后自动切换到 pgvector，使用同一个 PG 实例：
    #   postgresql+psycopg2://user:password@host:5432/dbname
    vector_db_url: str = ""
    # ChromaDB 本地持久化目录（仅 vector_db_url 为空时生效）
    chroma_dir: str = str(_BACKEND_DIR / "chroma_db")

    # 文件存储（绝对路径）
    upload_dir: str = str(_BACKEND_DIR / "uploads")
    log_dir: str = str(_BACKEND_DIR / "logs")

    # 文件上传限制
    max_upload_bytes: int = 10 * 1024 * 1024  # 10 MB
    allowed_extensions: list[str] = ["pdf", "txt", "doc", "docx"]

    model_config = SettingsConfigDict(
        env_file=str(_BACKEND_DIR / ".env"),
        extra="ignore",
    )


settings = Settings()
