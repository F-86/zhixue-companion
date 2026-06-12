# 智学伴侣 · 后端测试设计

本文档描述后端测试的架构、策略、Fixture 体系以及各测试模块的设计思路。

---

## 1. 概览

| 维度 | 取值 |
|------|------|
| 框架 | pytest 9.0 + pytest-mock 3.15 |
| 测试文件 | 6 个（`test_*.py`） |
| 测试用例 | 159 个 |
| 数据库 | 内存 SQLite（`:memory:`），每用例重建 |
| 外部依赖 | 全部 Mock（MiniMax API、向量库、C++ 扩展） |
| 运行方式 | `uv run pytest` |

### 1.1 测试文件清单

```
backend/tests/
├── conftest.py                      # 公共 fixture（db、make_user、make_course、enroll）
├── test_minimax_client.py           # MiniMax HTTP 客户端（58 用例）
├── test_chat_service.py             # 智能问答服务（14 用例）
├── test_learning_plan_service.py    # 学习计划与进度（21 用例）
├── test_quiz_grading.py             # 客观题自动批改（21 用例）
├── test_text_chunking.py            # 文本分块与哈希（12 用例）
└── test_vector_utils.py             # 向量 Rerank 精排（13 用例）
```

---

## 2. 核心设计原则

### 2.1 无外部依赖

```
测试依赖矩阵：
  ✅ 内存 SQLite          — 本地零依赖
  ✅ Mock MiniMax API     — 不产生网络请求
  ❌ ChromaDB             — 从未连接
  ❌ pgvector             — 从未连接
  ❌ C++ pybind11 扩展    — 从未加载
```

测试可以在任意环境运行——CI 服务器、开发者本地，甚至离线环境。不需要 `.env` 文件。

### 2.2 数据库隔离

每个测试函数获取一个**全新的内存 SQLite 数据库**：

```python
@pytest.fixture(scope="function")    # ← 关键：每个测试独立实例
def db():
    engine = create_engine("sqlite:///:memory:", ...)
    Base.metadata.create_all(bind=engine)
    session = Session(bind=engine)
    yield session
    session.close()
    Base.metadata.drop_all(bind=engine)   # 清理：测试后销毁所有表
    engine.dispose()
```

**为什么用 `scope="function"` 而非 `scope="module"`**：
- 每个测试可以自由插入脏数据，不影响其他测试
- 无测试执行顺序依赖
- 可并行运行（pytest-xdist）

### 2.3 Mock 层级

```
测试代码
    │
    ├── Mock: app.services.minimax_client.xxx()       ← MiniMax API
    ├── Mock: app.db.vector_store.query_chunks()       ← 向量库
    ├── Mock: app.db.repositories.quiz.xxx()           ← 仓库函数（依赖其他表）
    │
    └── 真实调用: app.db.repositories.* (SQLite)       ← 数据操作
```

Mock 路径直接指向**函数实际被导入的模块**，而非重导出层。例如：

```python
# learning_plan_service.py 内部:
#   from app.db.repositories.quiz import get_quiz_scores_for_signals
# 所以 mock 路径必须是:
mocker.patch("app.db.repositories.quiz.get_quiz_scores_for_signals", ...)
```

---

## 3. 公共 Fixture

`conftest.py` 提供 4 个 fixture，被所有测试文件共享：

### 3.1 `db`

每个测试函数的独立 SQLite 数据库 session。用法：

```python
def test_something(db, make_user, make_course):
    user = make_user()
    course = make_course(user.id)
    # db 中已有 user 和 course
```

### 3.2 `make_user`

创建用户工厂函数。默认 `role="student"`，支持 `extra` 字典：

```python
teacher = make_user(role="teacher")
student = make_user(role="student", extra={
    "interests": ["算法", "数据库"],
    "career_direction": "backend",
})
```

**内部行为**：
- 自动生成唯一 `username`
- 密码固定哈希为 `"password123"` 的 bcrypt 哈希
- 创建后立即 `commit` + `refresh`

### 3.3 `make_course`

创建课程工厂函数。需要 `teacher_id`：

```python
course = make_course(teacher_id=teacher.id)
```

生成的课程使用固定名称 `"测试课程"` 和代码 `"TEST01"`。

### 3.4 `enroll`

将学生加入课程的快捷函数：

```python
enroll(course_id=course.id, student_id=student.id)
```

---

## 4. 测试模块详解

### 4.1 `test_minimax_client.py`（58 用例）

**测试目标**：MiniMax HTTP 客户端的完整接口层，不涉及数据库。

**测试范围**：

