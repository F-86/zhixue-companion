# 智学伴侣 · 总体架构设计

## 1. 项目定位

智学伴侣是一个以 AI 为核心的校园学习辅助系统，面向高校学生和教师。  
**不是**传统教学平台（排课/成绩管理），而是聚焦：

- 学生侧：AI 陪伴学习（问答、总结、计划）
- 教师侧：AI 辅助处理作业（批改、查重、比对）

---

## 2. 系统边界

```
┌─────────────────────────────────────────────────┐
│                  浏览器 / 客户端                   │
│     React SPA（学生端 + 教师端合并为同一应用）      │
└───────────────────┬─────────────────────────────┘
                    │ HTTPS REST + JSON
┌───────────────────▼─────────────────────────────┐
│               FastAPI 后端服务                    │
│  ┌──────────┐ ┌──────────┐ ┌──────────────────┐ │
│  │  认证层  │ │  业务层  │ │   AI 适配层       │ │
│  │  JWT     │ │ Services │ │ MiniMax Client    │ │
│  └──────────┘ └──────────┘ └──────────────────┘ │
│  ┌──────────────────┐  ┌───────────────────────┐ │
│  │  关系型数据库     │  │     向量数据库         │ │
│  │ SQLite/PostgreSQL│  │ ChromaDB / pgvector   │ │
│  └──────────────────┘  └───────────────────────┘ │
│  ┌──────────────────────────────────────────────┐ │
│  │         C++ 文件处理扩展（pybind11）           │ │
│  └──────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────┘
                    │
        ┌───────────▼───────────┐
        │    MiniMax 大模型 API  │
        │  abab6.5s-chat        │
        │  embo-01 (Embedding)  │
        └───────────────────────┘
```

---

## 3. 技术栈选型

### 3.1 前端

| 技术 | 版本 | 选型理由 |
|------|------|---------|
| React | 19 | 生态成熟，组件复用性好 |
| TypeScript | 6 | 类型安全，接口契约清晰 |
| Vite | 8 | 构建速度快，ESM 原生支持 |
| React Router | 7 | 声明式路由，支持嵌套和守卫 |
| Axios | 1.x | 拦截器机制便于统一处理 token 和错误 |
| Tailwind CSS | 4 | 原子化 CSS，无需维护样式文件 |

**包管理器选 pnpm**：避免 phantom dependency、节省磁盘。

### 3.2 后端

| 技术 | 版本 | 选型理由 |
|------|------|---------|
| Python | 3.10+ | 类型注解成熟，AI 生态最佳 |
| FastAPI | 0.111+ | 自动生成 OpenAPI 文档，依赖注入友好 |
| SQLAlchemy | 2.0 | Mapped 类型注解，ORM 与裸 SQL 均支持 |
| Pydantic | 2.0 | 严格的请求/响应校验 |
| uv | 最新 | 极速依赖解析，替代 pip + venv |
| bcrypt | 4.x | 密码哈希行业标准 |
| python-jose | 3.x | JWT 签发与验证 |
| httpx | 0.27+ | 同步/异步 HTTP 客户端，连接池复用 |

### 3.3 数据存储

| 存储 | 用途 | 切换方式 |
|------|------|---------|
| SQLite（默认） | 关系数据，课程设计/本地开发 | 改 `DATABASE_URL` 即切换 PostgreSQL |
| ChromaDB（默认） | 向量存储，本地持久化 | 填写 `VECTOR_DB_URL` 即切换 pgvector |
| 本地文件系统 | 上传文件（课件、作业附件） | `upload_dir` 可配置，未来可接 OSS |

**双存储抽象**是亮点：所有向量库操作通过 `vector_store.py` 门面封装，调用方无感知切换。

### 3.4 AI 服务

| 模型 | 用途 |
|------|------|
| `abab6.5s-chat` | 问答、总结、学习计划、批改、查重 |
| `embo-01` | 文本 Embedding（1536 维），用于 RAG 检索 |

---

## 4. 分层架构

```
表现层（React Pages）
    ↓ HTTP 请求（Axios）
API 路由层（FastAPI routes_*.py）
    ↓ 调用服务函数
业务服务层（services/*.py）—— 业务编排 + AI 调用
    ↓                    ↓
数据仓库层（db/repositories/*.py）  外部适配层（minimax_client.py / file_processing/）
    ↓
数据模型层（models/*.py → SQLAlchemy ORM）
    ↓
存储层（SQLite/PostgreSQL + ChromaDB/pgvector + 文件系统）
```

### 各层职责

