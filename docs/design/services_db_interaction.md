# 智学伴侣 · 服务层与数据库层交互设计

本文档详细描述 `app/services/`（业务服务层）与 `app/db/repositories/`（数据仓库层）之间的交互模式、Session 生命周期、以及三种典型的服务实现方式。

---

## 1. 分层关系

```
┌─────────────────────────────────────────────────┐
│                app/api/routes_*.py               │
│        解析 HTTP 请求，调用服务函数，格式化响应    │
└──────────────────────┬──────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────┐
│              app/services/*.py                   │
│    ┌──────────────────┐  ┌────────────────────┐ │
│    │  纯重导出层       │  │  业务编排层         │ │
│    │  (14 个模块)      │  │  (6 个模块)         │ │
│    │                  │  │                    │ │
│    │  直接 re-export  │  │  调 repo → 调 AI   │ │
│    │  仓库函数         │  │  → 协调结果         │ │
│    └──────┬───────────┘  └─────────┬──────────┘ │
└───────────┼────────────────────────┼────────────┘
            │                        │
┌───────────▼────────────────────────▼────────────┐
│           app/db/repositories/*.py               │
│        纯 SQLAlchemy 查询 + 权限校验              │
└──────────────────────┬──────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────┐
│              app/models/*.py                     │
│            ORM 模型定义 (Base)                    │
└─────────────────────────────────────────────────┘
```

---

## 2. 三种服务实现模式

重构后，`services/` 下的 20 个模块按实现方式分为三类：

### 2.1 模式 A：纯重导出层（14 个模块）

**特征**：服务文件仅从 `db.repositories` 重导出函数，不包含任何业务逻辑。

**文件**：`auth_service.py`、`course_service.py`、`announcement_service.py`、`assignment_service.py`、`section_service.py`、`quiz_service.py`、`score_service.py`、`question_service.py`、`discussion_service.py`、`student_assignment_service.py`、`teacher_assignment_service.py`（及部分内部工具函数重导出）

**实现示例**（`quiz_service.py`）：

```python
"""测试服务 —— 从 db.repositories.quiz 重导出"""
from app.db.repositories.quiz import (
    create_quiz,
    list_teacher_quizzes,
    update_quiz_status,
    get_quiz_attempts_summary,
    list_student_quizzes,
    get_quiz_for_student,
    start_attempt,
    submit_attempt,
    save_answer,
    get_attempt_for_resume,
    get_attempt_result,
    get_quiz_scores_for_signals,
)
```

**调用链**：

```
routes_quizzes.py
    → from app.services import quiz_service as svc
    → svc.create_quiz(course_id, teacher_id, ...)
        → db/repositories/quiz.py::create_quiz()
            → SQLAlchemy Session
```

路由层完全无感知，通过 `app.services` 的统一入口调用。

### 2.2 模式 B：业务编排层（6 个模块）

**特征**：服务文件包含跨模块协调、AI 调用、信号采集等业务逻辑，数据库操作委托给仓库函数。

**文件**：`chat_service.py`、`grading_service.py`、`analyze_service.py`、`learning_plan_service.py`、`plan_progress_service.py`、`summary_service.py`

**实现示例**（`chat_service.py` 核心结构）：

```python
"""智能问答服务 —— 业务编排层"""
from sqlalchemy.orm import Session

# 数据库操作 → repo
from app.db.repositories.course import require_enrollment as _require_enrollment, get_course_name
from app.db.repositories.chat import get_history, save_messages

# AI 调用 → 同层客户端
from app.services.minimax_client import embed_query, answer_question_stream

# 向量检索 → db 层
from app.db.vector_store import query_chunks


def stream_message(course_id, student_id, question, session_id, section_id, db):
    # 1. 权限校验（repo）
    _require_enrollment(course_id, student_id, db)
    
    # 2. 读历史（repo）
    history = get_history(session_id, course_id, db)
    
    # 3. RAG 检索（向量库 + MiniMax Embedding）
    refs = _rag_retrieve(course_id, section_id, question, db)
    
    # 4. 构造上下文 + 调用 MiniMax
    for chunk in answer_question_stream(...):
        yield chunk
    
    # 5. 持久化（repo）
    save_messages(session_id, {...})
```

**调用链**：

```
routes_chat.py
    → from app.services import chat_service as svc
    → svc.stream_message(...)
        ├── db.repositories.course.require_enrollment()     # 仓库函数
        ├── db.repositories.chat.get_history()              # 仓库函数
        ├── db.vector_store.query_chunks()                  # 向量检索
        ├── minimax_client.answer_question_stream()         # AI 调用
        └── db.repositories.chat.save_messages()            # 仓库函数
```

### 2.3 模式 C：全局重导出（`services/__init__.py`）

`app/services/__init__.py` 从所有仓库模块集中重导出常用函数，使路由层可以统一用 `from app.services import create_course` 而不关心底层实现：

