# 智学伴侣 · 数据库层设计

本文档描述后端数据库层的完整架构：会话管理、数据仓库模式、向量存储和初始化流程。

---

## 1. 架构概览

```
app/db/
├── __init__.py          # 模块说明
├── session.py            # SQLAlchemy 引擎与会话管理
├── init_db.py            # 建表入口
├── vector_store.py       # 向量数据库双后端封装（ChromaDB / pgvector）
└── repositories/         # 数据仓库层（18 个模块）
    ├── __init__.py
    ├── user.py           # 用户注册 / 登录 / JWT 鉴权依赖
    ├── course.py         # 课程 CRUD、权限校验、成绩计算
    ├── announcement.py   # 公告 CRUD（教师 + 学生端）
    ├── assignment.py     # 作业 CRUD（教师 + 学生端）
    ├── submission.py     # 作业提交 / 查询
    ├── discussion.py     # 讨论 CRUD + 回复
    ├── question.py       # 提问 CRUD + 回答
    ├── section.py        # 小节 CRUD、文本分块、向量索引
    ├── quiz.py           # 测试 CRUD、作答提交、自动批改
    ├── score.py          # 成绩查询、分布统计、排名
    ├── grade.py          # AI 批改结果读写、确认
    ├── chat.py           # 聊天消息持久化、会话列表
    ├── learning_plan.py  # 学习计划 CRUD、版本管理
    ├── plan_progress.py  # 计划进度打卡、查询
    ├── summary.py        # 知识点总结 CRUD
    ├── file.py           # 上传文件记录查询
    └── analysis_report.py # 查重分析报告读写
```

---

## 2. 数据仓库（Repository）模式

### 2.1 设计动机

原始代码中，服务层函数混合了三种职责：

```
    路由层 ─→ 服务函数 ─→ SQLAlchemy Session（业务逻辑 + 数据库查询掺在一起）
```

重构后，所有纯数据库操作（SQLAlchemy 查询、插入、更新、删除）集中在 `db/repositories/`，服务层仅保留需要跨模块协调或调用外部 API 的业务逻辑。

```
    路由层 ─→ 服务层（业务编排）
                  ├──→ db/repositories（纯数据库操作）
                  ├──→ minimax_client（AI 调用）
                  └──→ file_processing（C++ 文件处理）
```

### 2.2 仓库函数约定

所有仓库函数遵循以下约定：

| 规则 | 说明 | 示例 |
|------|------|------|
| **第一个参数是业务 ID** | 如 `course_id`、`assignment_id`，便于阅读调用意图 | `create_course(teacher_id, name, desc, db)` |
| **最后一个参数是 Session** | `db: Session` 总是最后一个位置参数 | `require_enrollment(course_id, student_id, db)` |
| **路由鉴权由路由层处理** | 仓库不调用 `get_current_user`，角色/用户对象由调用方传入 | `list_teacher_quizzes(course_id, teacher_id, ...)` |
| **权限校验内聚** | 每个模块有自己的 `require_*` 函数，内部抛 `HTTPException` | `require_enrollment`、`require_quiz`、`require_plan` |
| **无副作用** | 不打印、不调用外部 API、不操作文件系统 | — |

### 2.3 权限校验函数族

| 函数 | 所在模块 | 校验内容 | 失败响应 |
|------|---------|---------|---------|
| `require_teacher_course` | `course.py` | 课程属于该教师 | 404 |
| `require_enrollment` | `course.py` | 学生已加入课程 | 403 |
| `require_section` | `section.py` | 小节属于该课程 | 404 |
| `require_assignment` | `assignment.py` | 作业属于该课程 | 404 |
| `require_quiz` | `quiz.py` | 测试属于该课程 | 404 |
| `require_attempt` | `quiz.py` | 作答记录属于该学生 | 404 |
| `require_announcement` | `announcement.py` | 公告属于该课程 | 404 |
| `require_discussion` | `discussion.py` | 讨论属于该课程 | 404 |
| `require_question` | `question.py` | 提问属于该课程 | 404 |
| `require_plan` | `learning_plan.py` | 计划属于该学生和课程 | 404 |
| `require_summary` | `summary.py` | 总结属于该学生和课程 | 404 |

**设计意图**：教师操作他人课程返回 404（不告知存在），防止枚举攻击；学生未加入课程返回 403。

### 2.4 责任边界

```
仓库层做：
  ✅ 所有 SQLAlchemy Session 操作
  ✅ 权限校验（require_*）
  ✅ 简单的字段转换（如生成 URL）

仓库层不做：
  ❌ 调用 MiniMax / 外部 API
  ❌ 调用 C++ 文件处理
  ❌ 文件 I/O
  ❌ 复杂的多步骤业务编排
```