| 层 | 职责 | 代表文件 |
|----|------|---------|
| API 路由层 | 解析请求、鉴权注入、调服务、格式化响应 | `routes_chat.py` |
| 业务服务层 | 业务逻辑、事务、AI 调用编排 | `chat_service.py`、`grading_service.py` |
| 数据仓库层 | 纯 SQLAlchemy 查询、权限校验 | `db/repositories/chat.py` |
| 数据模型层 | ORM 映射、表结构定义 | `models/section.py` |
| 外部适配层 | MiniMax HTTP 客户端、C++ 文件处理 | `minimax_client.py`、`file_processing/processor.py`（详见 [file_processing.md](file_processing.md)） |
| 向量存储层 | ChromaDB/pgvector 双后端抽象 | `db/vector_store.py` |

---

## 5. 关键设计决策

### 5.1 单体 vs 微服务

**选择单体**。原因：

- 课程设计阶段，团队规模小，拆分带来的运维成本远大于收益
- FastAPI 的依赖注入本身已经做到了层级隔离
- C++ 扩展以 pybind11 内嵌于 `app/file_processing/`，无额外进程，调用延迟 < 1ms

未来扩展路径：C++ 模块可以独立为 gRPC 微服务，其余保持单体。

### 5.2 同步 vs 异步

**混合策略**：

- 常规数据库操作：**同步**（SQLAlchemy synchronous session）
- MiniMax API 调用：**同步 httpx.Client**（连接池复用，避免 asyncio 上下文切换开销）
- 消息持久化：**BackgroundTasks**（FastAPI 后台任务，响应返回后异步执行，降低 P99 延迟）

具体见 `routes_chat.py`：

```python
# 先返回响应，后台再写消息
save_ctx = result.pop("_save_ctx")
background_tasks.add_task(svc.save_messages, result["session_id"], save_ctx)
return _ok(result)
```

### 5.3 双数据库抽象

`vector_store.py` 是核心设计：

```python
def _use_pg() -> bool:
    url = settings.vector_db_url.strip()
    return bool(url) and url.startswith("postgresql")

def query_chunks(query_embedding, course_id, top_k=3):
    recall_k = max(top_k * 4, 10)
    candidates = _pg_query(...) if _use_pg() else _chroma_query(...)
    return _rerank(candidates, query_embedding, top_k)
```

切换数据库：改一个环境变量，代码零修改。

### 5.4 配置管理

`core/config.py` 使用 `pydantic-settings`：

- `.env` 文件自动读取（`.env` 不提交到 git）
- 所有路径以 `backend/` 目录为锚点，`os.chdir` 不会影响文件位置
- 允许 `extra="ignore"`，环境变量中多余字段不报错

### 5.5 错误处理策略

| 错误类型 | 处理方式 |
|---------|---------|
| 业务逻辑错误（权限、不存在） | `raise HTTPException(status_code=4xx)` |
| 外部 API 失败（MiniMax） | `raise RuntimeError`，由全局 500 handler 捕获 |
| RAG 检索失败 | **静默降级**，返回空列表，不影响主流程 |
| 消息持久化失败 | 后台日志，不影响已返回的响应 |
| 向量化失败 | 日志记录，不阻断小节创建 |
| C++ 模块不可用 | try/except 跳过，服务仍可用 |

**核心原则**：AI 相关功能全部降级处理，不因外部服务不可用而影响主干功能。

---

## 6. 目录结构

```
zhixue-companion/
├── backend/
│   ├── pyproject.toml           # uv 项目配置
│   ├── app/
│   │   ├── main.py              # FastAPI 入口，lifespan 管理
│   │   ├── core/
│   │   │   ├── config.py        # 配置（pydantic-settings）
│   │   │   └── security.py      # JWT / bcrypt 工具
│   │   ├── db/
│   │   │   ├── session.py       # SQLAlchemy engine/session
│   │   │   ├── init_db.py       # 建表入口
│   │   │   ├── vector_store.py  # 向量库双后端封装
│   │   │   └── repositories/    # 数据仓库层（18 个模块）
│   │   │       ├── user.py      # 用户 / 认证
│   │   │       ├── course.py    # 课程管理
│   │   │       ├── section.py   # 小节 + 材料分块
│   │   │       ├── assignment.py
│   │   │       ├── submission.py
│   │   │       ├── grade.py     # AI 批改结果
│   │   │       ├── analysis_report.py
│   │   │       ├── quiz.py
│   │   │       ├── chat.py
│   │   │       ├── summary.py
│   │   │       ├── learning_plan.py
│   │   │       ├── plan_progress.py
│   │   │       ├── announcement.py
│   │   │       ├── discussion.py
│   │   │       ├── question.py
│   │   │       ├── score.py
│   │   │       └── file.py
│   │   ├── file_processing/     # C++ 文件处理封装
│   │   │   └── processor.py     # pybind11 扩展调用
│   │   ├── models/              # ORM 模型（17 张表）
│   │   ├── schemas/             # Pydantic 请求/响应模型
│   │   ├── api/                 # FastAPI 路由（12 个模块）
│   │   └── services/            # 业务编排层
│   │       ├── __init__.py      # 从 db.repositories 重导出
│   │       ├── chat_service.py  # 智能问答编排
│   │       ├── learning_plan_service.py
│   │       ├── plan_progress_service.py
│   │       ├── summary_service.py
│   │       ├── grading_service.py
│   │       ├── analyze_service.py
│   │       ├── minimax_client.py # MiniMax API 适配
│   │       ├── auth_service.py   # 认证（重导出）
│   │       ├── course_service.py # 课程（重导出）
│   │       └── ...               # 其他领域（重导出）
│   └── tests/                   # pytest 测试
├── frontend/
│   ├── package.json
│   └── src/
│       ├── api/                 # Axios 请求封装
│       ├── components/          # 公共组件（AuthContext/Guard/Layout）
│       ├── pages/               # 页面组件（学生 4 个 + 教师 4 个）
│       ├── router/              # React Router 路由定义
│       ├── types/               # TypeScript 类型声明
│       └── utils/               # 请求工具（request.ts）
├── cpp_processor/               # C++ 文件处理扩展（pybind11）
└── docs/
    └── design/                  # 设计文档（本目录）
```