| 被测函数 | 用例数 | 覆盖要点 |
|---------|:-----:|---------|
| `_parse_json` | 8 | 合法 JSON 对象/数组、markdown 包裹、截断修复、非法输入 |
| `_chat` | 4 | 正常返回、HTTP 500、网络错误、temperature 传递 |
| `_chat_stream` | 5 | SSE 流解析、空 delta 跳过、非法行忽略、HTTP 错误 |
| `embed_texts` | 7 | 空列表、格式 A（index 排序）、格式 B、批量分批、未知格式 |
| `embed_query` | 1 | 单条返回 |
| `answer_question` | 5 | 结构化返回、上下文传递、历史消息、无课程降级 |
| `answer_question_stream` | 3 | 流式输出 |
| `generate_summary` | 5 | structured/brief/review 三种类型、降级 |
| `generate_learning_plan` | 3 | 计划结构、降级、参数传递 |
| `grade_quiz_answer` | 4 | 批改结果、分数截断、降级、temperature |
| `grade_submission` | 5 | 完整批改、无参考答案、分数截断、降级、temperature |
| `adjust_learning_plan` | 3 | 调整结果、降级保留原计划 |
| `analyze_submissions` | 4 | 可疑对、单份提交、降级、维度传递 |

**Mock 策略**：所有测试通过 `mocker.patch.object(minimax_client, "_chat", ...)` 和 `mocker.patch.object(minimax_client, "_get_client", ...)` 拦截 HTTP 调用，验证参数和返回值的正确性。

### 4.2 `test_chat_service.py`（14 用例）

**测试目标**：智能问答服务的 RAG 检索、消息发送、后台持久化。

**测试范围**：

| 被测函数 | 用例数 | 覆盖要点 |
|---------|:-----:|---------|
| `_rag_retrieve` | 5 | 正常检索、section_id 过滤、Embedding 失败降级、向量库失败降级、空结果 |
| `send_message` | 7 | 完整流程、_save_ctx 构造、rag_used 标记、session_id 透传、历史加载、权限校验 |
| `save_messages` | 3 | 双记录写入、内容正确性、数据库异常静默处理 |

**关键设计**：

- `send_message` 的 `_save_ctx` 测试验证返回的上下文包含了后台任务写入所需的所有字段
- `save_messages` 的异常测试验证数据库故障时不抛异常（`.rollback()` + `.close()` 正常执行）

### 4.3 `test_learning_plan_service.py`（21 用例）

**测试目标**：学习计划生成的信号采集、RAG 检索、计划创建、进度跟踪、多轮调整。

**测试范围**：

| 被测函数 | 用例数 | 覆盖要点 |
|---------|:-----:|---------|
| `_collect_signals` | 9 | 空学生、profile 采集、字段过滤、chat/quizzes/questions/summaries/discussions 信号、sources 精确性 |
| `_rag_retrieve_for_plan` | 4 | 正常检索、空薄弱点、API 降级、多薄弱点拼接 |
| `create_plan` | 5 | 返回结构、数据库持久化、data_sources 包含 profile、RAG 数据源、403 错误 |
| mark_task | 3 | 创建记录、重复更新、无效 day |
| get_progress | 2 | 完成率计算、未完成任务默认值 |
| adjust_plan | 3 | 归档旧计划、版本递增、非 active 报错 |

**关键设计**：

- 8 类信号（profile、scores、assignments、quizzes、chat_sessions、questions、summaries、discussions）各有独立测试用例，确保信号采集的完整性
- `_collect_signals` 使用 Mock 替代 `get_quiz_scores_for_signals`，其他信号直接写入数据库

### 4.4 `test_quiz_grading.py`（21 用例）

**测试目标**：客观题自动批改逻辑 `_is_correct`，纯函数测试，零数据库依赖。

| 题型 | 用例数 | 覆盖要点 |
|------|:-----:|---------|
| 单选题 | 7 | 正确/错误、大小写不敏感、去除空白、空答案、空正确答案、None 正确答案 |
| 判断题 | 5 | true/false 正确、大小写不敏感 |
| 多选题 | 10 | 相同顺序、不同顺序、漏选、多选、全错、单选项、逗号降级解析、空列表 |
| 简答题 | 1 | 不崩溃 |

**关键设计**：使用 `types.SimpleNamespace` 模拟 SQLAlchemy 模型对象，避免数据库依赖。只验证 `question_type` 和 `correct_answer` 两个属性。

### 4.5 `test_text_chunking.py`（12 用例）

**测试目标**：课件文本分块算法、SHA-256 哈希、增量更新检测。

| 被测函数 | 用例数 | 覆盖要点 |
|---------|:-----:|---------|
| `_char_split` | 5 | 空文本、短文本、超长文本分块、块大小限制、句号边界优先 |
| `_split_text` | 10 | 空文本、短文本单块、空行切分、Markdown 标题切分、多级标题、超长段落降级、内容完整性、空块过滤 |
| `_text_hash` | 4 | 相同文本相同 hash、不同不同、SHA-256 格式、空白敏感 |
| 综合场景 | 2 | 内容修改 hash 变化、分块幂等性 |

**关键设计**：
- `_split_text` 模拟真实课件场景——含多级标题、段落、列表，验证不少于 4 个有意义的块
- 分块幂等性测试确保相同输入始终产生相同输出

### 4.6 `test_vector_utils.py`（13 用例）

**测试目标**：向量 Rerank 精排逻辑，纯数学函数测试，零外部依赖。