---

## 3. 会话管理

### 3.1 引擎与 Session 工厂

```python
# app/db/session.py
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

engine = create_engine(
    settings.database_url,
    connect_args={"check_same_thread": False},  # SQLite 多线程支持
    pool_pre_ping=True,                          # 连接健康检查
)

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)
```

**关键参数**：

| 参数 | 值 | 说明 |
|------|-----|------|
| `check_same_thread` | `False` | SQLite 默认只允许单线程，设为 False 才支持 FastAPI 并发 |
| `pool_pre_ping` | `True` | 每次从连接池取出连接前先 ping，检测断连 |
| `autocommit` | `False` | 由调用方显式控制事务边界 |
| `autoflush` | `False` | 避免意外的隐式 flush，由调用方按需控制 |

### 3.2 依赖注入

```python
# 请求级 Session：FastAPI 路由通过 Depends 注入
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()  # 请求结束后自动关闭
```

路由中使用：

```python
@router.get("/courses")
def list_courses(db: Session = Depends(get_db)):
    ...
```

### 3.3 独立 Session（后台任务）

某些场景需要脱离请求生命周期使用 Session，如 FastAPI 的 `BackgroundTasks` 异步写入：

```python
# chat_service.py
def save_messages(session_id: str, ctx: dict) -> None:
    db = SessionLocal()          # 独立 session
    try:
        db.add(ChatMessage(...))
        db.commit()
    except Exception:
        db.rollback()
    finally:
        db.close()
```

**原因**：请求的 Session 在响应发出后会被 FastAPI 关闭，后台任务若复用会报 `Session is closed` 错误。

---

## 4. 建表流程

### 4.1 init_db()

```python
# app/db/init_db.py
from app.db.session import engine, Base

def init_db():
    """创建所有 ORM 模型对应的表（不重复创建已存在的表）"""
    import app.models  # 确保所有 ORM 模型被注册到 Base.metadata
    Base.metadata.create_all(bind=engine)
```

**调用时机**：FastAPI 的 `lifespan` 事件中，应用启动时执行一次。

**Schema 迁移策略**：当前版本使用 `create_all`，适合开发阶段。生产环境建议引入 Alembic 做迁移版本管理。

### 4.2 模型注册

`app/models/__init__.py` 为空文件，通过 `import app.models` 触发所有模型模块的加载，注册到 `Base.metadata`：

```
app/models/
├── user.py
├── course.py
├── section.py
├── assignment.py
├── submission.py
├── grade.py
├── analysis_report.py
├── quiz.py
├── chat.py
├── summary.py
├── learning_plan.py
├── plan_progress.py
├── announcement.py
├── discussion.py
├── question.py
└── file.py
```

---

## 5. 向量存储

### 5.1 双后端设计

```
VECTOR_DB_URL 未设置（默认）
  └── ChromaDB 嵌入式
      ├── 持久化路径：backend/chroma_db/
      ├── 零额外依赖，开箱即用
      └── 通过 chromadb 库的 PersistentClient 操作

VECTOR_DB_URL = postgresql+psycopg2://...
  └── pgvector
      ├── 与关系数据库共用同一 PostgreSQL 实例
      ├── 表名：course_material_chunks（自动创建）
      └── 通过 SQLAlchemy raw connection 操作
```

切换只需要改 `.env` 中一个变量，业务代码零修改。

### 5.2 公开接口

| 函数 | 用途 | 说明 |
|------|------|------|
| `init_vector_store()` | 初始化向量库 | ChromaDB 获取/创建 collection；pgvector 建表 |
| `upsert_chunks(chunks)` | 批量写入向量块 | 每条 chunk 包含 `id`, `embedding`, `text`, `section_id`, `section_title`, `course_id`, `file_name` |
| `query_chunks(query_embedding, course_id, top_k)` | 检索相关块 | 粗筛（向量库）→ 精排（Python 余弦相似度 Rerank） |
| `delete_chunks_by_section(section_id)` | 按小节删除 | 课件更新时先删旧块再写入新块 |

### 5.3 Rerank 流程

向量库通常使用近似最近邻算法（ANN），可能存在精度误差。`query_chunks` 采用两阶段策略：

```
阶段一：粗筛
  └── 向量库召回 max(top_k × 4, 10) 个候选块

阶段二：精排
  └── Python 侧对每个候选块重新计算精确余弦相似度
  └── 降序排列，取 Top-K
  └── 从结果中移除 embedding 字段（减小响应体积）
```

### 5.4 分块策略

材料入库时，`_split_text()` 对文本做分段：