```python
# app/services/__init__.py（节选）
from app.db.repositories.user import get_current_user, register_student, login, ...
from app.db.repositories.course import create_course, list_teacher_courses, ...
from app.db.repositories.quiz import create_quiz, submit_attempt, ...
from app.db.repositories.chat import save_messages, get_session_messages, list_sessions
...
```

**效果**：

```
路由层:  from app.services import create_course
              ↓
         services/__init__.py:  from db.repositories.course import create_course
              ↓
         db/repositories/course.py:  def create_course(...)
```

---

## 3. Session 生命周期

### 3.1 正常请求路径

```
FastAPI 收到请求
  │
  ▼
get_db() 创建 Session
  │
  ▼
路由函数 (db = Depends(get_db))
  │
  ├── 调服务函数 (db 作为参数传入)
  │     ├── 调仓库函数 (db 作为参数传入)
  │     │     └── db.query(...) / db.add(...) / db.commit()
  │     └── 调 MiniMax (不涉及 db)
  │
  ▼
FastAPI 关闭 Session (finally: db.close())
  │
  ▼
响应返回客户端
```

**关键约定**：
- 路由层通过 `Depends(get_db)` 获取 Session
- Session 通过函数参数层层传递：路由 → 服务 → 仓库
- 仓库函数**不创建也不关闭** Session，由调用方管理生命周期

### 3.2 后台任务路径

```python
# routes_chat.py
result = chat_service.send_message(...)
save_ctx = result.pop("_save_ctx")
background_tasks.add_task(chat_service.save_messages, result["session_id"], save_ctx)
return _ok(result)
```

```python
# chat_service.py（独立 Session）
def save_messages(session_id: str, ctx: dict) -> None:
    from app.db.session import SessionLocal
    db = SessionLocal()          # ← 独立 Session，不依赖请求生命周期
    try:
        db.add(ChatMessage(...))
        db.add(ChatMessage(...))
        db.commit()
    except Exception:
        db.rollback()
    finally:
        db.close()
```

**为什么需要独立 Session**：FastAPI 在响应发出后关闭请求的 Session，后台任务若继续使用会报 `Instance is not bound to a Session`。

### 3.3 仓库函数签名约定

所有仓库函数遵循统一的参数顺序：

```python
def some_repo_function(business_id_1, business_id_2, ..., db: Session) -> ReturnType:
    """最后一个参数永远是 db: Session"""
```

示例：

```python
# course.py
def require_enrollment(course_id: str, student_id: str, db: Session) -> CourseEnrollment: ...

# quiz.py
def submit_attempt(course_id, quiz_id, attempt_id, student_id, db) -> dict: ...

# plan_progress.py
def mark_task(course_id, plan_id, student_id, day, completed, feedback, db, valid_days) -> dict: ...
```

---

## 4. 权限校验链

### 4.1 三层校验

```
Layer 1: FastAPI Depends (HTTP 层)
    get_current_user → JWT 解码 → 401
    require_student / require_teacher → 角色检查 → 403

Layer 2: 仓库权限函数 (数据层)
    require_enrollment → 学生已加入课程 → 403
    require_teacher_course → 课程属于该教师 → 404
    require_quiz → 测试属于该课程 → 404
    require_plan → 计划属于该学生 → 404
    ...

Layer 3: 业务级检查 (服务层，按需)
    作业未关闭才能提交
    计划状态为 active 才能调整
    ...
```

### 4.2 典型路由的完整校验链

以"学生查看测试"为例：

```python
# routes_quizzes.py
@router.get("/student/courses/{course_id}/quizzes/{quiz_id}")
def get_student_quiz(
    course_id: str,
    quiz_id: str,
    current_user: User = Depends(require_student),           # Layer 1
    db: Session = Depends(get_db),
):
    return quiz_service.get_quiz_for_student(
        course_id, quiz_id, current_user.id, db
    )


# quiz.py (repository)
def get_quiz_for_student(course_id, quiz_id, student_id, db):
    require_enrollment(course_id, student_id, db)            # Layer 2: 学生已加入课程
    require_quiz(quiz_id, course_id, db)                     # Layer 2: 测试属于该课程
    # ... 数据查询
```

---

## 5. 事务边界

### 5.1 commit 时机

| 场景 | commit 位置 | 说明 |
|------|-----------|------|
| 单表写入 | 仓库函数内 `db.commit()` | 如 `create_course`、`submit_attempt` |
| 多表写入 | 仓库函数内统一 commit | 如 `submit_attempt` 同时写 `QuizAttempt` + 多条 `QuizAnswer` |
| 失败回滚 | `try/except` 内 `db.rollback()` | 仓库函数内处理 |

### 5.2 不回滚的场景