| 被测函数 | 用例数 | 覆盖要点 |
|---------|:-----:|---------|
| `_cosine_similarity` | 7 | 相同向量=1.0、正交=0.0、相反=-1.0、零向量=0.0、已知值验证、1536 维向量、对称性 |
| `_rerank` | 10 | Top-K 返回、降序排列、最相关排第一、embedding 字段移除、top_k 超限、空候选、无 embedding 候选、精度 4 位、顺序校正 |

**关键设计**：
- 1536 维向量测试与 MiniMax `embo-01` 实际维度一致
- `_rerank` 验证了能纠正粗筛排序误差的场景

---

## 5. 测试运行

```bash
# 运行全部 159 个测试
cd backend && uv run pytest -v

# 按关键字筛选
uv run pytest -v -k "chat"

# 按文件运行
uv run pytest -v tests/test_minimax_client.py

# 按标记（暂无自定义标记，依赖 pytest 内置标记）
uv run pytest -v -m "not slow"
```

### 5.1 测试依赖

```toml
# backend/pyproject.toml
[tool.uv]
dev-dependencies = [
    "pytest>=9.0.3",
    "pytest-mock>=3.15.1",
]
```

`pytest-mock` 提供 `mocker` fixture，封装 `unittest.mock`，支持自动还原（无需手动 `stop`）。

---

## 6. 编写新测试指南

### 6.1 选择测试文件

| 被测代码位于 | 测试文件 |
|------------|---------|
| `app/services/minimax_client.py` | `test_minimax_client.py` |
| `app/services/chat_service.py` | `test_chat_service.py` |
| `app/services/learning_plan_service.py` / `plan_progress_service.py` | `test_learning_plan_service.py` |
| `app/services/quiz_service.py` 中的 `_is_correct` / `_split_text` / `_text_hash` / `_cosine_similarity` / `_rerank` | `test_quiz_grading.py` / `test_text_chunking.py` / `test_vector_utils.py` |
| 新的服务/仓库模块 | 新建 `test_<module>.py` |

### 6.2 测试模板

```python
"""<模块> 服务测试。"""
import uuid
import pytest
from app.services import my_service
import app.models.my_model


class TestMyFunction:
    def test_happy_path(self, db, make_user, make_course, enroll, mocker):
        # 1. 准备数据
        student = make_user(role="student")
        teacher = make_user(role="teacher")
        course = make_course(teacher_id=teacher.id)
        enroll(course.id, student.id)

        # 2. Mock 外部依赖
        mocker.patch("app.services.minimax_client.some_func",
                     return_value={"result": "mocked"})

        # 3. 调用被测函数
        result = my_service.do_something(
            course_id=course.id,
            student_id=student.id,
            db=db,
        )

        # 4. 断言
        assert result["key"] == "expected"

    def test_error_case(self, db, mocker):
        from fastapi import HTTPException
        mocker.patch("app.services.minimax_client.some_func",
                     side_effect=RuntimeError("API 不可用"))
        with pytest.raises(HTTPException):
            my_service.do_something(...)
```

### 6.3 Mock 路径规则

```
服务层内部 import 形式             →  Mock 路径
──────────────────────────────────────────────────
from app.services.minimax_client import func
                                   → app.services.minimax_client.func
from app.db.vector_store import func
                                   → app.db.vector_store.func
from app.db.repositories.quiz import func
                                   → app.db.repositories.quiz.func
```

**不要 mock 重导出路径**（如 `app.services.quiz_service.func`），因为服务层内部直接 `import` 源模块。

### 6.4 数据库相关测试

- **需要数据库的测试**：接收 `db` fixture，直接操作 ORM 写入数据
- **不需要数据库的测试**：使用 `types.SimpleNamespace` 模拟模型对象，或直接测试纯函数

---

## 7. 未覆盖的模块（当前缺口）

以下模块目前无独立测试：

| 模块 | 原因 | 覆盖情况 |
|------|------|---------|
| `routes_*.py` | HTTP 路由层 | 可通过 FastAPI `TestClient` 或集成测试覆盖 |
| `services/course_service.py` 等重导出层 | 纯重导出，无新增逻辑 | 仓库函数本身通过上层测试间接覆盖 |
| `db/repositories/user.py` 等 | 仓库层 | JWT 生成/验证需独立测试；CRUD 通过上层间接覆盖 |
| `file_processing/processor.py` | C++ 扩展封装 | 需要编译 C++ 扩展才能测试，当前通过降级逻辑保证可用性 |
| `db/vector_store.py` | ChromaDB/pgvector 实际连接 | 需要向量库运行环境，当前通过 Mock 间接覆盖 |
| `db/session.py` / `init_db.py` | 基础设施工厂 | 测试框架本身依赖它们，间接验证 |

### 7.1 建议优先补充的测试

1. **`db/repositories/user.py`**：`register_student`、`login`、`get_current_user` 的 JWT 签发和校验
2. **`db/repositories/quiz.py`**：`submit_attempt`、`start_attempt` 的完整流程
3. **`db/repositories/course.py`**：`list_teacher_courses`、成绩计算的边界情况
4. **`routes_*.py`** 集成测试：使用 FastAPI `TestClient` + 内存 SQLite，验证端到端的 HTTP 响应格式