```
优先级 1：按 Markdown 标题行（# 开头）切分
    ↓
优先级 2：按连续空行（\n\n）切分
    ↓
兜底策略：超长段落（> 500 字）降级为字符分块
    └── 相邻块保留 50 字重叠，避免语义断裂
```

### 5.5 增量更新

每次更新小节材料时，先计算新文本的 SHA-256 hash：

```
material_hash 已存储 && 相同
  └── 跳过向量化，不调用 Embedding API

material_hash 不同或为空
  └── 删除旧向量块 → 重新分块 → 批量向量化 → 写入新块 → 更新 hash
```

---

## 6. 主键策略

所有表使用 `str(uuid.uuid4())` 作为主键，应用层生成（非数据库自增）。

| 优点 | 说明 |
|------|------|
| 数据库无关 | SQLite 和 PostgreSQL 行为一致 |
| 预知 ID | 可在创建对象前确定 ID，无需 flush/refresh |
| 水平拆分友好 | 无全局自增冲突 |

**字段类型**：`String` 而非 `UUID`，兼容 SQLite（SQLite 无原生 UUID 类型）。

---

## 7. 时区约定

所有 `DateTime` 字段均声明 `timezone=True`，自动存储 UTC 时间。

```python
def _now() -> datetime:
    return datetime.now(timezone.utc)
```

前端展示时再转换为本地时间。后端所有时间比较均基于 UTC。

---

## 8. 数据一致性策略

| 场景 | 策略 | 实现位置 |
|------|------|---------|
| 软外键 | 不设数据库级外键约束，由 `require_*` 函数保证 | `repositories/*.py` |
| 级联删除 | 删小节时显式删关联作业和向量块 | `section.py` / `vector_store.py` |
| 冗余字段 | `assignment.course` 写入时由服务层保证一致 | `assignment.py` |
| 向量库同步 | `delete_chunks_by_section` 与关系库同步删除 | `section.py` → `vector_store.py` |
| 批改双分 | `confirmed=False` 为建议，`confirmed=True` 才计入成绩 | `grade.py` |

### 8.1 为什么不使用数据库外键？

1. **SQLite 兼容性**：SQLite 默认不强制外键约束（需要 `PRAGMA foreign_keys = ON`）
2. **错误提示**：应用层校验可以返回更友好的中文错误信息（404/403），而非数据库层报错
3. **测试便利**：测试中可以自由插入数据，不依赖外键依赖链

### 8.2 冗余字段设计

`assignments.course` 和 `learning_plans.course` 冗余存储课程名称：

| 利 | 弊 |
|----|-----|
| 列表查询免 JOIN，减少 SQL 复杂度 | 课程改名时需同步更新关联表 |
| SQLite 的 JOIN 性能有限，冗余可加速 | 存在数据不一致风险 |

**缓解措施**：课程名称不可修改（设计中），如需改名通过 `archive_course` + 新建课程实现。

---

## 9. 与上层的关系

```
┌──────────────────────────┐
│   app/api/routes_*.py    │  ← HTTP 路由，参数解析，调用服务
├──────────────────────────┤
│   app/services/*.py      │  ← 业务编排，跨模块协调，AI 调用
├──────────────────────────┤
│   app/db/repositories/*  │  ← 纯数据库操作（本文档）
├──────────────────────────┤
│   app/models/*.py        │  ← ORM 模型定义
├──────────────────────────┤
│   app/db/session.py      │  ← 引擎与 Session 工厂
└──────────────────────────┘
```

**向后兼容**：`app/services/__init__.py` 从 `db.repositories` 重导出所有函数，因此路由层 `from app.services import create_course` 仍然有效。

---

## 10. 扩展指南

### 10.1 新增一个仓库模块

1. 在 `app/db/repositories/` 下新建 `foo.py`
2. 实现 `require_foo` 权限校验和 CRUD 函数
3. 如需路由层使用，在 `app/services/__init__.py` 中添加重导出
4. 如需业务编排，在 `app/services/` 下新建 `foo_service.py`，导入仓库函数

### 10.2 新增一张表

1. 在 `app/models/` 下新建模型文件，继承 `from app.db.session import Base`
2. `init_db()` 会自动发现新表并创建
3. 如需向量检索，在 `vector_store.py` 中扩展

### 10.3 生产环境切换数据库

```bash
# .env
DATABASE_URL=postgresql+psycopg2://user:pass@host:5432/zhixue
VECTOR_DB_URL=postgresql+psycopg2://user:pass@host:5432/zhixue
```

重启服务即可，关系库和向量库都会使用 PostgreSQL。建议部署前用 Alembic 管理 Schema 迁移。