---

## 7. 启动流程

```
应用启动（lifespan）
   ├── init_db()          → 创建所有 ORM 表
   ├── init_vector_store() → 初始化 ChromaDB 或 pgvector
   └── _get_client()       → 预热 MiniMax HTTP 连接池

请求处理流程
   接受请求
   → JWT 鉴权（Depends(get_current_user)）
   → 路由函数（routes_*.py）
   → 业务服务（services/*.py）
   → 数据库操作 / AI 调用 / C++ 扩展
   → 格式化响应返回
   → （可选）BackgroundTasks 异步持久化
```

---

## 8. 部署

### 8.1 后端进程管理（server.sh）

项目根目录提供 `server.sh` 脚本，封装后端服务的启动/停止/重启/状态查看：

```bash
./server.sh start    # 后台启动，日志写入 logs/backend.log
./server.sh stop     # 优雅停止（SIGTERM，超时后 SIGKILL）
./server.sh restart  # 停止 + 启动
./server.sh status   # 查看运行状态（含 HTTP 健康检查）
./server.sh log      # 实时跟踪日志（tail -f）
```

默认监听 `0.0.0.0:8000`，可通过环境变量覆盖：

```bash
PORT=9000 ./server.sh start
HOST=127.0.0.1 ./server.sh start
```

**脚本行为说明**：

| 机制 | 说明 |
|------|------|
| 进程持久化 | 使用 `nohup` 后台运行，PID 写入 `pids/backend.pid` |
| 日志 | 标准输出/错误均追加到 `logs/backend.log` |
| 健康检查 | `status` 命令调用 `GET /api/health`，验证服务是否真正就绪 |
| 重复启动防护 | 已有进程运行时 `start` 命令直接返回警告，不重复启动 |
| 启动确认 | 启动后最多等待 5 秒确认进程存活，失败时清理 PID 文件 |

### 8.2 首次部署步骤

```bash
# 1. 配置环境变量
cp backend/.env.example backend/.env
# 编辑 .env，填写 MINIMAX_API_KEY 等

# 2. 安装依赖（uv 自动处理虚拟环境）
cd backend && uv sync && cd ..

# 3. 启动后端
./server.sh start

# 4. 验证
./server.sh status
# 健康检查: HTTP 200 ✓

# 5. 构建并托管前端（生产环境）
cd frontend && pnpm install && pnpm build
# 将 dist/ 由 Nginx 托管
```

### 8.3 生产环境配置

**数据库切换**（`backend/.env`）：

```bash
# 切换 PostgreSQL（同时用于关系库和向量库）
DATABASE_URL=postgresql+psycopg2://user:pass@host:5432/zhixue
VECTOR_DB_URL=postgresql+psycopg2://user:pass@host:5432/zhixue
```

**Nginx 参考配置**：

```nginx
# 前端静态资源 + API 反向代理
server {
    listen 80;
    server_name your-domain.com;

    location /api/ {
        proxy_pass http://127.0.0.1:8000/api/;
    }

    location /files/ {
        proxy_pass http://127.0.0.1:8000/files/;
    }

    location / {
        root /path/to/frontend/dist;
        try_files $uri /index.html;
    }
}
```

**CORS**：使用 Nginx 反代后前后端同域，`allow_origins=["*"]` 可收窄为具体域名：

```python
allow_origins=["https://your-domain.com"]
```