| 场景 | 原因 |
|------|------|
| MiniMax 调用失败 | 外部 API 失败不回滚数据库操作（RAG 降级不阻断主流程） |
| 向量库写入失败 | 向量库与关系库独立，不同步回滚 |
| 后台任务写入失败 | 响应已返回，只记录日志 |

---

## 6. 具体交互示例

### 6.1 AI 批改（grading_service）

```
routes_teacher_assignments.py
    → grade_submissions(assignment_id, submission_ids, teacher_id, db)
        │
        ├── 仓库: grade_submission_db()
        │     └── 查提交内容、参考答案、评分标准
        │         返回 [{submission_id, content, reference_answer, rubric, max_score}, ...]
        │
        ├── 循环每份提交:
        │     ├── AI: minimax_client.grade_submission(content, reference_answer, rubric, max_score)
        │     │     返回 {score, comments, deductions, suggestions}
        │     └── 仓库: upsert_grade_result(submission_id, ai_result, db)
        │           └── 写入/更新 AIGradingResult 记录
        │
        └── 返回汇总结果
```

### 6.2 学习计划生成（learning_plan_service）

```
routes_learning_plans.py
    → create_plan(course_id, student_id, goal, available_time_per_day, db)
        │
        ├── 仓库: require_enrollment()  → 权限校验
        │
        ├── 服务内部: _collect_signals()
        │     ├── 直接查 ORM: User.extra, Assignment, Submission, AIGradingResult
        │     ├── 直接查 ORM: ChatMessage, Summary, Question, Discussion
        │     └── 仓库: get_quiz_scores_for_signals()  → 测试成绩
        │     返回 {basis, data_sources}
        │
        ├── 服务内部: _rag_retrieve_for_plan()
        │     ├── minimax_client.embed_query(weak_points)
        │     └── vector_store.query_chunks(embedding, course_id, top_k=3)
        │     返回 [课程材料片段]
        │
        ├── AI: minimax_client.generate_learning_plan(course_name, goal, basis, time)
        │     返回 {analysis, plan}
        │
        └── 仓库: create_plan_obj(course_id, student_id, ...)
              └── 写入 LearningPlan 记录
```

### 6.3 查重分析（analyze_service）

```
routes_teacher_assignments.py
    → analyze(assignment_id, submission_ids, teacher_id, threshold, dimensions, db)
        │
        ├── 直接查 ORM: Assignment, Submission, SubmissionFile, File, User
        │     收集所有提交文本 → [{id, student_name, text}, ...]
        │
        ├── file_processing: get_fingerprint(text) × N
        │     每份提交的指纹 → {submission_id: [hash1, hash2, ...]}
        │
        ├── file_processing: batch_compare(texts, threshold)
        │     返回可疑对 [(i, j, similarity), ...]
        │
        ├── AI: minimax_client.analyze_submissions(submissions, suspect_pairs, dimensions)
        │     返回 {suspicious_pairs, comparison_details, common_issues, teaching_suggestions}
        │
        └── 仓库: upsert_report(assignment_id, ai_result, fingerprint_data, db)
              └── 写入/更新 AnalysisReport
```

---

## 7. 测试中的仓库模式

测试遵循"mock 最外层依赖"原则：

```python
# 仓库函数在服务层内被 import，mock 路径指向仓库模块
mocker.patch("app.db.repositories.quiz.get_quiz_scores_for_signals",
             return_value=[...])

# MiniMax 在服务层内被 import，mock 路径指向 minimax_client
mocker.patch("app.services.minimax_client.generate_learning_plan",
             return_value={...})

# 向量库在服务层内被 import，mock 路径指向 vector_store
mocker.patch("app.db.vector_store.query_chunks",
             return_value=[...])
```

服务层内部使用 `from ... import ...` 方式导入仓库函数，测试 mock 时需针对**实际被导入的模块**打补丁，而非重导出层。

---

## 8. 迁移指南

### 8.1 将仓库函数从服务层迁移到仓库层

当发现某个服务文件中有纯数据库操作时：

1. **提取**：将函数移到 `app/db/repositories/<domain>.py`
2. **参数化**：确保 `db: Session` 是最后一个参数
3. **重导出**：在 `app/services/<domain>_service.py` 中添加 `from app.db.repositories.<domain> import the_function`
4. **更新调用方**：路由层通过 `app.services` 的导入不受影响；服务层内部调用需更新 import 路径
5. **更新测试 mock 路径**：从 `app.services.xxx_service.func` 改为 `app.db.repositories.xxx.func`

### 8.2 新增一个业务编排服务

1. 在 `app/services/` 下新建 `foo_service.py`
2. 从 `app.db.repositories` 导入所需的仓库函数
3. 从 `app.services.minimax_client` 导入 AI 调用（如需）
4. 编排逻辑写在服务函数中
5. 在 `app/services/__init__.py` 中添加重导出（如需路由层直接访问）
6. 在 `app/api/` 中新建或更新路由文件
