"""
数据库层 —— 会话管理、初始化、向量存储、数据仓库。

结构说明：
  - session.py      数据库会话工厂与依赖注入
  - init_db.py      建表与模型注册
  - vector_store.py 向量数据库（ChromaDB / pgvector）封装
  - repositories/   数据仓库层，所有纯 SQLAlchemy 查询集中于此
"""
